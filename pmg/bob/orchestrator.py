"""Piece 2 — postmortem orchestration: IBM Bob agents + deterministic fallback.

Two orchestrators share one output contract (``contracts.Postmortem``):

* :class:`BobOrchestrator` — drives the real ``bob`` CLI (IBM Bob 2.0). The
  three analyst roles run as PARALLEL ``bob run --chat-mode=<slug>
  --format json`` subprocesses (Bob's built-in subagents are explore/general
  only, so per-role personas are custom chat modes launched as separate
  processes — docs/research/ibm-bob-notes.md sections 2-3), then the
  sre-synthesizer merges their findings into the SRE template.
* :class:`DeterministicOrchestrator` — the offline, no-AI floor: fills all
  8 sections from the ``Evidence`` alone and obeys the honesty rule
  (impact/detection are red 'No evidence' — repository data contains no
  user impact or detection story).

``generate_postmortem(evidence, mode)`` picks one; ``mode="auto"`` tries Bob
and falls back to deterministic with a recorded reason.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from pmg.contracts import (
    BADGES,
    Claim,
    Evidence,
    NO_EVIDENCE_PHRASE,
    Postmortem,
    SECTION_IDS,
    Section,
)
from pmg.bob.linkage import validate_linkage
from pmg.bob.roles import (
    ANALYST_ROLE_IDS,
    SYNTH_ROLE_ID,
    RoleDef,
    ROLES,
    build_role_prompt,
)
from pmg.bob.template import SECTION_TITLES, render_markdown

GENERATOR_DETERMINISTIC = "deterministic-fallback"
GENERATOR_BOB = "ibm-bob-agents"

# Per-role prompt is passed on argv; give each subprocess 15 minutes.
BOB_TIMEOUT_SECONDS = 900

_NO_IMPACT_BODY = (
    f"{NO_EVIDENCE_PHRASE} in repository data — user impact requires "
    "incident telemetry, alerts or user reports, none of which are captured "
    "in git history or the linked issue thread. Any number of affected "
    "users, severity rating or outage duration stated here would be "
    "invention, so this section makes no claims."
)
_NO_DETECTION_BODY = (
    f"{NO_EVIDENCE_PHRASE} in repository data — how this bug was found "
    "(who reported it, through which channel, and when) is not recorded in "
    "the git history or the linked issue thread. A detection story would "
    "have to come from the security advisory or disclosure report, which "
    "are outside the collected repository evidence."
)


class BobUnavailableError(RuntimeError):
    """Raised when the real Bob CLI cannot be used; ``reason`` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ---------------------------------------------------------------------------
# small deterministic helpers
# ---------------------------------------------------------------------------


def _date_part(iso: str) -> str:
    """Date (YYYY-MM-DD) part of an ISO-8601 timestamp."""
    return (iso or "")[:10]


def _parse_day(iso: str) -> date | None:
    try:
        return date.fromisoformat(_date_part(iso))
    except ValueError:
        return None


def _diff_key_lines(diff: str, max_lines: int = 15) -> list[str]:
    """Removed/added lines of a unified diff, capped at *max_lines*."""
    lines = [
        ln
        for ln in (diff or "").splitlines()
        if (ln.startswith("+") and not ln.startswith("+++"))
        or (ln.startswith("-") and not ln.startswith("---"))
    ]
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["... [diff trimmed]"]
    return lines


def _test_files(files: list[str]) -> list[str]:
    """Files of the fix commit that look like tests."""
    return [
        f
        for f in files
        if f.startswith("test") or "/test" in f or f.startswith("tests")
    ]


def _red_no_evidence(section_id: str) -> Section:
    """Red 'No evidence' stub for *section_id* (honesty rule)."""
    if section_id == "impact":
        body = _NO_IMPACT_BODY
    elif section_id == "detection":
        body = _NO_DETECTION_BODY
    else:
        body = (
            f"{NO_EVIDENCE_PHRASE} for this section in the collected "
            "repository data."
        )
    return Section(
        id=section_id,
        title=SECTION_TITLES[section_id],
        badge="red",
        body=body,
        claims=[],
    )


# ---------------------------------------------------------------------------
# deterministic (no-AI) orchestrator
# ---------------------------------------------------------------------------


