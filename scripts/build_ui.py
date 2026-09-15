#!/usr/bin/env python3
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. SPDX-License-Identifier:
# Apache-2.0 — see the LICENSE file at the repository root.
"""Build ui/index.html — the single-file, fully offline demo UI (piece 5).

Embeds every case found under eval-output/ (postmortem + evidence + optional
eval report) together with the matching human ground-truth markdown into one
self-contained HTML page: an interactive evidence timeline, a side-by-side
"generated vs human" postmortem view, and the deterministic metrics table.

Design constraints (see docs/UI.md):
  * stdlib only, deterministic — same inputs produce a byte-identical file
    (no timestamps, no randomness, no network);
  * works from file:// with JavaScript disabled — all content is rendered at
    build time; the inline script only adds interaction (case tabs, event
    selection, metric/doc toggles);
  * no external resources: no CDNs, no web fonts, no images; the only outbound
    URLs are GitHub links derived from case data and links that appear inside
    the human ground-truth text itself.

Usage:
    python3 scripts/build_ui.py [--cases one,two] [--out ui/index.html]
                                [--eval-dir eval-output]
                                [--ground-truth data/ground_truth]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Human-readable metric descriptions. Keep in sync with METRIC_NAMES in
# pmg/contracts.py (duplicated here so the builder stays standalone/stdlib).
METRIC_DESCRIPTIONS: dict[str, str] = {
    "introducer_top1": "Predicted introducer == ground truth (top-1 candidate)",
    "introducer_top5": "Ground-truth introducer appears in top-5 candidates",
    "timeline_recall": "Recall of ground-truth timeline events (date-window + token overlap)",
    "timeline_precision": "Precision of generated timeline events vs ground truth",
    "action_item_overlap": "Coverage of human action items by generated ones (best token match)",
    "root_cause_match": "Token-overlap score of generated root cause vs documented one (0..1)",
    "honesty_check": "impact/detection declared 'No evidence' (red) instead of invented",
    "claim_linkage_rate": "Share of claims with at least one valid evidence ref",
    "line_agreement": "Sentence-level recall over the human postmortem text",
    "wall_clock_seconds": "End-to-end generation time (human baseline: ~90 min)",
}

BADGES: dict[str, tuple[str, str]] = {
    # badge -> (emoji, short meaning)
    "green": ("\U0001f7e2", "every claim linked to evidence"),
    "yellow": ("\U0001f7e1", "grounded, some claims unreferenced"),
    "red": ("\U0001f534", "no evidence — said explicitly"),
}

HUMAN_BASELINE = "human baseline ≈ 90 min"

KIND_LABELS = {
    "commit": "commit",
    "issue": "issue",
    "issue-comment": "comment",
    "release": "release",
    "claim": "claim",
    "other": "event",
}


class BuildError(Exception):
    """Fatal, user-facing build error."""


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def gh_url(repo: str, *parts: str) -> str:
    if not repo:
        return ""
    return "/".join(["https://github.com", repo, *parts])


def fmt_wall_clock(seconds: float) -> str:
    """Human wall-clock formatting; deterministic."""
    if seconds >= 60.0:
        minutes = seconds / 60.0
        return f"{minutes:.1f} min"
    if seconds >= 1.0:
        return f"{seconds:.1f} s"
    if seconds >= 0.001:
        millis = seconds * 1000.0
        return f"{millis:.0f} ms" if millis >= 100.0 else f"{millis:.1f} ms"
    return f"{seconds * 1_000_000.0:.0f} µs"


def fmt_metric_value(name: str, value: Any) -> tuple[str, str]:
    """Format one metric value -> (display text, css class)."""
    if isinstance(value, bool):
        return ("✓ pass" if value else "✗ fail"), "val-pass" if value else "val-fail"
    if isinstance(value, (int, float)):
        if name == "wall_clock_seconds":
            return fmt_wall_clock(float(value)), "val-num"
        f = float(value)
        text = f"{f:.4f}" if 0.0 < abs(f) < 0.005 else f"{f:.2f}"
        return text, "val-num"
    if value is None or value == "":
        return "—", "val-none"
    return esc(value), "val-num"


# ---------------------------------------------------------------------------
# safe markdown-lite renderer (escape first, then a fixed tag vocabulary)
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_SOURCE_RE = re.compile(r"Source:\s*(https?://\S+)")
_CODE_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})\s*\w*\s*$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_UL_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^\s*>\s?(.*)$")
_HR_RE = re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$")


def _inline(text: str) -> str:
    """Inline markdown (code, links, images-as-text, bold, italics).
    Escapes HTML first — raw markup in the source can never reach the
    document. Order matters; code spans are stashed so their content is
    never re-processed."""
    codes: list[str] = []

    def _stash(m: re.Match[str]) -> str:
        codes.append(m.group(1))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", _stash, esc(text))
    t = re.sub(
        r"!\[([^\]]*)\]\((https?://[^)\s]+)\)",
        lambda m: f'<span class="img-ref">[image{": " + m.group(1) if m.group(1) else ""}]</span>',
        t,
    )
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        r'<a href="\2" rel="noopener">\1</a>',
        t,
    )
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*\s][^*]*?)\*(?!\*)", r"<em>\1</em>", t)
    t = t.replace("\\_", "_").replace("\\*", "*")
    t = t.replace("\\[", "[").replace("\\]", "]")
    return re.sub(
        "\x00(\\d+)\x00",
        lambda m: f"<code>{codes[int(m.group(1))]}</code>",
        t,
    )


def markdown_source_url(md: str) -> str:
    m0 = _COMMENT_RE.search(md)
    if m0:
        m1 = _SOURCE_RE.search(m0.group(0))
        if m1:
            return m1.group(1)
    return ""


def render_markdown(md: str) -> str:
    """Render a small, safe markdown subset to HTML.

    Supports: HTML comments (dropped), ATX headings, fenced code blocks,
    unordered/ordered lists, blockquotes, horizontal rules, paragraphs, and
    inline code/bold/italics/links. Everything is HTML-escaped first, so raw
    HTML in the source (e.g. <script>) can never reach the document.
    """
    md = _COMMENT_RE.sub("", md)
    out: list[str] = []
    para: list[str] = []
    list_tag: str | None = None  # "ul" | "ol" while inside a list
    list_items: list[str] = []
    quote: list[str] = []
    code: list[str] = []
    in_code = False

    def flush_para() -> None:
        nonlocal para
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>")
            para = []

    def flush_list() -> None:
        nonlocal list_tag, list_items
        if list_tag:
            out.append(f"<{list_tag}>" + "".join(f"<li>{_inline(i)}</li>" for i in list_items) + f"</{list_tag}>")
            list_tag, list_items = None, []

    def flush_quote() -> None:
        nonlocal quote
        if quote:
            out.append("<blockquote><p>" + _inline(" ".join(quote)) + "</p></blockquote>")
            quote = []

    def flush_all() -> None:
        flush_para()
        flush_list()
        flush_quote()

    for line in md.splitlines():
        if in_code:
            if _CODE_FENCE_RE.match(line):
                out.append("<pre><code>" + esc("\n".join(code)) + "</code></pre>")
                code, in_code = [], False
            else:
                code.append(line)
            continue
        if _CODE_FENCE_RE.match(line):
            flush_all()
            in_code = True
            continue
        m = _HEADING_RE.match(line)
        if m:
            flush_all()
            level = min(len(m.group(1)) + 1, 6)
            out.append(f"<h{level}>{_inline(m.group(2).strip())}</h{level}>")
            continue
        if _HR_RE.match(line):
            flush_all()
            out.append("<hr>")
            continue
        m = _UL_RE.match(line) or _OL_RE.match(line)
        if m:
            flush_para()
            flush_quote()
            tag = "ul" if _UL_RE.match(line) else "ol"
            if list_tag != tag:
                flush_list()
                list_tag = tag
            list_items.append(m.group(1).strip())
            continue
        m = _QUOTE_RE.match(line)
        if m:
            flush_para()
            flush_list()
            quote.append(m.group(1))
            continue
        if not line.strip():
            flush_all()
            continue
        para.append(line.strip())
    if in_code and code:  # unterminated fence: render what we have
        out.append("<pre><code>" + esc("\n".join(code)) + "</code></pre>")
    flush_all()
    return "".join(out)


# ---------------------------------------------------------------------------
# evidence-reference resolution (claim refs / timeline refs -> label + GitHub link)
# ---------------------------------------------------------------------------

def ref_info(ref: str, evidence: dict[str, Any]) -> dict[str, str]:
    """Resolve one evidence ref id to a label, tooltip title and GitHub URL."""
    repo = (evidence.get("case") or {}).get("repo") or ""
    fix = evidence.get("fix_commit") or {}
    cands = {c.get("short_sha"): c for c in evidence.get("introducer_candidates", [])}
    issues = {i.get("number"): i for i in evidence.get("issues", [])}

    def commit_url(sha: str) -> str:
        if not sha:
            return ""
        if fix.get("url") and sha == fix.get("sha"):
            return fix["url"]
        return gh_url(repo, "commit", sha)

    if ref == "fix":
        short = fix.get("short_sha", "")
        return {
            "label": f"fix {short}",
            "title": f"{fix.get('subject', '')} — fix commit".strip(" —"),
            "href": commit_url(fix.get("sha") or short),
        }
    if ref == "case":
        return {"label": "case", "title": "case configuration", "href": ""}
    if ref.startswith("commit:"):
        short = ref.split(":", 1)[1]
        full = fix.get("sha") if short == fix.get("short_sha") else short
        return {"label": f"commit {short}", "title": fix.get("subject", "commit"), "href": commit_url(full or short)}
    if ref.startswith("candidate:"):
        short = ref.split(":", 1)[1]
        c = cands.get(short) or {}
        methods = ", ".join(c.get("methods", [])) or "unknown method"
        return {
            "label": f"introducer? {short}",
            "title": f"{c.get('subject', '')} — SZZ-lite candidate (score {c.get('score', '?')}; {methods})",
            "href": commit_url(c.get("sha") or short),
        }
    m = re.match(r"^issue:(\d+)(?:#comment:(\d+))?$", ref)
    if m:
        n, k = m.group(1), m.group(2)
        iss = issues.get(int(n)) or {}
        href = iss.get("url") or gh_url(repo, "issues", n)
        return {"label": f"#{n}" + (f" comment {k}" if k else ""), "title": iss.get("title", f"issue #{n}"), "href": href}
    m = re.match(r"^event:(\d+)$", ref)
    if m:
        idx = int(m.group(1))
        events = evidence.get("timeline", [])
        if 0 <= idx < len(events):
            ev = events[idx]
            inner_ref = ev.get("ref", "")
            href = ""
            if inner_ref and not inner_ref.startswith("event:"):
                href = ref_info(inner_ref, evidence).get("href", "")
            return {"label": ev.get("date", ""), "title": ev.get("description", ""), "href": href}
    return {"label": ref, "title": "evidence reference", "href": ""}


def chip_label(ref: str, evidence: dict[str, Any]) -> str:
    """Compact chip text for a claim ref: fix sha, issue #, or event date."""
    info = ref_info(ref, evidence)
    if ref.startswith(("commit:", "candidate:")):
        return ref.split(":", 1)[1]
    if ref == "fix":
        return (evidence.get("fix_commit") or {}).get("short_sha", "fix")
    if ref.startswith("issue:"):
        m = re.match(r"^issue:(\d+)(?:#comment:(\d+))?$", ref)
        if m:
            return f"#{m.group(1)}" + (f"·c{m.group(2)}" if m.group(2) else "")
    return info["label"]


