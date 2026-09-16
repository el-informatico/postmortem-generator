"""collect_case(): assemble the Evidence contract from git + GitHub cache
(piece 1, collector orchestration). Deterministic, no AI, no invention —
every timeline entry traces back to a repository artifact.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from pmg.collector import szz
from pmg.collector.errors import CollectorError, OfflineCacheMiss
from pmg.collector.github_api import GitHubClient
from pmg.collector.git_local import DIFF_TRUNCATED_MARKER, GitRepo
from pmg.contracts import (
    CaseConfig,
    CommitInfo,
    Evidence,
    IssueComment,
    IssueThread,
    ReleaseInfo,
    TimelineEvent,
    utc_date,
    utc_iso,
)


def _snippet(text: str, width: int = 100) -> str:
    """Collapse whitespace and truncate a body to one factual line."""
    single = " ".join((text or "").split())
    return single if len(single) <= width else single[: width - 3] + "..."


def _display_path(path: Path) -> str:
    """Human-facing path label: relative to cwd when possible.

    Evidence JSON is a shareable artifact — it must never carry absolute
    host paths (they leak the machine's layout and username).
    """
    try:
        return str(Path(path).relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def _display_version(tag: str) -> str:
    """Best-effort display version for a git tag.

    ``curl-7_69_0`` → ``7.69.0`` · ``rel/2.15.0`` → ``2.15.0`` ·
    ``v1.2.3`` → ``1.2.3`` · anything unparseable → the tag itself.
    """
    name = tag.rsplit("/", 1)[-1]          # rel/2.15.0 → 2.15.0
    name = re.sub(r"^v(?=\d)", "", name)   # v1.2.3 → 1.2.3
    name = re.sub(r"^[a-z]+-(?=\d[\._])", "", name)  # curl-7_69_0 → 7_69_0
    return name.replace("_", ".")


def _tag_project(tag: str) -> str:
    """Project prefix of a version tag, ``""`` when the tag has none.

    ``curl-7_69_0`` → ``curl`` · ``log4j-2.15.0`` → ``log4j`` ·
    ``rel/2.15.0`` → ``""``. The tag itself names the project; no
    hard-coded project list.
    """
    name = tag.rsplit("/", 1)[-1]
    name = re.sub(r"^v(?=\d)", "", name)
    match = re.match(r"^([a-z][a-z0-9]*)-(?=\d)", name)
    return match.group(1) if match else ""


def _release_name(tag: str, version: str) -> str:
    """Human-facing release label: "curl 7.69.0", "2.15.0"."""
    project = _tag_project(tag)
    return f"{project} {version}".strip()


def _issue_thread(
    client: GitHubClient, case: CaseConfig, n: int
) -> IssueThread:
    """Fetch issue ``n`` (with comments) and map it to the contract."""
    data = client.issue(n)
    comments_raw = client.issue_comments(n)
    author = (data.get("user") or {}).get("login", "")
    pr_meta = data.get("pull_request") or {}
    return IssueThread(
        number=int(data.get("number") or n),
        title=data.get("title") or "",
        state=data.get("state") or "",
        author=author,
        created_at=data.get("created_at") or "",
        body=data.get("body") or "",
        comments=[
            IssueComment(
                author=(c.get("user") or {}).get("login", ""),
                created_at=c.get("created_at") or "",
                body=c.get("body") or "",
            )
            for c in comments_raw
            if isinstance(c, dict)
        ],
        url=data.get("html_url") or f"https://github.com/{case.repo}/issues/{n}",
        closed_at=data.get("closed_at") or "",
        merged_at=pr_meta.get("merged_at") or "",
        is_pull_request=bool(pr_meta),
    )


def collect_case(
    case: CaseConfig,
    cache_dir: Path,
    offline: bool = False,
    repo_path: Path | None = None,
    max_diff_bytes: int = 200_000,
) -> Evidence:
    """Collect the full :class:`Evidence` for ``case``.

    ``repo_path`` overrides ``case.local_repo``; relative repo paths resolve
    against the current working directory. ``offline=True`` requires every
    GitHub response to be in ``cache_dir`` (see scripts/refresh_cache.py).

    Issues-only cases (``case.fix_sha`` empty) skip the local repository and
    SZZ entirely — no ``local_repo`` is required — and produce
    ``Evidence.fix_commit = None`` with the timeline built from the issue
    threads alone.
    """
    notes: list[str] = []
    sources: list[str] = []

    # -- local repository + fix commit (skipped for issues-only cases) -------
    fix: CommitInfo | None = None
    repo = None
    if case.fix_sha:
        repo_dir = Path(repo_path) if repo_path is not None else Path(case.local_repo)
        if not repo_dir.is_absolute():
            repo_dir = Path.cwd() / repo_dir
        if not repo_dir.exists():
            raise CollectorError(
                f"local repository for case '{case.name}' not found at {repo_dir}; "
                f"clone it (e.g. git clone https://github.com/{case.repo} {repo_dir}) "
                f"or pass repo_path="
            )
        repo = GitRepo(repo_dir)
        fix = repo.commit_info(case.fix_sha, max_diff_bytes=max_diff_bytes)
        fix.url = f"https://github.com/{case.repo}/commit/{fix.sha}"
        sources.append(f"git: {_display_path(repo_dir)}")
        if fix.diff.endswith(DIFF_TRUNCATED_MARKER):
            notes.append("fix diff truncated at max_diff_bytes")
    else:
        notes.append("issues-only case (no fix commit in repository data)")

    # -- issue threads (GitHub API, cached) -----------------------------------
    client = GitHubClient(case.repo, cache_dir=cache_dir, offline=offline)
    issues: list[IssueThread] = []
    for n in case.issues:
        try:
            issues.append(_issue_thread(client, case, n))
        except OfflineCacheMiss as exc:
            raise OfflineCacheMiss(
                exc.url,
                f"{exc} (needed for issue #{n} of case '{case.name}'; warm the "
                f"cache first: /usr/bin/python3.12 scripts/refresh_cache.py)",
            ) from exc

    # -- introducer candidates (needs the fix commit + repo) --------------------
    candidates: list = []
    if fix is not None and repo is not None:
        candidates = szz.introducer_candidates(fix, repo, issues)

    # -- releases (first tag containing the fix / top candidate) ---------------
    releases: list[ReleaseInfo] = []
    if repo is not None:
        wanted: list[tuple[str, str]] = []
        if fix is not None:
            wanted.append(("fix", fix.sha))
        if candidates:
            wanted.append(("introducer-candidate", candidates[0].sha))
        for role, sha in wanted:
            hit = repo.first_tag_containing(sha)
            if hit is None:
                continue
            tag, tag_date = hit
            releases.append(
                ReleaseInfo(
                    tag=tag,
                    version=_display_version(tag),
                    date=utc_date(tag_date),
                    contains_sha=sha,
                    role=role,
                    url=f"https://github.com/{case.repo}/releases/tag/{tag}",
                )
            )

    # -- timeline (repository facts only, sorted by date) -----------------------
    timeline: list[TimelineEvent] = []
    for thread in issues:
        label = "PR" if thread.is_pull_request else "Issue"
        timeline.append(
            TimelineEvent(
                date=utc_date(thread.created_at),
                kind="issue",
                description=f"{label} #{thread.number} opened by "
                            f"{thread.author or 'unknown'}: {_snippet(thread.title)}",
                ref=f"issue:{thread.number}",
            )
        )
        if thread.closed_at:
            state = (
                " (merged)" if thread.merged_at
                else " (unmerged)" if thread.is_pull_request
                else ""
            )
            timeline.append(
                TimelineEvent(
                    date=utc_date(thread.closed_at),
                    kind="issue",
                    description=f"{label} #{thread.number} closed{state} "
                                f"(closed_at {utc_iso(thread.closed_at)})",
                    ref=f"issue:{thread.number}",
                )
            )
        for k, comment in enumerate(thread.comments):
            timeline.append(
                TimelineEvent(
                    date=utc_date(comment.created_at),
                    kind="issue-comment",
                    description=f"{comment.author or 'unknown'} commented on "
                                f"{label.lower()} #{thread.number}: "
                                f"{_snippet(comment.body)}",
                    ref=f"issue:{thread.number}#comment:{k}",
                )
            )
    for cand in candidates[:3]:
        timeline.append(
            TimelineEvent(
                date=utc_date(cand.author_date),
                kind="commit",
                description=f"Candidate introducer commit {cand.short_sha}: "
                            f"{_snippet(cand.subject)}",
                ref=f"candidate:{cand.short_sha}",
            )
        )
        if utc_date(cand.committer_date) not in ("", utc_date(cand.author_date)):
            timeline.append(
                TimelineEvent(
                    date=utc_date(cand.committer_date),
                    kind="commit",
                    description=f"Candidate introducer commit {cand.short_sha} "
                                f"pushed (committer date "
                                f"{utc_iso(cand.committer_date)})",
                    ref=f"candidate:{cand.short_sha}",
                )
            )
    if fix is not None:
        timeline.append(
            TimelineEvent(
                date=utc_date(fix.author_date),
                kind="commit",
                description=f"Fix commit {fix.short_sha}: {_snippet(fix.subject)}",
                ref="fix",
            )
        )
        if utc_date(fix.committer_date) not in ("", utc_date(fix.author_date)):
            timeline.append(
                TimelineEvent(
                    date=utc_date(fix.committer_date),
                    kind="commit",
                    description=f"Fix commit {fix.short_sha} pushed "
                                f"(committer date {utc_iso(fix.committer_date)})",
                    ref="fix",
                )
            )
    for rel in releases:
        name = _release_name(rel.tag, rel.version)
        if rel.role == "fix":
            description = (
                f"{name} released (first tag containing the fix "
                f"{rel.contains_sha[:10]}: {rel.tag})"
            )
        else:
            description = (
                f"{name} released (first tag containing introducer "
                f"candidate {rel.contains_sha[:10]}: {rel.tag})"
            )
        timeline.append(
            TimelineEvent(
                date=rel.date,
                kind="release",
                description=description,
                ref=f"release:{rel.tag}",
            )
        )
    timeline.sort(key=lambda e: e.date)  # ISO dates sort correctly; stable

    # -- meta & evidence ---------------------------------------------------------
    if case.issues:
        sources.append(
            f"github-api: {'cached' if offline else 'live'} ({_display_path(cache_dir)})"
        )
    meta: dict[str, object] = {
        "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "offline": offline,
        "sources": sources,
        "notes": "; ".join(notes),
    }

    return Evidence(
        case=case,
        fix_commit=fix,
        issues=issues,
        introducer_candidates=candidates,
        timeline=timeline,
        releases=releases,
        meta=meta,  # type: ignore[arg-type]
    )