class DeterministicOrchestrator:
    """Fill the SRE template from ``Evidence`` only — no AI, no invention.

    Sections the repository cannot ground (impact, detection) come out red
    with a 'No evidence' body; every claim carries refs drawn from
    ``evidence.ref_ids()`` so ``validate_linkage`` rates 1.0.
    """

    def __init__(self, evidence: Evidence) -> None:
        self.evidence = evidence

    # -- section builders ---------------------------------------------------

    def _top_candidate(self):
        """Highest-score introducer candidate, or None."""
        cands = self.evidence.introducer_candidates
        if not cands:
            return None
        return max(cands, key=lambda c: c.score)

    def _summary(self) -> Section:
        ev = self.evidence
        fix = ev.fix_commit
        cand = self._top_candidate()
        claims = [
            Claim(
                text=(
                    f"{ev.case.repo}: fixed by commit {fix.short_sha} "
                    f"(\"{fix.subject}\") authored by {fix.author} on "
                    f"{_date_part(fix.author_date)}."
                ),
                refs=["fix", f"commit:{fix.short_sha}"],
            )
        ]
        if cand is not None:
            claims.append(
                Claim(
                    text=(
                        f"Top introducer candidate by combined SZZ-lite "
                        f"score: {cand.short_sha} (\"{cand.subject}\", "
                        f"{_date_part(cand.author_date)}, score "
                        f"{cand.score:.2f})."
                    ),
                    refs=[f"candidate:{cand.short_sha}", "fix"],
                )
            )
        body = (
            f"Case **{ev.case.name}** in `{ev.case.repo}`: the fix commit "
            f"`{fix.short_sha}` (\"{fix.subject}\") was authored by "
            f"{fix.author} on {_date_part(fix.author_date)}."
        )
        if cand is not None:
            body += (
                f" The strongest introducer candidate is `{cand.short_sha}` "
                f"({_date_part(cand.author_date)}, combined score "
                f"{cand.score:.2f}) — see Root Cause."
            )
        body += (
            " Impact and detection are not derivable from repository data "
            "and are marked 'No evidence' in their sections."
        )
        return Section(
            id="summary", title=SECTION_TITLES["summary"], badge="green",
            body=body, claims=claims,
        )

    def _impact(self) -> Section:
        return _red_no_evidence("impact")

    def _timeline(self) -> Section:
        ev = self.evidence
        valid_ids = ev.ref_ids()
        events = sorted(
            enumerate(ev.timeline), key=lambda pair: (pair[1].date, pair[0])
        )
        claims: list[Claim] = []
        body_lines: list[str] = []
        for idx, event in events:
            refs = [f"event:{idx}"]
            if event.ref in valid_ids and event.ref not in refs:
                refs.append(event.ref)
            claims.append(
                Claim(
                    text=f"{event.date} — {event.description}",
                    refs=refs,
                )
            )
            body_lines.append(
                f"- **{event.date}** — {event.description} *(kind: "
                f"{event.kind}, ref: {', '.join(refs)})*"
            )
        body = (
            "\n".join(body_lines)
            if body_lines
            else f"{NO_EVIDENCE_PHRASE}: no dated events in the collected evidence."
        )
        badge = "green" if claims else "red"
        return Section(
            id="timeline", title=SECTION_TITLES["timeline"], badge=badge,
            body=body, claims=claims,
        )

    def _root_cause(self) -> Section:
        ev = self.evidence
        fix = ev.fix_commit
        cand = self._top_candidate()
        claims: list[Claim] = [
            Claim(
                text=(
                    f"The fix commit {fix.short_sha} changes "
                    f"{len(fix.files)} file(s): {', '.join(fix.files)}."
                ),
                refs=["fix", f"commit:{fix.short_sha}"],
            )
        ]
        diff_lines = _diff_key_lines(fix.diff)
        diff_block = (
            "\n".join(diff_lines)
            if diff_lines
            else "(no diff content in the collected evidence)"
        )
        cand_part = ""
        if cand is not None:
            methods = ", ".join(cand.methods)
            claims.append(
                Claim(
                    text=(
                        f"The evidence is consistent with the bug being "
                        f"introduced in {cand.short_sha} "
                        f"({_date_part(cand.author_date)}); candidate score "
                        f"{cand.score:.2f} via {methods}."
                    ),
                    refs=[f"candidate:{cand.short_sha}", f"commit:{fix.short_sha}"],
                )
            )
            cand_part = (
                f"\n\nThe introducer candidate with the highest combined "
                f"score is `{cand.short_sha}` (\"{cand.subject}\", "
                f"{_date_part(cand.author_date)}, score {cand.score:.2f}, "
                f"methods: {methods}). **The evidence is consistent with "
                f"the bug being introduced in {cand.short_sha} "
                f"({_date_part(cand.author_date)})** — this is candidate "
                f"evidence (SZZ-lite linkage), not proven causality."
            )
        else:
            cand_part = (
                "\n\nNo introducer candidate is present in the collected "
                f"evidence — {NO_EVIDENCE_PHRASE.lower()} for who "
                "introduced the bug."
            )
        body = (
            f"The fix diff shows what was fixed — key removed/added lines "
            f"of `{fix.short_sha}`:\n\n```\n{diff_block}\n```{cand_part}"
        )
        badge = "yellow"  # interpretation over grounded facts
        return Section(
            id="root_cause", title=SECTION_TITLES["root_cause"], badge=badge,
            body=body, claims=claims,
        )

    def _detection(self) -> Section:
        return _red_no_evidence("detection")

    def _resolution(self) -> Section:
        fix = self.evidence.fix_commit
        claims = [
            Claim(
                text=(
                    f"Fix commit {fix.short_sha}: \"{fix.subject}\" "
                    f"(authored { _date_part(fix.author_date)} by "
                    f"{fix.author})."
                ),
                refs=["fix", f"commit:{fix.short_sha}"],
            ),
            Claim(
                text=(
                    f"Files changed in the fix: {', '.join(fix.files)}."
                ),
                refs=[f"commit:{fix.short_sha}"],
            ),
        ]
        url = f" ({fix.url})" if fix.url else ""
        body = (
            f"Fixed in commit [`{fix.short_sha}`]{url} — \"{fix.subject}\", "
            f"authored by {fix.author} on {_date_part(fix.author_date)}.\n\n"
            f"Files changed: {', '.join(fix.files)}."
        )
        return Section(
            id="resolution", title=SECTION_TITLES["resolution"], badge="green",
            body=body, claims=claims,
        )

    def _action_items(self) -> Section:
        ev = self.evidence
        fix = ev.fix_commit
        claims: list[Claim] = []
        tests = _test_files(fix.files)
        if tests:
            claims.append(
                Claim(
                    text=(
                        f"Keep the regression test added with the fix "
                        f"({', '.join(tests)}) passing in CI."
                    ),
                    refs=["fix", f"commit:{fix.short_sha}"],
                )
            )
        for issue in ev.issues:
            if len(claims) >= 3:
                break
            claims.append(
                Claim(
                    text=(
                        f"Track follow-up in the linked issue "
                        f"(#{issue.number}) which is currently {issue.state}."
                    ),
                    refs=[f"issue:{issue.number}"],
                )
            )
        if not claims:
            return Section(
                id="action_items",
                title=SECTION_TITLES["action_items"],
                badge="red",
                body=(
                    f"{NO_EVIDENCE_PHRASE} of agreed follow-ups in "
                    "repository data: the fix commit adds no tests and no "
                    "linked issue thread records agreed action items."
                ),
                claims=[],
            )
        body = "Grounded follow-ups visible in the repository evidence:\n" + "\n".join(
            f"- {c.text}" for c in claims
        )
        return Section(
            id="action_items", title=SECTION_TITLES["action_items"],
            badge="yellow", body=body, claims=claims,
        )

    def _lessons(self) -> Section:
        ev = self.evidence
        cand = self._top_candidate()
        fix_day = _parse_day(ev.fix_commit.author_date)
        claims: list[Claim] = []
        if cand is not None and fix_day is not None:
            cand_day = _parse_day(cand.author_date)
            claims.append(
                Claim(
                    text=(
                        f"Introducer linkage: the top candidate "
                        f"{cand.short_sha} is supported by "
                        f"{', '.join(cand.methods)} (combined score "
                        f"{cand.score:.2f})."
                    ),
                    refs=[f"candidate:{cand.short_sha}", "fix"],
                )
            )
            if cand_day is not None:
                days = (fix_day - cand_day).days
                claims.append(
                    Claim(
                        text=(
                            f"Candidate evidence suggests ~{days} days "
                            f"between the introducer candidate "
                            f"({cand.short_sha}, {_date_part(cand.author_date)}) "
                            f"and the fix ({ev.fix_commit.short_sha}, "
                            f"{_date_part(ev.fix_commit.author_date)})."
                        ),
                        refs=[f"candidate:{cand.short_sha}", "fix"],
                    )
                )
                body_note = (
                    f"What the linkage shows: if `{cand.short_sha}` is "
                    f"indeed the introducer, the vulnerable code was in the "
                    f"repository for ~{days} days "
                    f"({_date_part(cand.author_date)} → "
                    f"{_date_part(ev.fix_commit.author_date)}). The day "
                    f"count derives from commit author dates of a "
                    f"*candidate* introducer (score {cand.score:.2f}), not "
                    f"a confirmed one — treat it as an estimate."
                )
            else:
                body_note = (
                    "The introducer candidate carries no parseable date, so "
                    "no latency estimate is possible."
                )
        else:
            claims.append(
                Claim(
                    text=(
                        "No introducer candidate met the evidence bar, so "
                        "no introducer-to-fix latency can be estimated."
                    ),
                    refs=["case"],
                )
            )
            body_note = (
                "Open question: SZZ-lite linkage produced no introducer "
                "candidate for this fix — the true origin of the bug "
                "remains unknown from repository data alone."
            )
        return Section(
            id="lessons", title=SECTION_TITLES["lessons"], badge="yellow",
            body=body_note, claims=claims,
        )

    # -- entry point ----------------------------------------------------------

    def generate(self) -> Postmortem:
        """Generate the postmortem from evidence alone (deterministic)."""
        start = time.monotonic()
        builders = {
            "summary": self._summary,
            "impact": self._impact,
            "timeline": self._timeline,
            "root_cause": self._root_cause,
            "detection": self._detection,
            "resolution": self._resolution,
            "action_items": self._action_items,
            "lessons": self._lessons,
        }
        sections = [builders[sid]() for sid in SECTION_IDS]
        elapsed = time.monotonic() - start
        pm = Postmortem(
            case=self.evidence.case.name,
            title=f"Postmortem: {self.evidence.fix_commit.subject} ({self.evidence.case.name})",
            generated_by=GENERATOR_DETERMINISTIC,
            sections=sections,
        )
        pm.markdown = render_markdown(pm)
        pm.meta = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "wall_clock_seconds": round(elapsed, 4),
            "generator": GENERATOR_DETERMINISTIC,
            "evidence_notes": self.evidence.meta.get("notes", ""),
        }
        return pm


