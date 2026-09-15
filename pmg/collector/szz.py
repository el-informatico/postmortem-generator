"""SZZ-lite introducer candidate search (piece 1, collector).

Deterministic git-archaeology, no AI anywhere. Given a fix commit's unified
diff we look for the commit(s) that most likely introduced the fixed bug
with three cheap methods:

* ``szz-blame``  — blame the OLD side (fix~1) of every removed line and
  count how many removed lines trace back to each commit.
* ``log-S``      — pickaxe (``git log -S``) strings mined from the removed
  lines (identifiers and string literals); the OLDEST commit that changed a
  string's occurrence count is a candidate.
* ``issue-link`` — explicit cross-links: a candidate commit message that
  closes/fixes one of the case's issue numbers, or an issue comment that
  mentions the candidate's sha.

Scoring formula (the single source of truth for ``IntroducerCandidate.score``):

    score = 0.5 * blame_norm + 0.3 * log_s + 0.2 * issue_link

    blame_norm = blamed_removed_lines(sha) / max over blame candidates
                 (0.0 when the blame method produced nothing)
    log_s      = 1.0 if the commit is the oldest -S hit for at least one
                 mined string, else 0.0
    issue_link = 1.0 if an explicit cross-link exists, else 0.0

Ranking: score descending, then EARLIER author date, then sha (a total,
deterministic order). The fix commit itself and any commit authored after
the fix are excluded. Edge cases: a diff with no removed lines falls back
to blaming the context lines around the additions (new files: pickaxe on
the added code's identifiers); truncated diffs are parsed as far as they
go; binary files simply contribute no hunks. When nothing is found the
result is ``[]`` — the postmortem then honestly reports "no introducer
identified".
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from pmg.collector.git_local import DIFF_TRUNCATED_MARKER, GitError, GitRepo
from pmg.contracts import CommitInfo, IntroducerCandidate, IssueThread, SZZ_METHODS

# Method weights (documented in the module docstring).
_W_BLAME = 0.5
_W_LOG_S = 0.3
_W_ISSUE_LINK = 0.2

#: How many blame commits to materialize into candidates (bounded work).
_MAX_BLAME_COMMITS = 10
#: Upper bound for the (unused) diff of candidate commits — candidates carry
#: no diff in the contract, this only keeps ``git show`` cheap.
_CANDIDATE_DIFF_BUDGET = 4096
#: Cap on pickaxe strings mined from removed lines (each costs one git log -S).
_MAX_PICKAXE_STRINGS = 12

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{5,}")
_STRING_RE = re.compile(r'"([^"\\\n]{6,})"')
_KEYWORD_ISSUE_RE = re.compile(
    r"\b(?:closes?|closed|fixes?|fixed|resolves?|resolved)\s*:?\s+#(\d+)",
    re.IGNORECASE,
)
_SHA_TOKEN_RE = re.compile(r"\b[0-9a-f]{7,40}\b")

# Generic C keywords / words that pickaxe to prehistoric commits and add noise.
_PICKAXE_STOPWORDS = {
    "return", "static", "struct", "sizeof", "switch", "typedef", "extern",
    "define", "include", "unsigned", "signed", "continue", "default",
    "hostname", "length", "defines", "include", "second", "server",
}

# Directory components that mark a path as test or documentation churn.
_SKIP_DIRS = {
    "test", "tests", "testing", "testsuite", "testdata",
    "doc", "docs", "documentation",
}


# ---------------------------------------------------------------------------
# Unified diff parsing
# ---------------------------------------------------------------------------


@dataclass
class FileDiff:
    """Per-file parse of a unified diff: line numbers WITH text (the text
    feeds the pickaxe string miner)."""

    path: str                              # repo path to blame/analyze
    old_path: str
    new_path: str
    is_new: bool                           # old side is /dev/null
    is_delete: bool                        # new side is /dev/null
    removed: list[tuple[int, str]] = field(default_factory=list)   # (old_ln, text)
    added: list[tuple[int, str]] = field(default_factory=list)     # (new_ln, text)
    context_old: list[tuple[int, str]] = field(default_factory=list)  # (old_ln, text)


def _norm_path(raw: str) -> str:
    """Strip the a// b/ prefix (and quoting) from a diff header path."""
    raw = raw.strip()
    if len(raw) >= 2 and raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    if raw.startswith("a/") or raw.startswith("b/"):
        return raw[2:]
    return raw


