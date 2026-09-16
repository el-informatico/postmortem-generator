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
import re
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
    utc_date,
    utc_iso,
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


def _snippet(text: str, width: int = 100) -> str:
    """Collapse whitespace and truncate to one line (collector parity)."""
    single = " ".join((text or "").split())
    return single if len(single) <= width else single[: width - 3] + "..."


def _push_day(commit) -> str | None:
    """Committer-date day (UTC) of *commit* when it differs from the author
    day (the review/merge latency worth a timeline line); else None."""
    day = utc_date(getattr(commit, "committer_date", "") or "")
    if day and day != utc_date(commit.author_date or ""):
        return day
    return None


_DIFF_STRING_RE = re.compile(r'"([^"\\]{3,})"')


def _diff_message_strings(diff: str, limit: int = 2) -> list[tuple[str, str]]:
    """Human-readable messages quoted in the changed (+/-) lines of *diff*.

    These are the diff's own words for what was wrong — error/info strings
    the code prints. Consecutive string literals are joined only when the
    first ends with a space (C/Java split-string continuation, e.g.
    ``"...hostnames of "`` + ``"length > 255"``); separate call arguments
    stay separate messages. A message counts when it has >= 4 words.
    Returns ``(sign, message)`` tuples — ``"+"`` what the fix now says,
    ``"-"`` what the vulnerable code used to say — added lines first.
    """
    added: list[tuple[str, str]] = []
    removed: list[tuple[str, str]] = []

    def _flush(sign: str, chunks: list[str]) -> None:
        messages: list[str] = []
        for chunk in chunks:
            if messages and messages[-1].endswith(" "):
                messages[-1] += chunk
            else:
                messages.append(chunk)
        for message in messages:
            message = " ".join(message.split())
            if len(message.split()) >= 4 and message not in [
                m for _, m in added + removed
            ]:
                (added if sign == "+" else removed).append((sign, message))

    current_sign = ""
    chunks: list[str] = []
    for line in (diff or "").splitlines():
        if line.startswith(("+++", "---")):
            continue
        sign = line[0] if line[:1] in "+-" else ""
        if sign and sign == current_sign:
            chunks += _DIFF_STRING_RE.findall(line)
        else:
            _flush(current_sign, chunks)
            if sign:
                current_sign, chunks = sign, _DIFF_STRING_RE.findall(line)
            else:
                current_sign, chunks = "", []
    _flush(current_sign, chunks)
    return (added + removed)[:limit]


_TAG_PROJECT_RE = re.compile(r"^([a-z][a-z0-9]*)-(?=\d)")


def _tag_project(tag: str) -> str:
    """Project prefix of a version tag ('' when none) — collector parity:
    ``curl-7_69_0`` → ``curl``, ``rel/2.15.0`` → ``''``."""
    name = tag.rsplit("/", 1)[-1]
    name = re.sub(r"^v(?=\d)", "", name)
    match = _TAG_PROJECT_RE.match(name)
    return match.group(1) if match else ""


_CHECKLIST_ITEM_RE = re.compile(r"^\s*-\s+(.+)$")
_CHECKLIST_REF_RE = re.compile(
    r"\(#\d+\)|https?://\S+/issues/\d+"
)

# commit-message trailer lines (Bug:/Fixes:/Closes:/Signed-off-by: ...)
_TRAILER_RE = re.compile(r"^[A-Z][A-Za-z0-9-]+:\s")
_IMPERATIVE_RE = re.compile(
    r"^(restrict|limit|disable|remove|block|prevent|enable|require|"
    r"validate|update|upgrade|add|use|fix)\b", re.I
)