def chips_html(refs: list[str], evidence: dict[str, Any]) -> str:
    parts: list[str] = []
    for ref in refs:
        info = ref_info(ref, evidence)
        label = esc(chip_label(ref, evidence))
        title = esc(info["title"])
        if info["href"]:
            parts.append(
                f'<a class="chip" href="{esc(info["href"])}" rel="noopener" title="{title}">{label}</a>'
            )
        else:
            parts.append(f'<span class="chip" title="{title}">{label}</span>')
    return "".join(parts)


# ---------------------------------------------------------------------------
# case loading
# ---------------------------------------------------------------------------

def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "…[truncated]"


def load_human_docs(case_name: str, repo: str, gt_root: Path) -> list[dict[str, str]]:
    """Human ground-truth markdown for a case.

    Layouts, in priority order:
      1. per-case dir:  data/ground_truth/<case>/*.md (sorted; notes.md excluded)
      2. legacy curl files at the top level (blog.md, advisory.md) — only for
         cases whose name or repo mentions curl.
    """
    per_case = gt_root / case_name
    if per_case.is_dir():
        docs = sorted(
            p for p in per_case.glob("*.md") if p.name.lower() != "notes.md"
        )
    elif "curl" in case_name.lower() or "curl" in repo.lower():
        docs = [gt_root / n for n in ("blog.md", "advisory.md") if (gt_root / n).is_file()]
    else:
        docs = []
    out: list[dict[str, str]] = []
    for path in docs:
        text = path.read_text(encoding="utf-8")
        out.append(
            {
                "label": path.stem,
                "source": markdown_source_url(text),
                "markdown": text,
            }
        )
    return out


