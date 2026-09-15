"""Core of the eval harness (piece 4): compare a generated postmortem
against the real human postmortem and produce an :class:`EvalReport`.

Fully deterministic and AI-free: every metric below is a documented
heuristic over token sets (``pmg.contracts.content_tokens``), Jaccard /
overlap ratios (``pmg.contracts.jaccard`` / ``overlap_ratio``) and sha
normalization (``pmg.contracts.sha10``). No network, no model, no
randomness — the same inputs always produce the same report.

Heuristics (canonical names in ``pmg.contracts.METRIC_NAMES``):

- ``introducer_top1`` (bool): the introducer the postmortem COMMITS to.
  Hex sha tokens (regex ``\\b[0-9a-f]{7,40}\\b`` over the root_cause body +
  claim texts, lowercased) are normalized with ``sha10``. When ``evidence``
  is supplied, the committed introducer is the best-ranked evidence
  candidate whose sha10 appears among the tokens (candidate order = score
  rank; a root_cause section routinely quotes the FIX sha first, which is
  not an introducer claim); without evidence it is the first distinct
  token. True iff the committed sha10 equals ``sha10(gt.introducer.full_sha
  or short_sha)``. No sha token in the section -> False ("no introducer
  sha stated").
- ``introducer_top5`` (bool): the ground-truth sha10 is among the first
  five DISTINCT sha10 tokens found in the root_cause section. For
  issues-only cases (``evidence`` without a fix commit, e.g. operational
  incidents) with a null ground-truth introducer, both introducer metrics
  are False with the detail "no fix commit / no introducer candidates
  (issues-only case)".
- ``timeline_recall`` (float | None): a gt timeline event counts as
  matched when some generated timeline entry (each claim, plus each body
  line that is a markdown list item or contains a YYYY-MM-DD date)
  (a) shares a sha10 token with it, OR (b) lies within ±3 days AND has
  content-token Jaccard >= 0.3. Value = matched / total gt events;
  None (undefined) when gt has no timeline events.
- ``timeline_precision`` (float): generated timeline entries that match
  some gt event (same pairwise rule) / total generated entries (0.0 when
  there are none).
- ``action_item_overlap`` (float | None): generated action items are the
  markdown list items of the action_items body (whole body if no list
  markers) plus the section's claims. A gt item is covered when the best
  ``overlap_ratio(gt_tokens, gen_tokens)`` over generated items is
  >= 0.35. Value = covered / total gt items; None when gt has none.
- ``root_cause_match`` (float): max( jaccard, overlap_ratio ) between
  content_tokens(root_cause body + claims) and content_tokens(
  gt.root_cause.statement + " " + gt.root_cause.quote); overlap_ratio is
  directed, generated-tokens-covered-by-ground-truth.
- ``honesty_check`` (bool): every section in ``HONESTY_SECTIONS``
  ("impact", "detection") passes: either badge "red" AND the body
  contains "no evidence" (case-insensitive), or badge "green"/"yellow"
  AND at least one of its claims cites an EXTERNAL source (a ref
  containing "http" or starting with "external:"). A missing section
  fails and is named in the detail.
- ``claim_linkage_rate`` (float): over ALL claims in the postmortem.
  Strict mode (an ``Evidence`` is passed): a claim counts when it has a
  non-empty ref list and every ref is in ``Evidence.ref_ids()``.
  Lenient mode (no Evidence): non-empty refs. 0.0 when there are no
  claims.
- ``line_agreement`` (float | None): sentence-level recall over the human
  postmortem text (``pmg.eval.ground_truth.sentences``): the share of
  human sentences with >= 6 content tokens that have a counterpart
  sentence anywhere in ``pm.markdown`` with Jaccard >= 0.35. None when
  no human text (or no comparable sentences) is available.
- ``wall_clock_seconds`` (float | None): taken from
  ``pm.meta["wall_clock_seconds"]`` when present and numeric.

Robustness: missing sections never raise — the metrics that need them get
False / 0.0 with a "section missing" detail.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any, Optional

from pmg.contracts import (
    HONESTY_SECTIONS,
    METRIC_NAMES,
    Claim,
    EvalReport,
    Evidence,
    Metric,
    Postmortem,
    Section,
    content_tokens,
    jaccard,
    overlap_ratio,
    sha10,
)
from pmg.eval.ground_truth import sentences as _sentences

__all__ = ["evaluate"]

# --- tunable thresholds (single place, mirrored in the docstrings above) ---
_SHA_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

_INTRODUCER_TOP_K = 5
_TIMELINE_DATE_WINDOW_DAYS = 3
_TIMELINE_JACCARD_MIN = 0.3
_ACTION_ITEM_COVER_MIN = 0.35
_LINE_AGREEMENT_JACCARD_MIN = 0.35
_LINE_AGREEMENT_MIN_TOKENS = 6


# ---------------------------------------------------------------------------
# small deterministic extraction helpers
# ---------------------------------------------------------------------------

def _sha10_tokens(text: str) -> list[str]:
    """Ordered distinct sha10 tokens in *text* (lowercased, first occurrence
    order, deduplicated after sha10 normalization)."""
    seen: list[str] = []
    for raw in _SHA_RE.findall((text or "").lower()):
        token = sha10(raw)
        if token and token not in seen:
            seen.append(token)
    return seen


def _parse_date(text: str) -> Optional[date]:
    """First YYYY-MM-DD date in *text* as a ``date``, or None."""
    match = _DATE_RE.search(text or "")
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def _section_text(section: Section) -> str:
    """Body plus claim texts of a section, newline-joined."""
    parts = [section.body] + [c.text for c in section.claims]
    return "\n".join(p for p in parts if p)


def _timeline_entries(section: Section) -> list[dict[str, Any]]:
    """Generated timeline entries: one per claim, plus one per body line
    that is a markdown list item or contains a YYYY-MM-DD date."""
    entries: list[dict[str, Any]] = []
    for claim in section.claims:
        entries.append(_entry(claim.text))
    for line in (section.body or "").splitlines():
        if _LIST_ITEM_RE.match(line) or _DATE_RE.search(line):
            content = _LIST_ITEM_RE.sub("", line).strip()
            if content:
                entries.append(_entry(content))
    return entries


def _entry(text: str) -> dict[str, Any]:
    return {
        "text": text,
        "date": _parse_date(text),
        "shas": set(_sha10_tokens(text)),
    }


def _split_action_items(section: Section) -> list[str]:
    """Split the action_items body into items on markdown list markers
    ("- ", "* ", "+ ", "1. ", "1) "); continuation lines join the current
    item. With no list markers the whole body is one item. Claim texts are
    appended as additional items."""
    items: list[str] = []
    current: Optional[list[str]] = None
    for line in (section.body or "").splitlines():
        if _LIST_ITEM_RE.match(line):
            if current:
                items.append(" ".join(current))
            current = [_LIST_ITEM_RE.sub("", line).strip()]
        elif line.strip() and current is not None:
            current.append(line.strip())
    if current:
        items.append(" ".join(current))
    if not items and (section.body or "").strip():
        items.append(section.body.strip())
    items.extend(c.text for c in section.claims)
    return [i for i in items if i.strip()]


def _gt_introducer_sha10(gt: dict[str, Any]) -> str:
    intro = gt.get("introducer") or {}
    return sha10(str(intro.get("full_sha") or "")) or sha10(str(intro.get("short_sha") or ""))


def _gt_timeline(gt: dict[str, Any]) -> list[dict[str, Any]]:
    """Ground-truth timeline events as {text, date, shas} entries."""
    events: list[dict[str, Any]] = []
    for ev in gt.get("timeline") or []:
        if isinstance(ev, dict):
            text = str(ev.get("event") or ev.get("description") or "")
            raw_date = str(ev.get("date") or "")
        else:
            text, raw_date = str(ev), ""
        entry = _entry(text + " " + raw_date)
        entry["text"] = text
        entry["raw_date"] = raw_date
        events.append(entry)
    return events


def _gt_action_items(gt: dict[str, Any]) -> list[str]:
    items: list[str] = []
    for it in gt.get("action_items") or []:
        items.append(str(it.get("item") or "") if isinstance(it, dict) else str(it))
    return [i for i in items if i.strip()]


def _timeline_pair_rule(gt_ev: dict[str, Any], gen_ev: dict[str, Any]) -> Optional[str]:
    """Return a short human-readable rule string when the pair matches:
    shared sha10, OR (|date delta| <= 3 days AND Jaccard >= 0.3)."""
    if gt_ev["shas"] and (gt_ev["shas"] & gen_ev["shas"]):
        return "sha match"
    if gt_ev["date"] is not None and gen_ev["date"] is not None:
        delta = abs((gt_ev["date"] - gen_ev["date"]).days)
        if delta <= _TIMELINE_DATE_WINDOW_DAYS:
            jac = jaccard(content_tokens(gt_ev["text"]), content_tokens(gen_ev["text"]))
            if jac >= _TIMELINE_JACCARD_MIN:
                return f"date ±{delta}d + jaccard {jac:.2f}"
    return None


# ---------------------------------------------------------------------------
# metric builders (each returns (Metric, detail-fragment))
# ---------------------------------------------------------------------------

def _introducer_metrics(
    pm: Postmortem,
    gt: dict[str, Any],
    candidate_sha10s: list[str] | None = None,
    issues_only: bool = False,
) -> tuple[Metric, Metric, dict[str, Any]]:
    section = pm.section("root_cause")
    gt_sha = _gt_introducer_sha10(gt)

    if section is None:
        tokens: list[str] = []
        top1 = top5 = False
        d1 = d5 = "root_cause section missing"
    elif issues_only and not gt_sha:
        # Ops incident without a fix commit: no candidates were even searched.
        tokens = _sha10_tokens(_section_text(section))
        top1 = top5 = False
        d1 = d5 = (
            "no fix commit / no introducer candidates (issues-only case)"
        )
    else:
        tokens = _sha10_tokens(_section_text(section))
        if not gt_sha:
            top1 = top5 = False
            d1 = d5 = "no ground truth introducer sha to compare against"
        elif not tokens:
            top1 = top5 = False
            d1 = d5 = "no introducer sha stated in root_cause (no hex token [0-9a-f]{7,40})"
        else:
            # The sha the postmortem commits to: prefer mentions that match a
            # ranked evidence candidate (root_cause routinely quotes the FIX
            # sha first, e.g. in a diff excerpt, which is not an introducer
            # claim). Among matching candidates take the best (earliest) rank;
            # fall back to the first distinct token without evidence.
            committed = tokens[0]
            commit_rule = "first distinct sha10 token in root_cause body+claims"
            if candidate_sha10s:
                rank = {sha: i for i, sha in enumerate(candidate_sha10s)}
                matching = [t for t in tokens if t in rank]
                if matching:
                    committed = min(matching, key=lambda t: rank[t])
                    commit_rule = (
                        f"best-ranked evidence candidate mentioned in root_cause "
                        f"(candidate rank {rank[committed]})"
                    )
            top1 = committed == gt_sha
            top5 = gt_sha in tokens[:_INTRODUCER_TOP_K]
            d1 = (
                f"{commit_rule} == sha10(gt.introducer.full_sha or short_sha) "
                f"('{committed}' vs '{gt_sha}')"
            )
            d5 = (
                f"gt sha10 '{gt_sha}' in first {_INTRODUCER_TOP_K} distinct sha10 "
                f"tokens {tokens[:_INTRODUCER_TOP_K]}"
            )
    detail = {
        "gt_sha10": gt_sha,
        "sha_tokens_considered": tokens,
        "top_k": _INTRODUCER_TOP_K,
    }
    return (
        Metric("introducer_top1", top1, detail=f"Heuristic: {d1}."),
        Metric("introducer_top5", top5, detail=f"Heuristic: {d5}."),
        detail,
    )


def _timeline_metrics(
    pm: Postmortem, gt: dict[str, Any]
) -> tuple[Metric, Metric, dict[str, Any]]:
    section = pm.section("timeline")
    gt_events = _gt_timeline(gt)
    gen_entries: list[dict[str, Any]] = _timeline_entries(section) if section else []

    rule = (
        f"match = shared sha10 OR (|date delta| <= {_TIMELINE_DATE_WINDOW_DAYS}d "
        f"AND content-token jaccard >= {_TIMELINE_JACCARD_MIN})"
    )

    # -- recall over ground-truth events ------------------------------------
    table: list[dict[str, Any]] = []
    matched_gt = 0
    for ev in gt_events:
        hit_text: Optional[str] = None
        hit_rule: Optional[str] = None
        for gen in gen_entries:
            why = _timeline_pair_rule(ev, gen)
            if why:
                hit_text, hit_rule = gen["text"], why
                break
        matched_gt += 1 if hit_text else 0
        table.append(
            {
                "gt_date": ev.get("raw_date", ""),
                "gt_event": ev["text"],
                "matched_generated": hit_text,
                "rule": hit_rule,
            }
        )

    if not gt_events:
        recall: Optional[float] = None
        recall_detail = "no ground truth timeline events (recall undefined)"
    elif section is None:
        recall = 0.0
        recall_detail = "timeline section missing"
    else:
        recall = matched_gt / len(gt_events)
        recall_detail = f"{matched_gt}/{len(gt_events)} gt events matched; {rule}"

    # -- precision over generated entries ------------------------------------
    if not gen_entries:
        precision = 0.0
        precision_detail = (
            "timeline section missing" if section is None else "no generated timeline entries"
        )
    else:
        matched_gen = sum(
            1 for gen in gen_entries if any(_timeline_pair_rule(ev, gen) for ev in gt_events)
        )
        precision = matched_gen / len(gen_entries)
        precision_detail = f"{matched_gen}/{len(gen_entries)} generated entries matched; {rule}"

    detail = {
        "rule": rule,
        "gt_events": table,
        "generated_entries": [
            {
                "text": g["text"],
                "date": g["date"].isoformat() if g["date"] else None,
                "shas": sorted(g["shas"]),
            }
            for g in gen_entries
        ],
    }
    return (
        Metric("timeline_recall", recall, detail=f"Heuristic: {recall_detail}."),
        Metric("timeline_precision", precision, detail=f"Heuristic: {precision_detail}."),
        detail,
    )


def _action_item_metric(
    pm: Postmortem, gt: dict[str, Any]
) -> tuple[Metric, dict[str, Any]]:
    section = pm.section("action_items")
    gt_items = _gt_action_items(gt)

    if not gt_items:
        value: Optional[float] = None
        text = "no ground truth action items (overlap undefined)"
        pairs: list[dict[str, Any]] = []
    elif section is None:
        value, text, pairs = 0.0, "action_items section missing", []
    else:
        gen_items = _split_action_items(section)
        pairs = []
        covered = 0
        for gt_item in gt_items:
            gt_tokens = content_tokens(gt_item)
            best_text: Optional[str] = None
            best_score = 0.0
            for gen_item in gen_items:
                score = overlap_ratio(gt_tokens, content_tokens(gen_item))
                if score > best_score:
                    best_text, best_score = gen_item, score
            is_covered = best_score >= _ACTION_ITEM_COVER_MIN
            covered += 1 if is_covered else 0
            pairs.append(
                {
                    "gt_item": gt_item,
                    "best_generated": best_text,
                    "best_score": round(best_score, 4),
                    "covered": is_covered,
                }
            )
        value = covered / len(gt_items)
        text = (
            f"{covered}/{len(gt_items)} gt action items covered: best "
            f"overlap_ratio(gt_tokens, gen_tokens) >= {_ACTION_ITEM_COVER_MIN}; "
            f"generated items = markdown list items of the body + claims"
        )
    detail = {"cover_threshold": _ACTION_ITEM_COVER_MIN, "pairs": pairs}
    return Metric("action_item_overlap", value, detail=f"Heuristic: {text}."), detail


def _root_cause_metric(pm: Postmortem, gt: dict[str, Any]) -> tuple[Metric, dict[str, Any]]:
    section = pm.section("root_cause")
    gt_rc = gt.get("root_cause") or {}
    gt_text = " ".join(str(gt_rc.get(k) or "") for k in ("statement", "quote"))

    if not gt_text.strip():
        # Ground truth carries no root-cause statement (null) — undefined,
        # same None convention as timeline_recall/action_item_overlap.
        metric = Metric(
            "root_cause_match",
            None,
            detail="Heuristic: no ground truth root cause text (undefined).",
        )
        return metric, {"jaccard": None, "overlap_ratio": None}
    if section is None:
        value, text, jac, ovr = 0.0, "root_cause section missing", 0.0, 0.0
    else:
        gen_tokens = content_tokens(_section_text(section))
        gt_tokens = content_tokens(gt_text)
        jac = jaccard(gen_tokens, gt_tokens)
        ovr = overlap_ratio(gen_tokens, gt_tokens)  # generated tokens covered by gt
        value = max(jac, ovr)
        text = (
            f"max(jaccard={jac:.3f}, overlap_ratio of generated tokens covered by "
            f"gt={ovr:.3f}) over content_tokens(root_cause body+claims) vs "
            f"content_tokens(gt.root_cause.statement + ' ' + gt.root_cause.quote)"
        )
    detail = {"jaccard": round(jac, 4), "overlap_ratio": round(ovr, 4)}
    return Metric("root_cause_match", value, detail=f"Heuristic: {text}."), detail


def _honesty_metric(pm: Postmortem) -> tuple[Metric, dict[str, Any]]:
    verdicts: dict[str, dict[str, Any]] = {}
    all_pass = True
    for sid in HONESTY_SECTIONS:
        section = pm.section(sid)
        if section is None:
            ok, reason = False, "section missing"
        elif section.badge == "red":
            ok = "no evidence" in (section.body or "").lower()
            reason = (
                "red badge and 'No evidence' stated in body"
                if ok
                else "red badge but body lacks the phrase 'No evidence'"
            )
        elif section.badge in ("green", "yellow"):
            ok = any(
                "http" in ref or ref.startswith("external:")
                for claim in section.claims
                for ref in claim.refs
            )
            reason = (
                f"{section.badge} badge with an external ref (contains 'http' or "
                f"starts 'external:') cited by a claim"
                if ok
                else f"{section.badge} badge but no claim cites an external ref "
                f"(containing 'http' or starting 'external:')"
            )
        else:
            ok, reason = False, f"unknown badge {section.badge!r} (expected red/green/yellow)"
        verdicts[sid] = {"pass": ok, "reason": reason}
        all_pass = all_pass and ok

    summary = "; ".join(
        f"{sid}: {'PASS' if v['pass'] else 'FAIL'} ({v['reason']})" for sid, v in verdicts.items()
    )
    metric = Metric(
        "honesty_check",
        all_pass,
        detail=(
            f"Heuristic: every honesty section ({', '.join(HONESTY_SECTIONS)}) must be "
            f"red + 'No evidence' in body, or green/yellow with an external ref. {summary}."
        ),
    )
    return metric, verdicts


def _claim_linkage_metric(
    pm: Postmortem, evidence: Optional[Evidence]
) -> tuple[Metric, dict[str, Any]]:
    all_claims: list[tuple[str, Claim]] = [
        (s.id, c) for s in pm.sections for c in s.claims
    ]
    if not all_claims:
        metric = Metric(
            "claim_linkage_rate",
            0.0,
            detail="Heuristic: no claims in the postmortem; rate defined as 0.0.",
        )
        return metric, {"mode": "n/a", "valid": 0, "total": 0, "invalid": []}

    if evidence is not None:
        ref_ids = evidence.ref_ids()
        mode = (
            f"strict (Evidence passed): non-empty refs AND refs ⊆ "
            f"Evidence.ref_ids() ({len(ref_ids)} valid ids)"
        )

        def linked(claim: Claim) -> bool:
            return bool(claim.refs) and set(claim.refs) <= ref_ids

    else:
        mode = "lenient (no Evidence passed): non-empty refs count as linked"

        def linked(claim: Claim) -> bool:
            return bool(claim.refs)

    valid = sum(1 for _, c in all_claims if linked(c))
    invalid = [
        {"section": sid, "claim": c.text, "refs": list(c.refs)}
        for sid, c in all_claims
        if not linked(c)
    ]
    metric = Metric(
        "claim_linkage_rate",
        valid / len(all_claims),
        detail=f"Heuristic: {mode}; {valid}/{len(all_claims)} claims linked.",
    )
    return metric, {"mode": mode, "valid": valid, "total": len(all_claims), "invalid": invalid}


def _line_agreement_metric(
    pm: Postmortem, human_text: Optional[str]
) -> tuple[Metric, dict[str, Any]]:
    if human_text is None:
        metric = Metric(
            "line_agreement",
            None,
            detail="Heuristic: human postmortem text not provided; metric undefined.",
        )
        return metric, {"human_sentences": 0, "matched": 0, "total": None}

    human_sents = [
        s for s in _sentences(human_text) if len(content_tokens(s)) >= _LINE_AGREEMENT_MIN_TOKENS
    ]
    gen_sents = _sentences(pm.markdown or "")
    if not human_sents:
        metric = Metric(
            "line_agreement",
            None,
            detail=(
                f"Heuristic: no human sentences with >= {_LINE_AGREEMENT_MIN_TOKENS} content "
                f"tokens survived splitting; metric undefined."
            ),
        )
        return metric, {"human_sentences": 0, "matched": 0, "total": None}

    matched = sum(
        1
        for h in human_sents
        if any(
            jaccard(content_tokens(h), content_tokens(g)) >= _LINE_AGREEMENT_JACCARD_MIN
            for g in gen_sents
        )
    )
    value = matched / len(human_sents)
    metric = Metric(
        "line_agreement",
        value,
        detail=(
            f"Heuristic: {matched}/{len(human_sents)} human sentences (>= "
            f"{_LINE_AGREEMENT_MIN_TOKENS} content tokens) have a pm.markdown sentence "
            f"with content-token jaccard >= {_LINE_AGREEMENT_JACCARD_MIN}."
        ),
    )
    return metric, {
        "human_sentences": len(human_sents),
        "matched": matched,
        "total": len(human_sents),
        "jaccard_threshold": _LINE_AGREEMENT_JACCARD_MIN,
    }


def _wall_clock_metric(pm: Postmortem) -> Metric:
    raw = (pm.meta or {}).get("wall_clock_seconds")
    try:
        value: Optional[float] = None if raw is None else float(raw)
    except (TypeError, ValueError):
        value = None
    note = (
        f"taken verbatim from pm.meta['wall_clock_seconds'] ({raw!r})"
        if value is not None
        else "pm.meta['wall_clock_seconds'] absent or non-numeric"
    )
    return Metric("wall_clock_seconds", value, detail=note)


# ---------------------------------------------------------------------------
# public entry point
# ---------------------------------------------------------------------------

def evaluate(
    pm: Postmortem,
    ground_truth: dict[str, Any],
    human_text: Optional[str] = None,
    evidence: Optional[Evidence] = None,
) -> EvalReport:
    """Compare *pm* against *ground_truth*; deterministic, AI-free.

    Args:
        pm: the generated postmortem (built by piece 2).
        ground_truth: parsed ground-truth dict (``ground_truth.load``).
        human_text: optional human postmortem prose (``ground_truth.human_text``)
            — enables the ``line_agreement`` metric.
        evidence: optional ``Evidence`` — switches ``claim_linkage_rate``
            to strict mode (refs must be valid evidence ids) and lets the
            introducer metrics prefer sha mentions that match a ranked
            candidate over incidental tokens (e.g. the fix sha quoted in a
            diff excerpt).

    Returns:
        An :class:`EvalReport` carrying one :class:`Metric` per name in
        ``METRIC_NAMES`` (all 10, always) plus a ``detail`` dict with the
        timeline match table, action-item best pairs, introducer sha tokens
        and per-section honesty verdicts.
    """
    gt = ground_truth or {}
    detail: dict[str, Any] = {}

    candidate_sha10s = (
        [sha10(c.sha) for c in evidence.introducer_candidates] if evidence else None
    )
    issues_only = evidence is not None and evidence.fix_commit is None
    m_top1, m_top5, detail["introducer"] = _introducer_metrics(
        pm, gt, candidate_sha10s, issues_only=issues_only
    )
    m_recall, m_precision, detail["timeline"] = _timeline_metrics(pm, gt)
    m_actions, detail["action_items"] = _action_item_metric(pm, gt)
    m_root_cause, detail["root_cause"] = _root_cause_metric(pm, gt)
    m_honesty, detail["honesty"] = _honesty_metric(pm)
    m_linkage, detail["claim_linkage"] = _claim_linkage_metric(pm, evidence)
    m_lines, detail["line_agreement"] = _line_agreement_metric(pm, human_text)
    m_wall = _wall_clock_metric(pm)

    computed = {
        m.name: m
        for m in (
            m_top1,
            m_top5,
            m_recall,
            m_precision,
            m_actions,
            m_root_cause,
            m_honesty,
            m_linkage,
            m_lines,
            m_wall,
        )
    }
    metrics = [computed[name] for name in METRIC_NAMES]  # canonical order, all 10
    return EvalReport(case=pm.case, generated_by=pm.generated_by, metrics=metrics, detail=detail)