def parse_unified_diff(diff: str) -> list[FileDiff]:
    """Parse ``git show`` output into per-file hunks.

    Robust to: multiple files, multiple hunks per file, new/deleted files
    (/dev/null), rename headers, ``\\ No newline`` markers, binary files
    (no hunks) and a trailing truncation marker — everything up to the
    truncation point is parsed.
    """
    if diff.endswith(DIFF_TRUNCATED_MARKER):
        diff = diff[: -len(DIFF_TRUNCATED_MARKER)]
    files: list[FileDiff] = []
    current: FileDiff | None = None
    old_path_pending = ""
    old_ln = new_ln = 0
    in_hunk = False

    for line in diff.splitlines():
        if line.startswith("diff --git"):
            current, in_hunk = None, False  # paths arrive via ---/+++ headers
            continue
        if line.startswith("--- "):
            old_path_pending = _norm_path(line[4:])
            in_hunk = False
            continue
        if line.startswith("+++ "):
            new_path = _norm_path(line[4:])
            old_path = old_path_pending or new_path
            is_new = old_path == "/dev/null"
            is_delete = new_path == "/dev/null"
            path = old_path if is_delete else new_path
            current = FileDiff(
                path=path, old_path=old_path, new_path=new_path,
                is_new=is_new, is_delete=is_delete,
            )
            files.append(current)
            in_hunk = False
            continue
        hunk = _HUNK_RE.match(line)
        if hunk:
            if current is not None:
                old_ln = int(hunk.group(1))
                new_ln = int(hunk.group(3))
                in_hunk = True
            continue
        if in_hunk and current is not None:
            if line.startswith("-"):
                current.removed.append((old_ln, line[1:]))
                old_ln += 1
            elif line.startswith("+"):
                current.added.append((new_ln, line[1:]))
                new_ln += 1
            elif line.startswith(" "):
                current.context_old.append((old_ln, line[1:]))
                old_ln += 1
                new_ln += 1
            elif line.startswith("\\"):
                pass  # "\ No newline at end of file"
            else:
                in_hunk = False  # unknown line (binary note, garbage): leave hunk
    return files


