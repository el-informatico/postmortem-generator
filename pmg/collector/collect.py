"""collect_case(): assemble the Evidence contract from git + GitHub cache
(piece 1, collector orchestration). Deterministic, no AI, no invention —
every timeline entry traces back to a repository artifact.
"""
from __future__ import annotations

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
    TimelineEvent,
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


def _issue_thread(
    client: GitHubClient, case: CaseConfig, n: int
) -> IssueThread:
    """Fetch issue ``n`` (with comments) and map it to the contract."""
    data = client.issue(n)
    comments_raw = client.issue_comments(n)
    author = (data.get("user") or {}).get("login", "")
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
    """
    # -- local repository ---------------------------------------------------
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

    # -- fix commit -----------------------------------------------------------
    fix = repo.commit_info(case.fix_sha, max_diff_bytes=max_diff_bytes)
    fix.url = f"https://github.com/{case.repo}/commit/{fix.sha}"
    notes: list[str] = []
    if fix.diff.endswith(DIFF_TRUNCATED_MARKER):
        notes.append("fix diff truncated at max_diff_bytes")

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

    # -- introducer candidates --------------------------------------------------
    candidates = szz.introducer_candidates(fix, repo, issues)

    # -- timeline (repository facts only, sorted by date) -----------------------
    timeline: list[TimelineEvent] = []
    for thread in issues:
        timeline.append(
            TimelineEvent(
                date=(thread.created_at or "")[:10],
                kind="issue",
                description=f"Issue #{thread.number} opened by "
                            f"{thread.author or 'unknown'}: {_snippet(thread.title)}",
                ref=f"issue:{thread.number}",
            )
        )
        for k, comment in enumerate(thread.comments):
            timeline.append(
                TimelineEvent(
                    date=(comment.created_at or "")[:10],
                    kind="issue-comment",
                    description=f"{comment.author or 'unknown'} commented on "
                                f"issue #{thread.number}: {_snippet(comment.body)}",
                    ref=f"issue:{thread.number}#comment:{k}",
                )
            )
    for cand in candidates[:3]:
        timeline.append(
            TimelineEvent(
                date=(cand.author_date or "")[:10],
                kind="commit",
                description=f"Candidate introducer commit {cand.short_sha}: "
                            f"{_snippet(cand.subject)}",
                ref=f"candidate:{cand.short_sha}",
            )
        )
    timeline.append(
        TimelineEvent(
            date=(fix.author_date or "")[:10],
            kind="commit",
            description=f"Fix commit {fix.short_sha}: {_snippet(fix.subject)}",
            ref="fix",
        )
    )
    timeline.sort(key=lambda e: e.date)  # ISO dates sort correctly; stable

    # -- meta & evidence ---------------------------------------------------------
    sources = [f"git: {_display_path(repo_dir)}"]
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
        meta=meta,  # type: ignore[arg-type]
    )