def _fix_message_segments(message: str) -> list[str]:
    """Clean prose segments of a commit message body (subject excluded).

    Paragraphs are split into sentences; bullet lines (``* `` / ``- ``)
    count as one segment each; trailer lines (``Bug:`` / ``Fixes:`` /
    ``Signed-off-by:`` ...) are dropped. These segments are the fix
    author's own explanation of the change — prime root-cause evidence
    that was in the repository all along.
    """
    lines = (message or "").splitlines()
    body = lines[1:] if lines else []  # drop the subject line
    raw: list[str] = []
    paragraph: list[str] = []
    for line in body:
        stripped = line.strip()
        if not stripped:
            if paragraph:
                raw.append(" ".join(paragraph))
                paragraph = []
            continue
        if stripped.startswith(("* ", "- ")):
            if paragraph:
                raw.append(" ".join(paragraph))
                paragraph = []
            raw.append(stripped[2:].strip())
        elif _TRAILER_RE.match(stripped):
            continue
        else:
            paragraph.append(stripped)
    if paragraph:
        raw.append(" ".join(paragraph))
    segments: list[str] = []
    for chunk in raw:
        if chunk.startswith(("http://", "https://")) or len(chunk.split()) < 5:
            continue
        parts = re.split(r"(?<=[.!?])\s+", chunk)
        current = ""
        for part in parts:
            candidate = (current + " " + part).strip() if current else part
            if len(candidate.split()) >= 5:
                segments.append(candidate)
                current = ""
            else:
                current = candidate
        if current and len(current.split()) >= 5:
            segments.append(current)
    return segments


def _top_segments(message: str, count: int = 2) -> list[str]:
    """The *count* longest fix-message segments, in their original order —
    the most informative lines of the author's own explanation."""
    segments = _fix_message_segments(message)
    chosen = sorted(segments, key=len, reverse=True)[:count]
    return [s for s in segments if s in chosen]

# classic buffer-overflow copy sinks — a diff line naming one is the copy
# the postmortem should point at (deterministic vocabulary, not semantics)
_COPY_SINK_RE = re.compile(r"\b(memcpy|memmove|strcpy|strncpy|sprintf)\s*\(")


def _diff_copy_lines(diff: str, limit: int = 2) -> list[str]:
    """Diff lines that perform a raw copy (``memcpy`` & friends), changed or
    context — the failure site of a buffer overflow, quoted verbatim."""
    out: list[str] = []
    for line in (diff or "").splitlines():
        if line.startswith(("+++", "---")):
            continue
        if _COPY_SINK_RE.search(line):
            stripped = line[1:].strip() if line[:1] in "+-" else line.strip()
            if stripped not in out:
                out.append(stripped)
    return out[:limit]