def is_analyzed_path(path: str) -> bool:
    """True when a file should participate in the analysis: skip test and
    documentation paths (their churn rarely introduces the production bug,
    and skipping keeps the work bounded)."""
    parts = [p for p in path.split("/") if p]
    if not parts:
        return False
    if any(p.lower() in _SKIP_DIRS for p in parts[:-1]):
        return False
    base = parts[-1].lower()
    if base.startswith("test"):
        return False
    if "_test" in base or "-test" in base or ".test." in base:
        return False
    if base.endswith((".md", ".rst")):
        return False
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(iso: str) -> datetime | None:
    """Parse an ISO-8601 date/datetime; naive values are treated as UTC."""
    try:
        dt = datetime.fromisoformat(iso.strip().replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _merge_ranges(line_nos: list[int]) -> list[tuple[int, int]]:
    """Merge sorted line numbers into inclusive (start, end) ranges."""
    if not line_nos:
        return []
    ordered = sorted(set(line_nos))
    ranges: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for n in ordered[1:]:
        if n <= prev + 1:
            prev = n
        else:
            ranges.append((start, prev))
            start = prev = n
    ranges.append((start, prev))
    return ranges


def _pickaxe_strings(lines: list[str], cap: int = _MAX_PICKAXE_STRINGS) -> list[str]:
    """Mine ``git log -S`` candidate strings from diff line text: identifiers
    of >= 6 chars plus quoted string literals; de-duplicated, stopwords
    removed, ordered by (occurrences, length) descending, capped."""
    counts: dict[str, int] = {}
    for text in lines:
        found = _IDENT_RE.findall(text) + _STRING_RE.findall(text)
        for s in set(found):
            if s.lower() in _PICKAXE_STOPWORDS:
                continue
            counts[s] = counts.get(s, 0) + 1
    ranked = sorted(counts, key=lambda s: (-counts[s], -len(s), s))
    return ranked[:cap]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def introducer_candidates(
    fix: CommitInfo,
    repo: GitRepo,
    issues: list[IssueThread],
    limit: int = 5,
) -> list[IntroducerCandidate]:
    """Rank commits that may have introduced the bug fixed by ``fix``.

    See the module docstring for the method descriptions and the scoring
    formula. Returns at most ``limit`` candidates, best first; ``[]`` when
    nothing could be established.
    """
    fix_dt = _parse_dt(fix.author_date)

    # -- parse the fix diff and pick the lines to analyze ------------------
    file_diffs = parse_unified_diff(fix.diff)
    analyzed = [f for f in file_diffs if not f.is_new and is_analyzed_path(f.path)]
    no_removed = not any(f.removed for f in analyzed)
    # (path, [(old_lineno, text)]) — removed lines, or context lines around
    # additions when the fix is a pure addition (blame fallback).
    target_lines: list[tuple[str, list[tuple[int, str]]]] = []
    for f in analyzed:
        lines = f.context_old if (no_removed and f.context_old) else f.removed
        if lines:
            target_lines.append((f.path, lines))
    all_removed_texts = [t for f in analyzed for _, t in f.removed]
    all_added_texts = [t for f in analyzed for _, t in f.added]
    pickaxe_texts = all_removed_texts or all_added_texts
    most_touched = (
        sorted(analyzed, key=lambda f: (-len(f.removed), -len(f.added), f.path))[0].path
        if analyzed
        else None
    )

    # -- method 1: szz-blame ------------------------------------------------
    blame_count: dict[str, int] = {}
    blame_lines: dict[str, list[str]] = {}
    try:
        blame_rev = repo.resolve_sha(f"{fix.sha}~1")
    except GitError:
        blame_rev = None  # root commit has no parent — nothing to blame
    if blame_rev:
        for path, lines in target_lines:
            for start, end in _merge_ranges([n for n, _ in lines]):
                try:
                    hits = repo.blame_lines(blame_rev, path, start, end)
                except GitError:
                    continue  # e.g. path missing at that revision
                for line_no, commit_sha in hits:
                    blame_count[commit_sha] = blame_count.get(commit_sha, 0) + 1
                    blame_lines.setdefault(commit_sha, []).append(f"{path}:{line_no}")

    # -- method 2: log-S (pickaxe on mined strings) -------------------------
    oldest_log_s: dict[str, str] = {}  # candidate sha -> pickaxe string
    if pickaxe_texts:
        strings = _pickaxe_strings(pickaxe_texts)
        before = fix.author_date if fix_dt else None
        for s in strings:
            hits = repo.log_pickaxe(s, file=most_touched, before=before)
            if hits and hits[0][0] not in oldest_log_s:
                oldest_log_s[hits[0][0]] = s
        if not oldest_log_s and most_touched is not None:
            # nothing found path-restricted: retry the best strings repo-wide
            for s in strings[:3]:
                hits = repo.log_pickaxe(s, file=None, before=before)
                if hits and hits[0][0] not in oldest_log_s:
                    oldest_log_s[hits[0][0]] = s

    # -- method 3: issue-link (needs issue numbers and sha mentions) --------
    issue_numbers = {t.number for t in issues}
    mentioned: dict[str, int] = {}  # short10 sha -> issue number mentioning it
    for thread in issues:
        blob = (thread.body or "") + "\n" + "\n".join(
            c.body or "" for c in thread.comments
        )
        for token in _SHA_TOKEN_RE.findall(blob):
            mentioned.setdefault(token[:10].lower(), thread.number)

    # -- assemble candidates (bounded work) ----------------------------------
    blame_ranked = sorted(blame_count, key=lambda s: (-blame_count[s], s))
    shas = list(blame_ranked[:_MAX_BLAME_COMMITS])
    shas += [s for s in oldest_log_s if s not in shas]

    candidates: list[IntroducerCandidate] = []
    for sha in shas:
        if sha == fix.sha:
            continue
        try:
            info = repo.commit_info(sha, max_diff_bytes=_CANDIDATE_DIFF_BUDGET)
        except GitError:
            continue
        info_dt = _parse_dt(info.author_date)
        if fix_dt is not None and info_dt is not None and info_dt > fix_dt:
            continue  # authored after the fix — cannot have introduced it
        linked_issue: int | None = None
        for m in _KEYWORD_ISSUE_RE.finditer(info.message):
            if int(m.group(1)) in issue_numbers:
                linked_issue = int(m.group(1))
                break
        if linked_issue is None and info.short_sha in mentioned:
            linked_issue = mentioned[info.short_sha]

        count = blame_count.get(sha, 0)
        max_count = max(
            (blame_count.get(s, 0) for s in shas if s != fix.sha), default=0
        )
        blame_norm = (count / max_count) if max_count else 0.0
        log_s_hit = sha in oldest_log_s
        link_hit = linked_issue is not None
        score = (
            _W_BLAME * blame_norm + _W_LOG_S * (1.0 if log_s_hit else 0.0)
            + _W_ISSUE_LINK * (1.0 if link_hit else 0.0)
        )

        method_map = {
            "szz-blame": count > 0,
            "log-S": log_s_hit,
            "issue-link": link_hit,
        }
        detail: dict[str, object] = {}
        fallbacks: list[str] = []
        if count > 0:
            detail["blamed_lines"] = blame_lines.get(sha, [])
            detail["line_count"] = count
        if log_s_hit:
            detail["pickaxe_string"] = oldest_log_s[sha]
        if link_hit:
            detail["linked_issue"] = linked_issue
        if no_removed and count > 0:
            fallbacks.append("blamed context lines (fix is a pure addition)")
        if not all_removed_texts and log_s_hit:
            fallbacks.append("pickaxe on added code (no removed lines)")
        if fallbacks:
            detail["fallback"] = fallbacks

        candidates.append(
            IntroducerCandidate(
                sha=info.sha,
                short_sha=info.short_sha,
                subject=info.subject,
                author=info.author,
                author_date=info.author_date,
                methods=[m for m in SZZ_METHODS if method_map[m]],
                score=round(score, 4),
                detail=detail,  # type: ignore[arg-type]
            )
        )

    far_past = datetime.min.replace(tzinfo=timezone.utc)
    candidates.sort(
        key=lambda c: (
            -c.score,
            _parse_dt(c.author_date) or far_past,
            c.sha,
        )
    )
    return candidates[:limit]