def load_case(case_dir: Path, gt_root: Path) -> dict[str, Any]:
    name = case_dir.name
    pm_path = case_dir / "postmortem.json"
    if not pm_path.is_file():
        raise BuildError(
            f"case '{name}': {pm_path} not found — run the pipeline (bob-postmortem "
            f"postmortem ...) before building the UI"
        )
    ev_path = case_dir / "evidence.json"
    if not ev_path.is_file():
        raise BuildError(f"case '{name}': {ev_path} not found (required for evidence refs)")
    pm = json.loads(pm_path.read_text(encoding="utf-8"))
    evidence = json.loads(ev_path.read_text(encoding="utf-8"))

    eval_data: dict[str, Any] | None = None
    er_path = case_dir / "eval_report.json"
    if er_path.is_file():
        er = json.loads(er_path.read_text(encoding="utf-8"))
        eval_data = {"case": er.get("case", name), "generated_by": er.get("generated_by", ""), "metrics": er.get("metrics", [])}

    # Slim the embedded copies: drop fields the page never shows (the full
    # files stay in eval-output/). Pure projection -> deterministic.
    pm_slim = {k: v for k, v in pm.items() if k != "markdown"}
    ev_slim = json.loads(json.dumps(evidence))  # deep copy
    fix = ev_slim.get("fix_commit") or {}
    fix.pop("diff", None)
    for issue in ev_slim.get("issues", []):
        issue["body"] = _truncate(issue.get("body", ""), 1200)
        for c in issue.get("comments", []):
            c["body"] = _truncate(c.get("body", ""), 600)

    repo = (evidence.get("case") or {}).get("repo") or ""
    return {
        "name": name,
        "repo": repo,
        "postmortem": pm_slim,
        "evidence": ev_slim,
        "eval": eval_data,
        "human": load_human_docs(name, repo, gt_root),
    }


def discover_cases(eval_dir: Path) -> list[Path]:
    if not eval_dir.is_dir():
        raise BuildError(f"eval dir not found: {eval_dir}")
    return sorted(d for d in eval_dir.iterdir() if d.is_dir() and (d / "postmortem.json").is_file())


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------