# ---------------------------------------------------------------------------
# Bob CLI plumbing (parse + normalize are unit-testable without the binary)
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from *text* (tolerates code fences)."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop the opening fence line and any trailing fence
        if len(lines) > 1:
            lines = lines[1:]
        while lines and lines[-1].strip().endswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        data = json.loads(stripped[start : end + 1])
        if isinstance(data, dict):
            return data
    raise ValueError("no JSON object found")


def parse_bob_result(raw: str) -> dict[str, Any]:
    """Parse ``bob run --format json`` stdout into the role's JSON payload.

    Documented envelope (docs/research/ibm-bob-notes.md section 3):
    ``{type:"result", timestamp, status, stats{...}, last_message}`` — the
    role's own JSON output rides in ``last_message`` (possibly wrapped in a
    markdown fence). Raises ``ValueError`` starting with
    'unparseable bob output:' when nothing parses.
    """
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        raise ValueError(f"unparseable bob output: {raw[:200]}") from None
    if not isinstance(envelope, dict):
        raise ValueError(f"unparseable bob output: {raw[:200]}")
    last_message = envelope.get("last_message")
    if isinstance(last_message, dict):
        return last_message
    if isinstance(last_message, str):
        try:
            return _extract_json(last_message)
        except (ValueError, json.JSONDecodeError):
            raise ValueError(f"unparseable bob output: {raw[:200]}") from None
    raise ValueError(f"unparseable bob output: {raw[:200]}")


