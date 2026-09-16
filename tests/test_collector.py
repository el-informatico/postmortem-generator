"""Offline unit tests for the collector piece (pmg.collector).

No network: GitHubClient's ``_fetch`` seam is monkeypatched with canned
responses, and git runs against tiny synthetic repositories in tmp_path.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from pmg.collector import (
    CollectorError,
    GitHubClient,
    GitRepo,
    OfflineCacheMiss,
    collect_case,
)
from pmg.collector.github_api import BASE_URL, GitHubAPIError
from pmg.contracts import CaseConfig, Evidence


# ---------------------------------------------------------------------------
# synthetic git repo helper
# ---------------------------------------------------------------------------


def _git(repo: Path, *args: str, date: str | None = None) -> str:
    env = dict(os.environ)
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0, f"git {args} failed: {proc.stderr}"
    return proc.stdout


def build_synthetic_repo(root: Path) -> dict[str, str]:
    """Build a 4-commit repo: initial, INTRODUCER (adds the vulnerable
    memcpy line), README churn, FIX (adds a bounds check replacing it).
    Returns the full shas keyed by role."""
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)

    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Dev Example")

    def commit(msg: str, files: dict[str, str], date: str) -> str:
        for rel, text in files.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", msg, date=date)
        return _git(repo, "rev-parse", "HEAD").strip()

    shas: dict[str, str] = {}
    shas["initial"] = commit(
        "initial: add socks module",
        {
            "README.md": "demo project\n",
            "src/socks.c": (
                "#include <string.h>\n"
                "\n"
                "int socks5_connect(const char *hostname)\n"
                "{\n"
                "  return 0;\n"
                "}\n"
            ),
        },
        "2019-01-01T10:00:00+00:00",
    )
    shas["introducer"] = commit(
        "socks: add SOCKS5 remote resolve",
        {
            "src/socks.c": (
                "#include <string.h>\n"
                "\n"
                "int socks5_resolve_local(const char *hostname, size_t hostname_len)\n"
                "{\n"
                "  char dst[256];\n"
                "  memcpy(dst, hostname, hostname_len); /* SOCKS5 remote resolve */\n"
                "  return 0;\n"
                "}\n"
            ),
        },
        "2020-02-14T10:00:00+00:00",
    )
    shas["readme"] = commit(
        "readme: fix typo",
        {"README.md": "demo project, fixed\n"},
        "2021-06-01T10:00:00+00:00",
    )
    shas["fix"] = commit(
        "socks: return error if hostname too long",
        {
            "src/socks.c": (
                "#include <string.h>\n"
                "\n"
                "int socks5_resolve_local(const char *hostname, size_t hostname_len)\n"
                "{\n"
                "  char dst[256];\n"
                "  if(hostname_len > 255)\n"
                "    return -1; /* hostname too long for remote resolve */\n"
                "  memcpy(dst, hostname, hostname_len); /* checked copy */\n"
                "  return 0;\n"
                "}\n"
            ),
        },
        "2023-10-11T05:34:19+00:00",
    )
    return shas


# ---------------------------------------------------------------------------
# (a) GitHubClient cache behaviour via the _fetch seam
# ---------------------------------------------------------------------------


def test_github_client_cache_roundtrip(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    calls: list[str] = []

    def fake_fetch(url, headers):
        calls.append(url)
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["User-Agent"] == "postmortem-generator"
        assert headers["Authorization"] == "Bearer tk"
        return 200, {"number": 7, "title": "hello"}, {}

    client = GitHubClient("curl/curl", token="tk", cache_dir=cache)
    monkeypatch.setattr(client, "_fetch", fake_fetch)

    assert client.issue(7) == {"number": 7, "title": "hello"}
    assert calls == [BASE_URL + "/repos/curl/curl/issues/7"]

    # cache file written with the documented shape, keyed by sha256(url)
    url = BASE_URL + "/repos/curl/curl/issues/7"
    key = hashlib.sha256(url.encode()).hexdigest()
    entry = json.loads((cache / f"{key}.json").read_text(encoding="utf-8"))
    assert entry["url"] == url
    assert entry["status"] == 200
    assert entry["body"] == {"number": 7, "title": "hello"}
    assert entry["fetched_at"]

    # online mode always refetches (no stale cache reads)
    client.issue(7)
    assert len(calls) == 2

    # offline mode reads only the cache and never calls _fetch
    offline = GitHubClient("curl/curl", cache_dir=cache, offline=True)
    monkeypatch.setattr(
        offline, "_fetch", lambda *a, **k: pytest.fail("network in offline mode")
    )
    assert offline.issue(7) == {"number": 7, "title": "hello"}

    # offline miss on an uncached URL
    with pytest.raises(OfflineCacheMiss) as excinfo:
        offline.get_json("/repos/curl/curl/issues/8")
    assert "/repos/curl/curl/issues/8" in str(excinfo.value)
    assert isinstance(excinfo.value, CollectorError)


def test_github_client_pagination_online_and_offline(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    page1 = BASE_URL + "/repos/o/r/issues/5/comments?per_page=100"
    page2 = BASE_URL + "/repos/o/r/issues/5/comments?per_page=100&page=2"

    def fake_fetch(url, headers):
        if url == page1:
            return 200, [{"id": 1}], {"Link": f'<{page2}>; rel="next"'}
        assert url == page2, url
        return 200, [{"id": 2}], {}

    client = GitHubClient("o/r", cache_dir=cache)
    monkeypatch.setattr(client, "_fetch", fake_fetch)
    assert client.issue_comments(5) == [{"id": 1}, {"id": 2}]
    assert client.fetched_urls == [page1, page2]

    # offline replay merges the recorded pagination chain from cache
    offline = GitHubClient("o/r", cache_dir=cache, offline=True)
    monkeypatch.setattr(
        offline, "_fetch", lambda *a, **k: pytest.fail("network in offline mode")
    )
    assert offline.issue_comments(5) == [{"id": 1}, {"id": 2}]


def test_github_client_error_on_non_200(tmp_path, monkeypatch):
    client = GitHubClient("o/r", cache_dir=tmp_path / "cache")
    monkeypatch.setattr(
        client, "_fetch", lambda url, headers: (403, {"message": "rate limited"}, {})
    )
    with pytest.raises(GitHubAPIError) as excinfo:
        client.get_json("/repos/o/r")
    assert excinfo.value.status == 403
    assert "rate limited" in str(excinfo.value)


# ---------------------------------------------------------------------------
# (b) collect_case over a synthetic repo
# ---------------------------------------------------------------------------


def test_collect_case_synthetic(tmp_path):
    shas = build_synthetic_repo(tmp_path)
    case = CaseConfig(
        name="synthetic",
        repo="example/demo",
        issues=[],
        fix_sha=shas["fix"][:10],
        local_repo=str(tmp_path / "repo"),
    )
    evidence = collect_case(case, tmp_path / "cache", offline=True)

    assert isinstance(evidence, Evidence)
    # fix commit shape
    assert evidence.fix_commit.sha == shas["fix"]
    assert evidence.fix_commit.subject == "socks: return error if hostname too long"
    assert evidence.fix_commit.author == "Dev Example"
    assert evidence.fix_commit.author_date.startswith("2023-10-11")
    assert evidence.fix_commit.files == ["src/socks.c"]
    assert evidence.fix_commit.url == (
        f"https://github.com/example/demo/commit/{shas['fix']}"
    )
    assert "memcpy" in evidence.fix_commit.diff

    # no issues requested
    assert evidence.issues == []

    # introducer candidates: the INTRODUCER commit is top-1
    assert evidence.introducer_candidates, "expected at least one candidate"
    top = evidence.introducer_candidates[0]
    assert top.sha == shas["introducer"]
    assert top.subject == "socks: add SOCKS5 remote resolve"
    assert "szz-blame" in top.methods
    assert "log-S" in top.methods
    assert top.detail["blamed_lines"] == ["src/socks.c:6"]
    assert top.detail["line_count"] == 1
    # blame(1.0)*0.5 + log-S(1.0)*0.3, no issue-link
    assert top.score == pytest.approx(0.8)

    # timeline: sorted by date, refs well-formed, fix event present
    dates = [event.date for event in evidence.timeline]
    assert dates == sorted(dates)
    ids = evidence.ref_ids()
    for event in evidence.timeline:
        assert event.ref in ids, f"dangling ref {event.ref}"
    assert {"fix", "case", f"commit:{evidence.fix_commit.short_sha}",
            f"candidate:{top.short_sha}"} <= ids
    fix_events = [e for e in evidence.timeline if e.ref == "fix"]
    assert len(fix_events) == 1
    assert fix_events[0].date == "2023-10-11"

    # meta
    assert evidence.meta["offline"] is True
    assert evidence.meta["collected_at"]
    assert any(s.startswith("git:") for s in evidence.meta["sources"])

    # JSON round-trip preserves the contract
    out = tmp_path / "evidence.json"
    evidence.save(out)
    assert Evidence.load(out).to_dict() == evidence.to_dict()


def test_collect_case_missing_repo(tmp_path):
    case = CaseConfig(
        name="synthetic",
        repo="example/demo",
        issues=[],
        fix_sha="deadbeef",
        local_repo=str(tmp_path / "nope"),
    )
    with pytest.raises(CollectorError, match="local repository"):
        collect_case(case, tmp_path / "cache", offline=True)


# ---------------------------------------------------------------------------
# (c) offline cache miss path
# ---------------------------------------------------------------------------


def test_collect_case_offline_cache_miss(tmp_path):
    shas = build_synthetic_repo(tmp_path)
    case = CaseConfig(
        name="synthetic",
        repo="example/demo",
        issues=[1],
        fix_sha=shas["fix"],
        local_repo=str(tmp_path / "repo"),
    )
    with pytest.raises(OfflineCacheMiss) as excinfo:
        collect_case(case, tmp_path / "empty-cache", offline=True)
    message = str(excinfo.value)
    assert "/repos/example/demo/issues/1" in message
    assert "refresh_cache" in message


# ---------------------------------------------------------------------------
# GitRepo basics (blame / pickaxe) against the synthetic repo
# ---------------------------------------------------------------------------


def test_gitrepo_blame_and_pickaxe(tmp_path):
    shas = build_synthetic_repo(tmp_path)
    repo = GitRepo(tmp_path / "repo")

    assert repo.resolve_sha(shas["fix"][:8]) == shas["fix"]
    assert repo.resolve_sha(f"{shas['fix']}~1") == shas["readme"]

    # line 6 in the pre-fix file is the vulnerable memcpy line
    blamed = repo.blame_lines(f"{shas['fix']}~1", "src/socks.c", 6, 6)
    assert blamed == [(6, shas["introducer"])]

    hits = repo.log_pickaxe("memcpy", file="src/socks.c")
    assert hits[0] == (shas["introducer"], "2020-02-14T10:00:00+00:00")
    # oldest first
    dates = [d for _, d in hits]
    assert dates == sorted(dates)

    # before= filter excludes commits dated after the cutoff
    old_hits = repo.log_pickaxe("checked copy", file="src/socks.c",
                                before="2023-10-10T00:00:00+00:00")
    assert old_hits == []
    assert repo.log_pickaxe("checked copy", file="src/socks.c") == [
        (shas["fix"], "2023-10-11T05:34:19+00:00")
    ]


# ---------------------------------------------------------------------------
# (d) tags → releases; committer dates; issue lifecycle fields (B7)
# ---------------------------------------------------------------------------


def test_first_tag_containing_prefers_stable_and_versionsort(tmp_path):
    shas = build_synthetic_repo(tmp_path)
    repo = tmp_path / "repo"
    # a pre-release tag and a stable tag on the fix; a version-sort trap
    # (v10 vs v9) on the introducer
    _git(repo, "tag", "rel-2.15.0-rc1", shas["fix"])
    _git(repo, "tag", "v9.0.0", shas["fix"])
    _git(repo, "tag", "v10.0.0", shas["introducer"])
    gr = GitRepo(repo)

    assert gr.tags_containing(shas["fix"]) == ["rel-2.15.0-rc1", "v9.0.0"]
    # the -rc tag is skipped: a release candidate is not a release
    tag, date = gr.first_tag_containing(shas["fix"])
    assert tag == "v9.0.0"
    assert date.startswith("2023-10-11")
    # version sort, not alphabetical (v9.0.0 < v10.0.0 numerically); the
    # introducer is an ancestor of the fix, so v9.0.0 contains it too
    assert gr.first_tag_containing(shas["introducer"])[0] == "v9.0.0"
    # a commit no tag contains (new work on top of the fix) → None
    after = _git(
        repo, "commit", "-q", "--allow-empty", "-m", "post-fix work",
        date="2024-01-01T00:00:00+00:00",
    )
    del after
    assert gr.first_tag_containing("HEAD") is None


def test_collect_case_release_and_lifecycle_events(tmp_path, monkeypatch):
    shas = build_synthetic_repo(tmp_path)
    _git(tmp_path / "repo", "tag", "v2.0.0", shas["fix"])
    case = CaseConfig(
        name="synthetic",
        repo="example/demo",
        issues=[7],
        fix_sha=shas["fix"][:10],
        local_repo=str(tmp_path / "repo"),
    )

    class _StubClient:
        def __init__(self, repo, cache_dir=None, offline=False):
            pass

        def issue(self, n):
            return {
                "number": n,
                "title": "PR: fix the socks bug",
                "state": "closed",
                "user": {"login": "dev"},
                "created_at": "2023-10-10T00:00:00Z",
                "closed_at": "2023-10-11T06:00:00Z",
                "body": "Fixes the bug.",
                "html_url": "https://github.com/example/demo/issues/7",
                "pull_request": {"merged_at": None},
            }

        def issue_comments(self, n):
            return []

    monkeypatch.setattr("pmg.collector.collect.GitHubClient", _StubClient)
    evidence = collect_case(case, tmp_path / "cache", offline=True)

    # lifecycle fields mapped through the contract
    issue = evidence.issues[0]
    assert issue.closed_at == "2023-10-11T06:00:00Z"
    assert issue.merged_at == ""
    assert issue.is_pull_request is True

    # releases: one for the fix, one for the top introducer candidate
    roles = {r.role: r for r in evidence.releases}
    assert roles["fix"].tag == "v2.0.0"
    assert roles["fix"].version == "2.0.0"
    assert roles["fix"].date == "2023-10-11"
    assert roles["fix"].url.endswith("/releases/tag/v2.0.0")
    assert roles["introducer-candidate"].tag == "v2.0.0"

    # timeline carries issue-open, issue-close (unmerged PR) and release rows
    texts = [e.description for e in evidence.timeline]
    assert any("PR #7 opened" in t for t in texts)
    assert any("PR #7 closed (unmerged)" in t and "closed_at" in t for t in texts)
    assert any(
        "2.0.0 released (first tag containing the fix" in t for t in texts
    )
    ids = evidence.ref_ids()
    for event in evidence.timeline:
        assert event.ref in ids, f"dangling ref {event.ref}"
    assert "release:v2.0.0" in ids