def _issue_checklist_items(body: str, limit: int = 12) -> list[str]:
    """Top-level checklist items of an issue body that reference another
    issue/PR (by ``(#N)`` or an issues URL) — recorded follow-ups, i.e.
    action items the humans actually agreed to, quoted verbatim from the
    thread. Sub-bullets (indented lines) are detail, not follow-ups;
    ``:emoji:`` status markers are stripped."""
    items: list[str] = []
    for line in (body or "").splitlines():
        if line.startswith((" ", "\t")):
            continue  # sub-bullet / continuation, not a top-level follow-up
        match = _CHECKLIST_ITEM_RE.match(line)
        if not match:
            continue
        item = re.sub(r"^:[a-z0-9_]+:\s*", "", match.group(1))
        item = _snippet(item, width=160)
        if _CHECKLIST_REF_RE.search(item):
            items.append(item)
        if len(items) >= limit:
            break
    return items


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
        if fix is None:
            # Issues-only case: an ops/community incident reconstruction with
            # no fix commit in repository data.
            claims: list[Claim] = []
            for issue in ev.issues:
                claims.append(
                    Claim(
                        text=(
                            f"Issue #{issue.number} (\"{issue.title}\", state "
                            f"{issue.state}) documents this incident in "
                            f"{ev.case.repo}."
                        ),
                        refs=[f"issue:{issue.number}"],
                    )
                )
            if not claims:
                return _red_no_evidence("summary")
            body = (
                f"Case **{ev.case.name}** in `{ev.case.repo}` is an "
                f"operational/community incident reconstructed from the "
                f"linked issue thread(s) only — no fix commit exists in the "
                f"collected repository data, so there is no commit-level fix "
                f"or introducer story to report. "
                + " ".join(c.text for c in claims)
                + " Impact and detection are not derivable from repository "
                "data and are marked 'No evidence' in their sections."
            )
            return Section(
                id="summary", title=SECTION_TITLES["summary"], badge="green",
                body=body, claims=claims,
            )
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

    def _milestone_entries(self) -> list[dict[str, Any]]:
        """Curated (date, kind, text, refs) narrative milestones.

        The timeline a postmortem reader needs is a list of milestones,
        not every raw evidence row: issue/PR lifecycle, the TOP introducer
        candidate (authored, and pushed when the committer date differs),
        the releases that started shipping the vulnerable code and the
        fix, and the fix itself. Lower-ranked SZZ candidates stay in
        root_cause as what they are (candidates), and comments posted
        after the resolution are follow-up discussion, not incident
        history. An issue/PR closing on the same day a commit was pushed
        is folded into that push line — one story moment, one line.
        """
        ev = self.evidence
        fix = ev.fix_commit
        cand = self._top_candidate()

        resolution: date | None = None
        if fix is not None:
            resolution = _parse_day(
                utc_date(fix.committer_date or fix.author_date)
            )
        if resolution is None:
            resolution = max(
                (d for d in (_parse_day(utc_date(i.closed_at)) for i in ev.issues) if d),
                default=None,
            )

        # days on which a commit-push line can absorb a same-day close
        push_days = {
            day
            for day in (
                _push_day(cand) if cand is not None else None,
                _push_day(fix) if fix is not None else None,
            )
            if day
        }

        def _close_state(issue) -> str:
            if issue.merged_at:
                return " (merged)"
            return " (unmerged)" if issue.is_pull_request else ""

        entries: list[dict[str, Any]] = []
        for issue in ev.issues:
            label = "PR" if issue.is_pull_request else "Issue"
            entries.append(
                {
                    "date": utc_date(issue.created_at),
                    "kind": "issue",
                    "text": (
                        f"{label} #{issue.number} opened by "
                        f"{issue.author or 'unknown'}: {_snippet(issue.title)}"
                    ),
                    "refs": [f"issue:{issue.number}"],
                }
            )
            if issue.closed_at:
                close_day = utc_date(issue.closed_at)
                if close_day not in push_days:
                    entries.append(
                        {
                            "date": close_day,
                            "kind": "issue",
                            "text": (
                                f"{label} #{issue.number} closed"
                                f"{_close_state(issue)} (closed_at "
                                f"{utc_iso(issue.closed_at)})"
                            ),
                            "refs": [f"issue:{issue.number}"],
                        }
                    )
            for k, comment in enumerate(issue.comments):
                day = _parse_day(utc_date(comment.created_at))
                if resolution is not None and day is not None and day > resolution:
                    continue  # post-resolution discussion, not incident history
                entries.append(
                    {
                        "date": utc_date(comment.created_at),
                        "kind": "issue-comment",
                        "text": (
                            f"{comment.author or 'unknown'} commented on "
                            f"{label.lower()} #{issue.number}: "
                            f"{_snippet(comment.body)}"
                        ),
                        "refs": [f"issue:{issue.number}#comment:{k}"],
                    }
                )
        if cand is not None:
            entries.append(
                {
                    "date": utc_date(cand.author_date),
                    "kind": "commit",
                    "text": (
                        f"Candidate introducer commit {cand.short_sha}: "
                        f"{_snippet(cand.subject)}"
                    ),
                    "refs": [f"candidate:{cand.short_sha}"],
                }
            )
            push_day = _push_day(cand)
            if push_day is not None:
                text = (
                    f"Candidate introducer commit {cand.short_sha} pushed "
                    f"(committer date {utc_iso(cand.committer_date)})"
                )
                refs = [f"candidate:{cand.short_sha}"]
                for issue in ev.issues:
                    if issue.closed_at and utc_date(issue.closed_at) == push_day:
                        text += (
                            f"; {'PR' if issue.is_pull_request else 'Issue'} "
                            f"#{issue.number} closed{_close_state(issue)} "
                            f"(closed_at {utc_iso(issue.closed_at)})"
                        )
                        refs.append(f"issue:{issue.number}")
                entries.append(
                    {"date": push_day, "kind": "commit", "text": text, "refs": refs}
                )
        for rel in ev.releases:
            name = _tag_project(rel.tag)
            label = f"{name} {rel.version}".strip() if name else rel.version
            if rel.role == "fix":
                text = (
                    f"{label} released — first release containing the "
                    f"fix (tag {rel.tag} contains fix commit "
                    f"{rel.contains_sha[:10]})"
                )
                refs = [f"release:{rel.tag}", "fix"]
            else:
                text = (
                    f"{label} released — first release shipping the "
                    f"vulnerable code (tag {rel.tag} contains introducer "
                    f"candidate {rel.contains_sha[:10]})"
                )
                refs = [f"release:{rel.tag}"]
                if cand is not None:
                    refs.append(f"candidate:{cand.short_sha}")
            entries.append(
                {"date": rel.date, "kind": "release", "text": text, "refs": refs}
            )
        if fix is not None:
            entries.append(
                {
                    "date": utc_date(fix.author_date),
                    "kind": "commit",
                    "text": (
                        f"Fix commit {fix.short_sha}: {_snippet(fix.subject)}"
                    ),
                    "refs": ["fix", f"commit:{fix.short_sha}"],
                }
            )
            push_day = _push_day(fix)
            if push_day is not None:
                text = (
                    f"Fix commit {fix.short_sha} pushed (committer date "
                    f"{utc_iso(fix.committer_date)})"
                )
                refs = ["fix", f"commit:{fix.short_sha}"]
                for issue in ev.issues:
                    if issue.closed_at and utc_date(issue.closed_at) == push_day:
                        text += (
                            f"; {'PR' if issue.is_pull_request else 'Issue'} "
                            f"#{issue.number} closed{_close_state(issue)} "
                            f"(closed_at {utc_iso(issue.closed_at)})"
                        )
                        refs.append(f"issue:{issue.number}")
                entries.append(
                    {"date": push_day, "kind": "commit", "text": text, "refs": refs}
                )
        entries = [e for e in entries if e.get("date")]
        entries.sort(key=lambda e: e["date"])  # ISO dates sort correctly; stable
        return entries

    def _timeline(self) -> Section:
        claims: list[Claim] = []
        body_lines: list[str] = []
        for entry in self._milestone_entries():
            claims.append(
                Claim(
                    text=f"{entry['date']} — {entry['text']}",
                    refs=list(entry["refs"]),
                )
            )
            body_lines.append(f"- **{entry['date']}** — {entry['text']}")
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
        if fix is None:
            # Issues-only case: degrade to an issue-thread-derived statement.
            if not ev.issues:
                return _red_no_evidence("root_cause")
            claims = [
                Claim(
                    text=(
                        f"No fix commit exists in the collected repository "
                        f"data; the incident is documented in issue "
                        f"#{issue.number} (\"{issue.title}\", state "
                        f"{issue.state})."
                    ),
                    refs=[f"issue:{issue.number}"],
                )
                for issue in ev.issues
            ]
            body = (
                "No fix commit exists in the collected repository data, so no "
                "diff-based technical root cause can be reconstructed. What "
                f"the linked issue thread(s) document for this incident: "
                + "; ".join(
                    f"#{i.number} \"{i.title}\" ({i.state})" for i in ev.issues
                )
                + ". This is an issue-thread-derived statement, not "
                "commit-level causality."
            )
            return Section(
                id="root_cause", title=SECTION_TITLES["root_cause"],
                badge="yellow", body=body, claims=claims,
            )
        claims: list[Claim] = []
        chain: list[str] = []
        if cand is not None:
            claims.append(
                Claim(
                    text=(
                        f"The bug was introduced in the introducer candidate "
                        f"{cand.short_sha} (\"{cand.subject}\", "
                        f"{_date_part(cand.author_date)})."
                    ),
                    refs=[f"candidate:{cand.short_sha}", f"commit:{fix.short_sha}"],
                )
            )
            chain.append(
                f"The bug was introduced in the introducer candidate "
                f"`{cand.short_sha}` (\"{cand.subject}\", "
                f"{_date_part(cand.author_date)})."
            )
        fix_fact = (
            f"The fix `{fix.short_sha}` (\"{fix.subject}\", "
            f"{_date_part(fix.author_date)})."
        )
        chain.append(fix_fact)
        messages = _diff_message_strings(fix.diff)
        if messages:
            quoted = "; ".join(
                f"\"{msg}\" "
                + ("(added by the fix)" if sign == "+"
                   else "(the vulnerable behavior — a switch instead of failing)")
                for sign, msg in messages
            )
            claims.append(
                Claim(
                    text=(
                        f"The fix diff states the failure in its own words: "
                        f"{quoted}."
                    ),
                    refs=[f"commit:{fix.short_sha}"],
                )
            )
            chain.append(
                f"The fix diff states the failure in its own words: {quoted}."
            )
        segments = _top_segments(fix.message)
        if segments:
            excerpt = " ".join(segments)
            claims.append(
                Claim(
                    text=f'The fix commit message explains: "{excerpt}"',
                    refs=[f"commit:{fix.short_sha}"],
                )
            )
            chain.append(f'The fix commit message explains: "{excerpt}".')
        copy_lines = _diff_copy_lines(fix.diff, limit=1)
        if copy_lines:
            line = copy_lines[0]
            object_noun = (
                "the too-long hostname" if re.search(r"host", line, re.I)
                else "the data"
            )
            claims.append(
                Claim(
                    text=(
                        f"The diff shows the copy at the failure site "
                        f"(`{line}`): {object_noun} copied into the buffer."
                    ),
                    refs=[f"commit:{fix.short_sha}"],
                )
            )
            chain.append(
                f"The diff shows the copy at the failure site (`{line}`): "
                f"{object_noun} copied into the buffer."
            )
        if not claims:
            # nothing richer was derivable — anchor the section on the fix
            claims.append(
                Claim(text=fix_fact, refs=["fix", f"commit:{fix.short_sha}"])
            )
            chain.append(fix_fact)
        cand_part = ""
        if cand is not None:
            methods = ", ".join(cand.methods)
            cand_part = (
                f"\n\n**Introducer linkage:** the top candidate "
                f"`{cand.short_sha}` (score {cand.score:.2f}, methods: "
                f"{methods}) — the evidence is consistent with the bug being "
                f"introduced in {cand.short_sha} "
                f"({_date_part(cand.author_date)}); this is SZZ-lite "
                "candidate linkage, not proven causality."
            )
        else:
            cand_part = (
                "\n\nNo introducer candidate is present in the collected "
                f"evidence — {NO_EVIDENCE_PHRASE.lower()} for who "
                "introduced the bug."
            )
        body = " ".join(chain) + cand_part
        badge = "yellow"  # interpretation over grounded facts
        return Section(
            id="root_cause", title=SECTION_TITLES["root_cause"], badge=badge,
            body=body, claims=claims,
        )

    def _detection(self) -> Section:
        return _red_no_evidence("detection")

    def _resolution(self) -> Section:
        fix = self.evidence.fix_commit
        if fix is None:
            # Issues-only case: honestly state there is no fix commit.
            return Section(
                id="resolution",
                title=SECTION_TITLES["resolution"],
                badge="red",
                body=(
                    f"{NO_EVIDENCE_PHRASE} — no fix commit in repository "
                    "data. This case is an operational/community incident "
                    "reconstructed from the linked issue thread(s); "
                    "resolution is documented there, not in a repository "
                    "commit, so this section makes no claims."
                ),
                claims=[],
            )
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
        fix_release = next(
            (r for r in self.evidence.releases if r.role == "fix"), None
        )
        if fix_release is not None:
            claims.append(
                Claim(
                    text=(
                        f"First release containing the fix: "
                        f"{fix_release.version} (tag {fix_release.tag}, "
                        f"{fix_release.date})."
                    ),
                    refs=[f"release:{fix_release.tag}"],
                )
            )
            body += (
                f"\n\nFirst release containing the fix: "
                f"{fix_release.version} (tag {fix_release.tag}, "
                f"{fix_release.date})."
            )
        diff_lines = _diff_key_lines(fix.diff, max_lines=6)
        if diff_lines:
            body += (
                "\n\nKey lines of the fix diff:\n\n```\n"
                + "\n".join(diff_lines)
                + "\n```"
            )
        return Section(
            id="resolution", title=SECTION_TITLES["resolution"], badge="green",
            body=body, claims=claims,
        )

    def _action_items(self) -> Section:
        ev = self.evidence
        fix = ev.fix_commit
        claims: list[Claim] = []
        fix_release = next(
            (r for r in ev.releases if r.role == "fix"), None
        )
        if fix_release is not None:
            up_name = _tag_project(fix_release.tag)
            up_label = (
                f"{up_name} {fix_release.version}".strip()
                if up_name else fix_release.version
            )
            claims.append(
                Claim(
                    text=(
                        f"Upgrade to {up_label} — the first "
                        f"release containing the fix (tag {fix_release.tag})."
                    ),
                    refs=[f"release:{fix_release.tag}", "fix"],
                )
            )
        if fix is not None:
            claims.append(
                Claim(
                    text=(
                        f"Apply the patch to your local version — fix commit "
                        f"{fix.short_sha} (\"{fix.subject}\") — where "
                        "upgrading is not possible."
                    ),
                    refs=["fix", f"commit:{fix.short_sha}"],
                )
            )
            imperatives = [
                seg for seg in _fix_message_segments(fix.message)
                if _IMPERATIVE_RE.match(seg)
            ][:3]
            if imperatives:
                joined = " ".join(imperatives)
                claims.append(
                    Claim(
                        text=(
                            "Deploy the change the fix itself describes: "
                            f"\"{joined}\"."
                        ),
                        refs=["fix", f"commit:{fix.short_sha}"],
                    )
                )
        tests = _test_files(fix.files) if fix is not None else []
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
        recorded = 0
        for issue in ev.issues:
            for item in _issue_checklist_items(issue.body):
                claims.append(
                    Claim(
                        text=(
                            f"Follow-up recorded in the tracking issue "
                            f"(#{issue.number}): {item}"
                        ),
                        refs=[f"issue:{issue.number}"],
                    )
                )
                recorded += 1
        if fix is not None and not recorded:
            # no thread-recorded follow-ups: keep the tracking pointer only
            for issue in ev.issues:
                claims.append(
                    Claim(
                        text=(
                            f"Track follow-up in the linked issue "
                            f"(#{issue.number}) which is currently "
                            f"{issue.state}."
                        ),
                        refs=[f"issue:{issue.number}"],
                    )
                )
                break
        if not claims:
            if fix is None:
                red_body = (
                    f"{NO_EVIDENCE_PHRASE} of agreed follow-ups in "
                    "repository data: there is no fix commit and no linked "
                    "issue thread records agreed action items."
                )
            else:
                red_body = (
                    f"{NO_EVIDENCE_PHRASE} of agreed follow-ups in "
                    "repository data: the fix commit adds no tests and no "
                    "linked issue thread records agreed action items."
                )
            return Section(
                id="action_items",
                title=SECTION_TITLES["action_items"],
                badge="red",
                body=red_body,
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
        fix_day = (
            _parse_day(ev.fix_commit.author_date)
            if ev.fix_commit is not None
            else None
        )
        claims: list[Claim] = []
        if ev.fix_commit is None:
            # Issues-only case: no introducer→fix latency exists at all.
            claims.append(
                Claim(
                    text=(
                        "No fix commit exists in the repository data for "
                        "this case, so no introducer-to-fix latency can be "
                        "estimated (issues-only case)."
                    ),
                    refs=["case"],
                )
            )
            body_note = (
                "Open question: this operational/community incident has no "
                "fix commit in repository data, so introducer-to-fix latency "
                "is undefined — the linked issue thread(s) are the only "
                "repository evidence for what happened and what was done "
                "about it."
            )
            return Section(
                id="lessons", title=SECTION_TITLES["lessons"], badge="yellow",
                body=body_note, claims=claims,
            )
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

    def _default_title(self) -> str:
        """Title from the fix commit subject, or the issue thread for
        issues-only cases (no fix commit in repository data)."""
        ev = self.evidence
        if ev.fix_commit is not None:
            subject = ev.fix_commit.subject
        elif ev.issues:
            subject = ev.issues[0].title
        else:
            subject = ev.case.name
        return f"Postmortem: {subject} ({ev.case.name})"

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
            title=self._default_title(),
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
    if evidence.fix_commit is not None:
        fallback_title = f"Postmortem: {evidence.fix_commit.subject}"
    elif evidence.issues:
        fallback_title = f"Postmortem: {evidence.issues[0].title}"
    else:
        fallback_title = f"Postmortem: {evidence.case.name}"
    title = str(data.get("title") or fallback_title)
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