def _clamp_badge(badge: Any) -> str:
    """Clamp an arbitrary badge value to one of contracts.BADGES."""
    return badge if badge in BADGES else "yellow"


def normalize_postmortem(
    data: dict[str, Any], evidence: Evidence, meta: dict[str, Any] | None = None
) -> Postmortem:
    """Validate/normalize raw sre-synthesizer JSON into a contracts.Postmortem.

    * badges are clamped to ``BADGES``;
    * sections with unknown ids are folded into ``lessons``;
    * all 8 canonical sections end up present: missing ones (in particular
      the honesty sections impact/detection) are inserted as red
      'No evidence' sections — the model omitting impact is NOT a license
      to skip the honesty rule;
    * impact/detection are forced to red/no-claims unless repository
      evidence actually contains them (it never does for collector output).
    """
    case = str(data.get("case") or evidence.case.name)
    title = str(data.get("title") or f"Postmortem: {evidence.fix_commit.subject}")
    by_id: dict[str, Section] = {}
    stray_notes: list[str] = []

    raw_sections = data.get("sections") or []
    if not isinstance(raw_sections, list):
        raw_sections = []
    for raw in raw_sections:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id", "")).strip()
        if sid not in SECTION_IDS:
            stray = str(raw.get("body", "") or raw.get("title", "")).strip()
            if stray:
                stray_notes.append(stray)
            continue
        body = str(raw.get("body", ""))
        claims = [
            Claim(
                text=str(c.get("text", "")),
                refs=[str(r) for r in (c.get("refs") or [])],
            )
            for c in (raw.get("claims") or [])
            if isinstance(c, dict) and str(c.get("text", "")).strip()
        ]
        by_id[sid] = Section(
            id=sid,
            title=str(raw.get("title") or SECTION_TITLES[sid]),
            badge=_clamp_badge(raw.get("badge")),
            body=body,
            claims=claims,
        )

    # honesty enforcement: repository evidence cannot ground impact or
    # detection, so whatever the model wrote there is discarded and replaced
    # by the red 'No evidence' section (contract: red + phrase + no claims)
    for hid in ("impact", "detection"):
        by_id.pop(hid, None)

    sections: list[Section] = []
    for sid in SECTION_IDS:
        sections.append(by_id.get(sid) or _red_no_evidence(sid))
    if stray_notes:
        lessons = sections[-1]  # lessons is the last canonical id
        extra = "\n\n".join(stray_notes)
        lessons.body = (
            (lessons.body + "\n\n" if lessons.body.strip() else "")
            + "Additional notes from synthesis (unknown section ids, kept "
            "here):\n" + extra
        )

    pm = Postmortem(
        case=case,
        title=title,
        generated_by=GENERATOR_BOB,
        sections=sections,
    )
    pm.markdown = render_markdown(pm)
    pm.meta = {
        "generator": GENERATOR_BOB,
        "evidence_notes": evidence.meta.get("notes", ""),
    }
    if meta:
        pm.meta.update(meta)
    return pm