def timeline_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Track items = evidence.timeline events + any generated timeline-section
    claim that is not already covered by an event."""
    evidence = payload["evidence"]
    pm = payload["postmortem"]
    fix_short = (evidence.get("fix_commit") or {}).get("short_sha", "")
    candidates = evidence.get("introducer_candidates") or []
    top_short = candidates[0].get("short_sha", "") if candidates else ""

    tl_section = next((s for s in pm.get("sections", []) if s.get("id") == "timeline"), None)
    claims = (tl_section or {}).get("claims", [])

    items: list[dict[str, Any]] = []
    covered: set[str] = set()
    for idx, ev in enumerate(evidence.get("timeline", [])):
        ref = ev.get("ref", "")
        covered.add(ref)
        covered.add(f"event:{idx}")
        info = ref_info(ref, evidence) if ref else {"label": "", "title": "", "href": ""}
        kind = ev.get("kind", "other")
        if ref == "fix":
            title, sub = f"fix {fix_short}", (evidence.get("fix_commit") or {}).get("subject", "")
        elif ref.startswith("candidate:"):
            short = ref.split(":", 1)[1]
            c = next((c for c in candidates if c.get("short_sha") == short), {})
            title, sub = short, c.get("subject", "")
        elif ref.startswith("issue:"):
            m = re.match(r"^issue:(\d+)", ref)
            iss = next((i for i in evidence.get("issues", []) if str(i.get("number")) == (m.group(1) if m else "")), {})
            title, sub = f"#{m.group(1)}" if m else ref, iss.get("title", "")
        else:
            title = ev.get("date", "")
            sub = ev.get("description", "")
        cls = "is-fix" if ref == "fix" else ("is-top" if ref == f"candidate:{top_short}" and top_short else "")
        items.append(
            {
                "date": ev.get("date", ""),
                "kind": kind,
                "desc": ev.get("description", ""),
                "ref": ref,
                "reflabel": info["label"] or ref,
                "href": info["href"],
                "title": title,
                "sub": sub,
                "cls": cls,
            }
        )
    for claim in claims:  # generated claims with no matching evidence event
        refs = claim.get("refs", [])
        if refs and not (set(refs) & covered):
            m = re.match(r"^(\d{4}-\d{2}-\d{2})", claim.get("text", ""))
            items.append(
                {
                    "date": m.group(1) if m else "",
                    "kind": "claim",
                    "desc": claim.get("text", ""),
                    "ref": refs[0],
                    "reflabel": ref_info(refs[0], evidence)["label"],
                    "href": ref_info(refs[0], evidence)["href"],
                    "title": (m.group(1) if m else "claim"),
                    "sub": claim.get("text", "")[:80],
                    "cls": "",
                }
            )
    items.sort(key=lambda it: it["date"] or "9999")  # stable
    return items


def timeline_html(payload: dict[str, Any]) -> str:
    items = timeline_items(payload)
    evidence = payload["evidence"]
    uid = payload["name"]

    kinds_present = []
    for it in items:
        k = it["kind"]
        if k not in kinds_present:
            kinds_present.append(k)
    legend = "".join(
        f'<span class="lg"><span class="lg-dot k-{esc(k)}" aria-hidden="true"></span>{esc(KIND_LABELS.get(k, k))}</span>'
        for k in kinds_present
        if k in ("commit", "issue", "issue-comment", "release", "claim")
    )

    track: list[str] = []
    for it in items:
        classes = f"tl-item k-{esc(it['kind'])}"
        if it["cls"]:
            classes += f" {it['cls']}"
        tag = ""
        if it["cls"] == "is-fix":
            tag = '<span class="tl-tag">fix</span>'
        elif it["cls"] == "is-top":
            tag = '<span class="tl-tag">top introducer candidate</span>'
        track.append(
            f'<button type="button" class="{classes}"'
            f' data-date="{esc(it["date"])}" data-kind="{esc(KIND_LABELS.get(it["kind"], it["kind"]))}"'
            f' data-desc="{esc(it["desc"])}" data-reflabel="{esc(it["reflabel"])}"'
            f' data-href="{esc(it["href"])}">'
            f'<span class="tl-date">{esc(it["date"])}</span>'
            f'<span class="tl-title">{esc(it["title"])}</span>'
            f'<span class="tl-sub">{esc(it["sub"])}</span>{tag}</button>'
        )

    first = items[0] if items else None
    detail = detail_panel_html(first) if first else '<p class="hint">no timeline events in evidence</p>'
    return (
        '<section class="panel timeline-panel" aria-label="Evidence timeline">'
        f'<div class="sec-head"><h2>Timeline</h2>'
        f'<span class="hint">reconstructed from repository data — click or hover an event</span>'
        f'<span class="legend">{legend}</span></div>'
        f'<ol class="tl-track" data-track="{esc(uid)}">{"".join(track)}</ol>'
        f'<div class="tl-detail" data-detail="{esc(uid)}">{detail}</div>'
        "</section>"
    )


def detail_panel_html(item: dict[str, Any]) -> str:
    ref_html = (
        f'<a href="{esc(item["href"])}" rel="noopener">{esc(item["reflabel"])}</a>'
        if item.get("href")
        else f"<span>{esc(item['reflabel'])}</span>"
    )
    return (
        f'<p class="d-date">{esc(item["date"])} · {esc(KIND_LABELS.get(item["kind"], item["kind"]))}</p>'
        f'<p class="d-desc">{esc(item["desc"])}</p>'
        f'<p class="d-ref">evidence: {ref_html}</p>'
    )


def section_html(section: dict[str, Any], evidence: dict[str, Any]) -> str:
    badge = section.get("badge", "other")
    emoji, meaning = BADGES.get(badge, ("⚪", badge))
    claims = section.get("claims", [])
    claims_html = ""
    if claims:
        rows = []
        for c in claims:
            chips = chips_html(c.get("refs", []), evidence)
            rows.append(
                f'<li><span class="claim-text">{esc(c.get("text", ""))}</span>'
                f'<span class="chips">{chips}</span></li>'
            )
        claims_html = f'<ul class="claims">{"".join(rows)}</ul>'
    body = render_markdown(section.get("body", ""))
    return (
        f'<section class="pm-section b-{esc(badge)}" data-section="{esc(section.get("id", ""))}">'
        f'<h3><span class="badge b-{esc(badge)}">{emoji}</span> {esc(section.get("title", section.get("id", "")))}'
        f'<span class="badge-note">{esc(meaning)}</span></h3>'
        f'<div class="pm-body">{body}</div>{claims_html}</section>'
    )


def metrics_html(payload: dict[str, Any]) -> str:
    eval_data = payload.get("eval")
    if not eval_data:
        return ""
    rows = []
    for m in eval_data.get("metrics", []):
        name = m.get("name", "")
        value, vcls = fmt_metric_value(name, m.get("value"))
        desc = METRIC_DESCRIPTIONS.get(name, "")
        detail = esc(m.get("detail", ""))
        rows.append(
            f'<tr data-metric="{esc(name)}"><td class="mono">{esc(name)}</td>'
            f'<td class="mdesc">{esc(desc)}</td>'
            f'<td class="{vcls}" title="{detail}">{value}</td></tr>'
        )
    return (
        f'<section class="panel metrics-panel" id="metrics-{esc(payload["name"])}" hidden>'
        f'<div class="sec-head"><h2>Evaluation vs human ground truth</h2>'
        f'<span class="hint">deterministic harness — no AI in scoring</span></div>'
        f'<div class="table-wrap"><table class="mtable">'
        f"<thead><tr><th>metric</th><th>description</th><th>value</th></tr></thead>"
        f'<tbody>{"".join(rows)}</tbody></table></div></section>'
    )


def human_docs_html(payload: dict[str, Any]) -> str:
    docs = payload.get("human") or []
    if not docs:
        return '<p class="hint">No human baseline documents found for this case.</p>'
    case = payload["name"]
    tabs, panels = [], []
    for i, doc in enumerate(docs):
        did = f"{case}--{esc(doc['label'])}"
        src = (
            f'<p class="doc-src">cached from <a href="{esc(doc["source"])}" rel="noopener">{esc(doc["source"])}</a></p>'
            if doc.get("source")
            else ""
        )
        hidden = " hidden" if i > 0 else ""
        aria = ' aria-pressed="true"' if i == 0 else ""
        tabs.append(
            f'<button type="button" class="tab small" data-doc-tab="{did}" data-doc-scope="{esc(case)}"{aria}>{esc(doc["label"])}</button>'
        )
        panels.append(
            f'<div class="doc" data-doc-panel="{did}"{hidden}>{src}{render_markdown(doc["markdown"])}</div>'
        )
    tabs_html = f'<div class="doc-tabs">{"".join(tabs)}</div>' if len(docs) > 1 else ""
    return tabs_html + "".join(panels)


def case_html(payload: dict[str, Any], first: bool) -> str:
    pm = payload["postmortem"]
    evidence = payload["evidence"]
    name = payload["name"]

    meta_bits = [f'<span class="pill">generator: {esc(pm.get("generated_by", "?"))}</span>']
    wall = (pm.get("meta") or {}).get("wall_clock_seconds")
    if isinstance(wall, (int, float)):
        meta_bits.append(
            f'<span class="pill">generated in {esc(fmt_wall_clock(float(wall)))}</span>'
            f'<span class="pill accent">{esc(HUMAN_BASELINE)}</span>'
        )
    if payload.get("eval"):
        rate = next((m.get("value") for m in payload["eval"].get("metrics", []) if m.get("name") == "claim_linkage_rate"), None)
        if isinstance(rate, (int, float)) and not isinstance(rate, bool):
            meta_bits.append(f'<span class="pill">claim linkage {rate * 100:.0f}%</span>')

    sections = "".join(section_html(s, evidence) for s in pm.get("sections", []))
    metrics = metrics_html(payload)
    metrics_btn = (
        f'<button type="button" class="ghost-btn" data-toggle-metrics="metrics-{esc(name)}">'
        "▾ evaluation metrics</button>"
        if metrics
        else '<span class="hint">no eval report for this case</span>'
    )

    hidden = "" if first else " hidden"
    return (
        f'<article class="case" data-case-article="{esc(name)}" id="case-{esc(name)}"{hidden}>'
        f'<header class="case-head">'
        f'<p class="kicker">case</p><h1>{esc(name)}</h1>'
        f'<p class="pm-title">{esc(pm.get("title", ""))}</p>'
        f'<p class="meta">{"".join(meta_bits)}</p></header>'
        f"{timeline_html(payload)}"
        f'<section class="panel compare-panel" aria-label="Generated versus human postmortem">'
        f'<div class="compare-head">'
        f'<div class="sec-head"><h2>Side by side</h2><span class="hint">generated from repository evidence vs the human-written baseline</span></div>'
        f"{metrics_btn}</div>"
        f'<div class="compare">'
        f'<div class="col col-generated"><h3 class="col-h">Generated <span class="col-sub">{esc(pm.get("generated_by", ""))}</span></h3>{sections}</div>'
        f'<div class="col col-human"><h3 class="col-h">Human baseline <span class="col-sub">{esc(HUMAN_BASELINE)}</span></h3>{human_docs_html(payload)}</div>'
        f"</div></section>"
        f"{metrics}"
        "</article>"
    )


# ---------------------------------------------------------------------------
# page shell
# ---------------------------------------------------------------------------

_CSS = """
:root{color-scheme:light dark;
--bg:#f6f6f4;--surface:#ffffff;--surface2:#f0efec;--ink:#202428;--muted:#5c6670;
--border:#dddad2;--accent:#4338ca;--accent-ink:#ffffff;
--green:#15803d;--amber:#b45309;--red:#b91c1c;
--commit:#4338ca;--issue:#7c3aed;--comment:#0e7490;--release:#a16207;--otherk:#6b7280;
--code-bg:#f0efec;--shadow:0 1px 3px rgba(0,0,0,.07)}
@media(prefers-color-scheme:dark){:root:not([data-theme="light"]){
--bg:#101318;--surface:#171b21;--surface2:#1e242c;--ink:#e8eaed;--muted:#98a1ab;
--border:#2a303a;--accent:#8b95f6;--accent-ink:#101318;
--green:#4ade80;--amber:#fbbf24;--red:#f87171;
--commit:#a5b4fc;--issue:#c4b5fd;--comment:#67e8f9;--release:#fcd34d;--otherk:#9ca3af;
--code-bg:#1b2027;--shadow:none}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.62 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.mono,.chip,.tl-title,td.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"Liberation Mono",monospace}
a{color:var(--accent)}a:hover{text-decoration:underline}
.top{position:sticky;top:0;z-index:20;display:flex;flex-wrap:wrap;gap:.5rem 1.5rem;align-items:baseline;
justify-content:space-between;padding:.8rem 1.25rem;background:var(--surface);
border-bottom:1px solid var(--border)}
.brand{font-weight:650;letter-spacing:.01em}
.brand .tagline{font-weight:400;color:var(--muted);margin-left:.6rem;font-size:.86em}
.cases{display:flex;gap:.4rem;flex-wrap:wrap}
.tab{appearance:none;border:1px solid var(--border);background:var(--surface);color:var(--ink);
border-radius:999px;padding:.28rem .85rem;font:inherit;font-size:.88em;cursor:pointer}
.tab:hover{border-color:var(--accent)}
.tab[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
.tab.small{font-size:.82em;padding:.18rem .7rem}
main{max-width:1180px;margin:0 auto;padding:1.5rem 1.25rem 3rem}
.case>.case-head{margin:.5rem 0 1.25rem}
.kicker{text-transform:uppercase;letter-spacing:.14em;font-size:.72em;color:var(--muted);margin:0 0 .15rem}
h1{font-size:1.65rem;line-height:1.25;margin:0 0 .3rem;letter-spacing:-.01em}
.pm-title{margin:.1rem 0 .8rem;color:var(--muted);font-size:1.02rem;max-width:60ch}
.meta{display:flex;flex-wrap:wrap;gap:.45rem;margin:.4rem 0 0}
.pill{border:1px solid var(--border);background:var(--surface);border-radius:999px;
padding:.14rem .7rem;font-size:.8em;color:var(--muted)}
.pill.accent{border-color:var(--amber);color:var(--amber)}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:10px;
padding:1.1rem 1.25rem 1.25rem;margin:0 0 1.4rem;box-shadow:var(--shadow)}
.sec-head{display:flex;flex-wrap:wrap;align-items:baseline;gap:.4rem 1rem;margin:0 0 .9rem}
h2{font-size:1.02rem;margin:0;text-transform:uppercase;letter-spacing:.09em}
.hint{color:var(--muted);font-size:.82em}
.legend{margin-left:auto;display:flex;gap:.7rem;flex-wrap:wrap;font-size:.78em;color:var(--muted)}
.lg{display:inline-flex;align-items:center;gap:.3rem}
.lg-dot{width:.62em;height:.62em;border-radius:50%;display:inline-block;background:var(--otherk)}
.k-commit{background:var(--commit)}.k-issue{background:var(--issue)}
.k-issue-comment{background:var(--comment)}.k-release{background:var(--release)}
/* timeline track */
.tl-track{display:flex;gap:0;list-style:none;margin:0;padding:0 0 .4rem;overflow-x:auto}
.tl-item{appearance:none;position:relative;flex:1 0 185px;max-width:260px;text-align:left;
background:var(--surface2);border:1px solid var(--border);border-top:2px solid var(--border);
border-radius:0 0 8px 8px;padding:.6rem .75rem .7rem;margin-right:.6rem;font:inherit;color:var(--ink);
cursor:pointer;display:flex;flex-direction:column;gap:.15rem}
.tl-item:hover,.tl-item:focus-visible{border-color:var(--accent);border-top-color:var(--accent)}
.tl-item.sel{outline:2px solid var(--accent);outline-offset:1px}
.tl-item::before{content:"";position:absolute;top:-7px;left:.8rem;width:10px;height:10px;border-radius:50%;
background:var(--otherk);border:2px solid var(--surface)}
.tl-item.k-commit::before{background:var(--commit)}
.tl-item.k-issue::before{background:var(--issue)}
.tl-item.k-issue-comment::before{background:var(--comment)}
.tl-item.k-release::before{background:var(--release)}
.tl-item.is-fix::before{background:var(--green)}
.tl-item.is-top::before{background:var(--red)}
.tl-date{font-size:.78em;color:var(--muted)}
.tl-title{font-weight:600;font-size:.92em;word-break:break-all}
.tl-sub{font-size:.8em;color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tl-tag{font-size:.68em;text-transform:uppercase;letter-spacing:.08em;color:var(--green);
border:1px solid currentColor;border-radius:4px;padding:0 .35rem;width:fit-content;margin-top:.2rem}
.is-top .tl-tag{color:var(--red)}
.tl-detail{border:1px dashed var(--border);border-radius:8px;background:var(--surface2);
padding:.7rem .95rem;max-width:74ch}
.d-date{margin:0 0 .25rem;font-weight:650;font-size:.9em}
.d-desc{margin:0 0 .35rem}
.d-ref{margin:0;font-size:.85em;color:var(--muted)}
/* side-by-side */
.compare-head{display:flex;flex-wrap:wrap;gap:.6rem 1rem;align-items:center;justify-content:space-between}
.ghost-btn{appearance:none;font:inherit;font-size:.85em;color:var(--accent);background:none;
border:1px solid var(--border);border-radius:8px;padding:.3rem .8rem;cursor:pointer}
.ghost-btn:hover{border-color:var(--accent)}
.compare{display:grid;grid-template-columns:1fr 1fr;gap:0;margin-top:1rem}
.col{padding:0 1.25rem;min-width:0}
.col:first-child{padding-left:0;border-right:1px solid var(--border)}
.col:last-child{padding-right:0}
.col-h{position:sticky;top:3.4rem;background:var(--surface);margin:0 0 .6rem;padding:.35rem 0;
font-size:.95rem;border-bottom:2px solid var(--border);z-index:5}
.col-sub{font-weight:400;color:var(--muted);font-size:.8em;margin-left:.4rem}
.pm-section{border-left:3px solid var(--border);padding:.1rem 0 .1rem .9rem;margin:0 0 1.3rem}
.pm-section.b-green{border-left-color:var(--green)}
.pm-section.b-yellow{border-left-color:var(--amber)}
.pm-section.b-red{border-left-color:var(--red)}
.pm-section h3{margin:.1rem 0 .5rem;font-size:1rem;display:flex;flex-wrap:wrap;align-items:baseline;gap:.45rem}
.badge-note{color:var(--muted);font-weight:400;font-size:.78em}
.b-green .badge-note{color:var(--green)}.b-yellow .badge-note{color:var(--amber)}.b-red .badge-note{color:var(--red)}
.pm-body p{margin:.45rem 0}
.pm-body pre{background:var(--code-bg);border:1px solid var(--border);border-radius:8px;
padding:.7rem .85rem;overflow-x:auto;font-size:.82em}
.pm-body code{background:var(--code-bg);border-radius:4px;padding:.06em .3em;font-size:.88em}
.pm-body pre code{background:none;padding:0}
.pm-body blockquote{margin:.5rem 0;padding:.1rem .9rem;border-left:3px solid var(--border);color:var(--muted)}
.claims{list-style:none;margin:.7rem 0 0;padding:0;border-top:1px dashed var(--border)}
.claims li{padding:.5rem .1rem;border-bottom:1px dashed var(--border);display:flex;flex-wrap:wrap;gap:.3rem .6rem;align-items:baseline}
.claim-text{flex:1 1 34ch;font-size:.92em}
.chips{display:flex;flex-wrap:wrap;gap:.3rem}
.chip{font-size:.72em;border:1px solid var(--border);border-radius:999px;padding:.1rem .55rem;
background:var(--surface2);color:var(--muted);text-decoration:none;white-space:nowrap}
a.chip:hover{border-color:var(--accent);color:var(--accent);text-decoration:none}
/* human column */
.doc-tabs{display:flex;gap:.4rem;margin:0 0 .8rem}
.doc-src{font-size:.78em;color:var(--muted);margin:.1rem 0 .6rem}
.doc h2{font-size:1.18rem;letter-spacing:0;text-transform:none;margin:.9rem 0 .4rem}
.doc h3{font-size:1.02rem;margin:.8rem 0 .35rem}
.doc h4,.doc h5,.doc h6{font-size:.95rem;margin:.7rem 0 .3rem}
.doc p{margin:.5rem 0}
.doc ul,.doc ol{margin:.5rem 0;padding-left:1.4rem}
.doc pre{background:var(--code-bg);border:1px solid var(--border);border-radius:8px;
padding:.7rem .85rem;overflow-x:auto;font-size:.82em}
.doc code{background:var(--code-bg);border-radius:4px;padding:.06em .3em;font-size:.88em}
.doc pre code{background:none;padding:0}
.doc blockquote{margin:.5rem 0;padding:.1rem .9rem;border-left:3px solid var(--border);color:var(--muted)}
.img-ref{color:var(--muted);font-size:.9em}
/* metrics */
.table-wrap{overflow-x:auto}
.mtable{border-collapse:collapse;width:100%;font-size:.9em}
.mtable th,.mtable td{text-align:left;padding:.45rem .7rem;border-bottom:1px solid var(--border);vertical-align:top}
.mtable th{font-size:.78em;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)}
.mdesc{color:var(--muted)}
td.val-pass{color:var(--green);font-weight:650}
td.val-fail{color:var(--red);font-weight:650}
footer{border-top:1px solid var(--border);color:var(--muted);font-size:.82em;
padding:1.1rem 1.25rem 2rem;max-width:1180px;margin:0 auto}
footer a{color:var(--muted)}
/* responsive: narrow -> stacked columns, vertical timeline */
@media(max-width:900px){
.compare{grid-template-columns:1fr}
.col{padding:0;border:0 !important}
.col+.col{margin-top:1.6rem;border-top:1px solid var(--border);padding-top:1rem}
.tl-track{flex-direction:column;overflow:visible}
.tl-item{max-width:none;flex:auto;margin:0 0 .5rem;border:1px solid var(--border);
border-left:3px solid var(--border);border-top:1px solid var(--border);border-radius:8px}
.tl-item::before{top:calc(50% - 6px);left:-8px}
.col-h{position:static}
}
@media print{.top{position:static}.panel{box-shadow:none;break-inside:avoid}}
"""

_JS = """
(function () {
  "use strict";
  // Case switcher
  var tabs = document.querySelectorAll("[data-case-tab]");
  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      var name = tab.getAttribute("data-case-tab");
      tabs.forEach(function (t) {
        t.setAttribute("aria-pressed", t === tab ? "true" : "false");
      });
      document.querySelectorAll("[data-case-article]").forEach(function (a) {
        a.hidden = a.getAttribute("data-case-article") !== name;
      });
    });
  });
  // Timeline: click / hover / focus an event -> detail panel (DOM built with
  // textContent only; data comes from data-* attributes rendered at build time)
  document.querySelectorAll(".tl-track").forEach(function (track) {
    var detail = track.parentElement.querySelector(".tl-detail");
    if (!detail) return;
    var items = Array.prototype.slice.call(track.querySelectorAll(".tl-item"));
    function select(btn) {
      items.forEach(function (b) { b.classList.toggle("sel", b === btn); });
      detail.textContent = "";
      var head = document.createElement("p"); head.className = "d-date";
      head.textContent = btn.dataset.date + " · " + btn.dataset.kind;
      var desc = document.createElement("p"); desc.className = "d-desc";
      desc.textContent = btn.dataset.desc;
      var ref = document.createElement("p"); ref.className = "d-ref";
      ref.appendChild(document.createTextNode("evidence: "));
      if (btn.dataset.href) {
        var a = document.createElement("a");
        a.href = btn.dataset.href; a.rel = "noopener"; a.textContent = btn.dataset.reflabel;
        ref.appendChild(a);
      } else {
        var s = document.createElement("span"); s.textContent = btn.dataset.reflabel;
        ref.appendChild(s);
      }
      detail.append(head, desc, ref);
    }
    var first = items[0];
    if (first) first.classList.add("sel");
    items.forEach(function (btn) {
      btn.addEventListener("click", function () { select(btn); });
      btn.addEventListener("mouseenter", function () { select(btn); });
      btn.addEventListener("focus", function () { select(btn); });
    });
  });
  // Metrics toggle
  document.querySelectorAll("[data-toggle-metrics]").forEach(function (btn) {
    var target = document.getElementById(btn.getAttribute("data-toggle-metrics"));
    if (!target) return;
    btn.addEventListener("click", function () {
      target.hidden = !target.hidden;
      btn.textContent = (target.hidden ? "▾ " : "▸ ") + "evaluation metrics";
    });
  });
  // Human document tabs (scoped per case)
  document.querySelectorAll("[data-doc-tab]").forEach(function (tab) {
    tab.addEventListener("click", function () {
      var scope = tab.getAttribute("data-doc-scope");
      var root = document.querySelector('[data-case-article="' + scope + '"]');
      if (!root) return;
      root.querySelectorAll("[data-doc-tab]").forEach(function (t) {
        t.setAttribute("aria-pressed", t === tab ? "true" : "false");
      });
      root.querySelectorAll("[data-doc-panel]").forEach(function (p) { p.hidden = true; });
      var panel = root.querySelector('[data-doc-panel="' + tab.getAttribute("data-doc-tab") + '"]');
      if (panel) panel.hidden = false;
    });
  });
})();
"""


def _embed_json(obj: Any) -> str:
    blob = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    return blob.replace("<", "\\u003c")  # keep </script> out of the document


def page_html(payloads: list[dict[str, Any]]) -> str:
    names = [p["name"] for p in payloads]
    title = "postmortem-generator"
    if len(names) == 1:
        title += f" — {names[0]}"
    elif names:
        title += f" — {len(names)} cases"

    tab_parts: list[str] = []
    for i, n in enumerate(names):
        aria = ' aria-pressed="true"' if i == 0 else ""
        tab_parts.append(
            f'<button type="button" class="tab" data-case-tab="{esc(n)}"{aria}>{esc(n)}</button>'
        )
    tabs = "".join(tab_parts)
    tabs_nav = f'<nav class="cases" aria-label="Cases">{tabs}</nav>' if len(names) > 1 else ""

    data_scripts = "\n".join(
        f'<script type="application/json" id="case-{esc(p["name"])}">{_embed_json(p)}</script>'
        for p in payloads
    )
    articles = "\n".join(case_html(p, i == 0) for i, p in enumerate(payloads))

    return (
        "<!DOCTYPE html>\n"
        "<!-- Built by scripts/build_ui.py (postmortem-generator). Deterministic, "
        "offline, single-file. Licensed under the Apache License, Version 2.0 "
        "(see the LICENSE file in the repository). -->\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{esc(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n"
        f'<header class="top"><div class="brand">postmortem-generator'
        '<span class="tagline">from fix commit to postmortem · repository evidence only</span></div>'
        f"{tabs_nav}</header>\n"
        f"<main>\n{articles}\n</main>\n"
        "<footer>postmortem-generator · Apache-2.0 · "
        "this page is one self-contained HTML file — offline, no external resources "
        "(rebuild: <span class=\"mono\">python3 scripts/build_ui.py</span>)</footer>\n"
        f"{data_scripts}\n<script>{_JS}</script>\n</body>\n</html>\n"
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build(cases: list[Path], gt_root: Path, out_path: Path) -> int:
    payloads = []
    for case_dir in cases:
        payload = load_case(case_dir, gt_root)
        if not payload["human"]:
            print(
                f"note: no human ground-truth markdown found for case '{payload['name']}'",
                file=sys.stderr,
            )
        payloads.append(payload)
    html_text = page_html(payloads)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html_text, encoding="utf-8")
    print(
        f"built {out_path.relative_to(PROJECT_ROOT) if out_path.is_relative_to(PROJECT_ROOT) else out_path} "
        f"({len(payloads)} case(s), {len(html_text.encode('utf-8'))} bytes)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the single-file offline demo UI (ui/index.html)."
    )
    parser.add_argument("--cases", default="", help="comma-separated case names under --eval-dir (default: all found)")
    parser.add_argument("--out", default=str(PROJECT_ROOT / "ui" / "index.html"), help="output HTML path")
    parser.add_argument("--eval-dir", default=str(PROJECT_ROOT / "eval-output"), help="directory of per-case outputs")
    parser.add_argument("--ground-truth", default=str(PROJECT_ROOT / "data" / "ground_truth"),
                        help="ground-truth root (per-case subdirs or legacy top-level files)")
    args = parser.parse_args(argv)

    eval_dir = Path(args.eval_dir)
    gt_root = Path(args.ground_truth)
    out_path = Path(args.out)

    try:
        if args.cases.strip():
            case_dirs: list[Path] = []
            seen: set[str] = set()
            for raw in args.cases.split(","):
                name = raw.strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                case_dir = eval_dir / name
                if not case_dir.is_dir():
                    raise BuildError(f"unknown case '{name}': no directory {case_dir}")
                if not (case_dir / "postmortem.json").is_file():
                    raise BuildError(
                        f"case '{name}' lacks postmortem.json — the UI embeds generated postmortems; "
                        f"run the pipeline first (bob-postmortem postmortem ...)"
                    )
                case_dirs.append(case_dir)
            if not case_dirs:
                raise BuildError("no case names given")
        else:
            case_dirs = discover_cases(eval_dir)
            if not case_dirs:
                raise BuildError(f"no cases with postmortem.json found under {eval_dir}")
        return build(case_dirs, gt_root, out_path)
    except BuildError as exc:
        print(f"build_ui failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