class BobOrchestrator:
    """Drive the real IBM Bob CLI: 3 parallel analyst roles, then synthesis.

    Command template (flags per docs/research/ibm-bob-notes.md section 3)::

        bob run --chat-mode=<role-slug> --format json [--max-cost N] \
            [--workspace <workdir>] --accept-license "<role prompt>"

    Analyst failures do not abort the run — they are recorded in
    ``meta['role_failures']`` and synthesis continues with the survivors
    (honesty over completeness).
    """

    def __init__(
        self,
        evidence: Evidence,
        workdir: Path | None = None,
        bob_bin: str = "bob",
        api_key: str | None = None,
        max_cost: float | None = None,
    ) -> None:
        self.evidence = evidence
        self.workdir = workdir
        self.bob_bin = bob_bin
        self.api_key = api_key
        self.max_cost = max_cost

    # -- plumbing -------------------------------------------------------------

    def _preflight(self) -> str:
        """Check the bob binary and API key; return the key to use."""
        if shutil.which(self.bob_bin) is None:
            raise BobUnavailableError("bob binary not found")
        key = self.api_key or os.environ.get("BOB_API_KEY", "")
        if not key:
            raise BobUnavailableError("BOB_API_KEY not set")
        return key

    def _build_command(self, role: RoleDef, prompt: str) -> list[str]:
        cmd = [
            self.bob_bin,
            "run",
            f"--chat-mode={role.slug}",
            "--format",
            "json",
            "--accept-license",
        ]
        if self.max_cost is not None:
            cmd += ["--max-cost", str(self.max_cost)]
        if self.workdir is not None:
            cmd += ["--workspace", str(self.workdir)]
        cmd.append(prompt)
        return cmd

    def _run_role(self, role: RoleDef, prompt: str, key: str) -> dict[str, Any]:
        """Run one ``bob run`` subprocess and return its parsed JSON payload."""
        cmd = self._build_command(role, prompt)
        env = dict(os.environ)
        env["BOB_API_KEY"] = key
        cwd = str(self.workdir) if self.workdir is not None else None
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=BOB_TIMEOUT_SECONDS,
            env=env,
            cwd=cwd,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"bob run exited {proc.returncode} for role {role.id}: "
                f"{(proc.stderr or proc.stdout)[-400:]}"
            )
        return parse_bob_result(proc.stdout)

    # -- phases ----------------------------------------------------------------

    def _analysts(self, key: str) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
        """Phase 1: run the 3 analyst roles in parallel subprocesses."""
        analyst_roles = [r for r in ROLES if r.id in ANALYST_ROLE_IDS]
        findings: dict[str, dict[str, Any]] = {}
        failures: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(
                    self._run_role, role, build_role_prompt(role, self.evidence), key
                ): role
                for role in analyst_roles
            }
            for future, role in futures.items():
                try:
                    findings[role.id] = future.result()
                except Exception as exc:  # analyst failure != abort
                    failures[role.id] = str(exc)[:400]
        return findings, failures

    def _synthesis_prompt(self, findings: dict[str, dict[str, Any]]) -> str:
        synth_role = ROLES[-1]
        assert synth_role.id == SYNTH_ROLE_ID
        base_prompt = build_role_prompt(synth_role, self.evidence)
        findings_json = json.dumps(findings, indent=2)
        return (
            base_prompt
            + "\n\n## Analyst findings (phase 1)\n"
            + "```json\n"
            + findings_json
            + "\n```\n\n"
            + "Merge the analyst findings with the evidence into the "
            "postmortem JSON. Where analysts disagree or went beyond the "
            "evidence, prefer the evidence. Roles that failed are simply "
            "absent — do not invent their findings. Reply with the JSON "
            "object defined by the output contract, nothing else."
        )

    # -- entry point -------------------------------------------------------------

    def generate(self) -> Postmortem:
        """Run the two-phase Bob pipeline and normalize its output."""
        start = time.monotonic()
        key = self._preflight()
        findings, failures = self._analysts(key)
        try:
            synth_role = ROLES[-1]
            payload = self._run_role(
                synth_role, self._synthesis_prompt(findings), key
            )
            if not isinstance(payload.get("sections"), list):
                raise ValueError(
                    f"unparseable bob output: {json.dumps(payload)[:200]}"
                )
        except BobUnavailableError:
            raise
        except Exception as exc:
            raise BobUnavailableError(str(exc)) from exc
        elapsed = time.monotonic() - start
        meta = {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "wall_clock_seconds": round(elapsed, 4),
            "role_failures": failures,
            "analyst_roles_used": sorted(findings.keys()),
        }
        pm = normalize_postmortem(payload, self.evidence, meta=meta)
        report = validate_linkage(pm, self.evidence)
        pm.meta["linkage_rate"] = report.rate
        pm.meta["linkage_invalid"] = [i.to_dict() for i in report.invalid]
        return pm


# ---------------------------------------------------------------------------
# mode dispatch
# ---------------------------------------------------------------------------


def generate_postmortem(
    evidence: Evidence, mode: str = "auto", **orchestrator_kwargs: Any
) -> Postmortem:
    """Generate a postmortem for *evidence*.

    ``mode``: ``"deterministic"`` (offline floor), ``"bob"`` (real CLI;
    :class:`BobUnavailableError` propagates) or ``"auto"`` (try Bob, fall
    back to deterministic recording ``meta['fallback_reason']``).
    ``orchestrator_kwargs`` are forwarded to :class:`BobOrchestrator`.
    """
    if mode == "deterministic":
        return DeterministicOrchestrator(evidence).generate()
    if mode == "bob":
        return BobOrchestrator(evidence, **orchestrator_kwargs).generate()
    if mode == "auto":
        try:
            return BobOrchestrator(evidence, **orchestrator_kwargs).generate()
        except BobUnavailableError as exc:
            pm = DeterministicOrchestrator(evidence).generate()
            pm.meta["fallback_reason"] = exc.reason
            return pm
    raise ValueError(f"unknown mode: {mode!r} (use auto|bob|deterministic)")
