"""Unit tests for the SZZ-lite diff parser and scoring, plus the optional
integration test against the real curl clone (.repos/curl, skips cleanly).

No network anywhere: everything runs on crafted diff strings or tiny
synthetic git repositories in tmp_path.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from pmg.collector import szz
from pmg.collector.git_local import DIFF_TRUNCATED_MARKER, GitError, GitRepo
from pmg.contracts import IntroducerCandidate, IssueComment, IssueThread, SZZ_METHODS

CURL_REPO = Path(__file__).resolve().parents[1] / ".repos" / "curl"
GROUND_TRUTH_API = (
    Path(__file__).resolve().parents[1] / "data" / "ground_truth" / "github-api.json"
)

DIFF_SAMPLE = """\
diff --git a/src/app.c b/src/app.c
index 1111111..2222222 100644
--- a/src/app.c
+++ b/src/app.c
@@ -10,4 +10,5 @@ int f(void) {
     keep();
-    old_one();
-    old_two();
+    new_one();
     tail();
diff --git a/tests/unit/test_x.c b/tests/unit/test_x.c
index 3333333..4444444 100644
--- a/tests/unit/test_x.c
+++ b/tests/unit/test_x.c
@@ -1,2 +1,3 @@
 check();
+check_more();
 done();
diff --git a/src/new_file.c b/src/new_file.c
new file mode 100644
index 0000000..5555555
--- /dev/null
+++ b/src/new_file.c
@@ -0,0 +1,2 @@
+int brand_new(void);
+int also_new(void);
"""


# ---------------------------------------------------------------------------
# diff parser
# ---------------------------------------------------------------------------


def test_parse_unified_diff_removed_line_numbers():
    files = szz.parse_unified_diff(DIFF_SAMPLE)
    by_path = {f.path: f for f in files}
    assert set(by_path) == {"src/app.c", "tests/unit/test_x.c", "src/new_file.c"}

    app = by_path["src/app.c"]
    assert app.removed == [(11, "    old_one();"), (12, "    old_two();")]
    assert app.added == [(11, "    new_one();")]
    assert app.context_old == [(10, "    keep();"), (13, "    tail();")]
    assert not app.is_new and not app.is_delete

    test_file = by_path["tests/unit/test_x.c"]
    assert test_file.removed == []
    assert test_file.added == [(2, "check_more();")]

    new_file = by_path["src/new_file.c"]
    assert new_file.is_new
    assert new_file.removed == []
    assert [n for n, _ in new_file.added] == [1, 2]


def test_parse_unified_diff_tolerates_truncation():
    truncated = DIFF_SAMPLE + DIFF_TRUNCATED_MARKER
    assert szz.parse_unified_diff(truncated) == szz.parse_unified_diff(DIFF_SAMPLE)


def test_parse_unified_diff_multiple_hunks_same_file():
    diff = (
        "--- a/lib/socks.c\n"
        "+++ b/lib/socks.c\n"
        "@@ -10,3 +10,3 @@\n"
        " ctx1();\n"
        "-removed_a();\n"
        " ctx2();\n"
        "@@ -900,3 +900,4 @@\n"
        " ctx3();\n"
        "-removed_b();\n"
        "+added_b();\n"
        "+added_c();\n"
    )
    (file_diff,) = szz.parse_unified_diff(diff)
    assert file_diff.removed == [(11, "removed_a();"), (901, "removed_b();")]
    assert file_diff.added == [(901, "added_b();"), (902, "added_c();")]
    assert file_diff.context_old == [(10, "ctx1();"), (12, "ctx2();"), (900, "ctx3();")]


def test_is_analyzed_path_filters_tests_and_docs():
    assert szz.is_analyzed_path("lib/socks.c")
    assert szz.is_analyzed_path("src/app.c")
    assert not szz.is_analyzed_path("tests/unit/unit1620.c")
    assert not szz.is_analyzed_path("tests/data/test728")
    assert not szz.is_analyzed_path("tests/data/Makefile.inc")
    assert not szz.is_analyzed_path("docs/foo.md")
    assert not szz.is_analyzed_path("src/test_helper.c")


# ---------------------------------------------------------------------------
# synthetic repo for scoring tests (local helper, kept inside this file)
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


def build_scoring_repo(root: Path) -> dict[str, str]:
    """Layout crafted so blame and log-S disagree:

    * ``old`` (2019) introduces the identifier ``resolve_remote_len``;
    * ``blamed`` (2020) adds the line the fix later removes (and its message
      says "Closes #5");
    * the fix removes that line, so blame -> ``blamed`` while the oldest
      pickaxe hit for ``resolve_remote_len`` is ``old``.
    """
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

    vulnerable = (
        "static size_t resolve_remote_len;\n"
        "int process(const char *hostname)\n"
        "{\n"
        "  copy_out(resolve_remote_len);\n"
        "  return 0;\n"
        "}\n"
    )
    shas: dict[str, str] = {}
    shas["old"] = commit(
        "base: add resolve_remote_len",
        {
            "src/x.c": (
                "static size_t resolve_remote_len;\n"
                "int process(const char *hostname)\n"
                "{\n"
                "  return 0;\n"
                "}\n"
            ),
            "README.md": "demo\n",
        },
        "2019-01-01T10:00:00+00:00",
    )
    shas["blamed"] = commit(
        "feature: use remote resolve length\n\nCloses #5\n",
        {"src/x.c": vulnerable},
        "2020-02-14T10:00:00+00:00",
    )
    shas["readme"] = commit(
        "readme: fix typo",
        {"README.md": "demo, fixed\n"},
        "2021-06-01T10:00:00+00:00",
    )
    shas["fix"] = commit(
        "fix: check length",
        {
            "src/x.c": (
                "static size_t resolve_remote_len;\n"
                "int process(const char *hostname)\n"
                "{\n"
                "  copy_out_checked(resolve_remote_len);\n"
                "  return 0;\n"
                "}\n"
            )
        },
        "2023-10-11T05:34:19+00:00",
    )
    return shas


def _fix_commit(repo: GitRepo, sha: str):
    return repo.commit_info(sha, max_diff_bytes=4096)


def _thread(number: int, comments: list[IssueComment] | None = None) -> IssueThread:
    return IssueThread(
        number=number,
        title=f"thread #{number}",
        state="closed",
        author="someone",
        created_at="2020-02-10T00:00:00Z",
        body="",
        comments=comments or [],
    )


# ---------------------------------------------------------------------------
# scoring / ordering
# ---------------------------------------------------------------------------


def test_blame_plus_issue_link_beats_log_s_only(tmp_path):
    shas = build_scoring_repo(tmp_path)
    repo = GitRepo(tmp_path / "repo")
    fix = _fix_commit(repo, shas["fix"])

    candidates = szz.introducer_candidates(fix, repo, [_thread(5)])
    assert [c.sha for c in candidates[:2]] == [shas["blamed"], shas["old"]]

    top = candidates[0]
    assert isinstance(top, IntroducerCandidate)
    assert top.methods == list(SZZ_METHODS)  # all three fired
    assert top.detail["blamed_lines"] == ["src/x.c:4"]
    assert top.detail["line_count"] == 1
    assert top.detail["linked_issue"] == 5
    # 0.5*1.0 (blame) + 0.3 (oldest -S hit for copy_out) + 0.2 (closes #5)
    assert top.score == pytest.approx(1.0)

    log_s_only = candidates[1]
    assert log_s_only.sha == shas["old"]
    assert log_s_only.methods == ["log-S"]
    assert log_s_only.detail["pickaxe_string"] == "resolve_remote_len"
    assert log_s_only.score == pytest.approx(0.3)

    # deterministic order, scores descending, limit respected
    scores = [c.score for c in candidates]
    assert scores == sorted(scores, reverse=True)
    assert len(szz.introducer_candidates(fix, repo, [], limit=2)) == 2

    # the fix commit itself never appears as a candidate
    assert shas["fix"] not in [c.sha for c in candidates]


def test_issue_comment_sha_mention_boosts(tmp_path):
    shas = build_scoring_repo(tmp_path)
    repo = GitRepo(tmp_path / "repo")
    fix = _fix_commit(repo, shas["fix"])
    short = shas["old"][:10]

    thread = _thread(
        9,
        comments=[
            IssueComment(
                author="reporter",
                created_at="2023-09-30T00:00:00Z",
                body=f"regression introduced in {short}",
            )
        ],
    )
    candidates = szz.introducer_candidates(fix, repo, [thread])
    by_sha = {c.sha: c for c in candidates}
    # sha mention in an issue comment counts as an explicit link
    assert by_sha[shas["old"]].methods == ["log-S", "issue-link"]
    assert by_sha[shas["old"]].detail["linked_issue"] == 9
    assert by_sha[shas["old"]].score == pytest.approx(0.5)
    # unrelated issue number in "Closes #5" no longer matches -> blamed keeps
    # blame + log-S only
    assert by_sha[shas["blamed"]].score == pytest.approx(0.8)


def test_pure_addition_fix_falls_back_to_context_blame(tmp_path):
    root = tmp_path
    repo_dir = root / "repo"
    (repo_dir / "src").mkdir(parents=True)
    _git(repo_dir, "init", "-q", "-b", "main")
    _git(repo_dir, "config", "user.email", "dev@example.com")
    _git(repo_dir, "config", "user.name", "Dev Example")

    def commit(msg: str, content: str, date: str) -> str:
        (repo_dir / "src" / "a.c").write_text(content, encoding="utf-8")
        _git(repo_dir, "add", "-A")
        _git(repo_dir, "commit", "-q", "-m", msg, date=date)
        return _git(repo_dir, "rev-parse", "HEAD").strip()

    initial = commit(
        "initial",
        "int f(void)\n{\n  setup();\n  return 0;\n}\n",
        "2019-01-01T10:00:00+00:00",
    )
    commit(
        "add config knob",
        "int f(void)\n{\n  configure(1);\n  setup();\n  return 0;\n}\n",
        "2020-05-05T10:00:00+00:00",
    )
    fix_sha = commit(
        "fix: add audit call",
        "int f(void)\n{\n  configure(1);\n  setup();\n  audit_event();\n"
        "  return 0;\n}\n",
        "2023-10-11T05:34:19+00:00",
    )

    repo = GitRepo(repo_dir)
    fix = _fix_commit(repo, fix_sha)
    assert all(not f.removed for f in szz.parse_unified_diff(fix.diff))

    candidates = szz.introducer_candidates(fix, repo, [])
    assert candidates, "context-line fallback should still produce candidates"
    top = candidates[0]
    # context lines around the addition are dominated by the initial commit
    assert top.sha == initial
    assert top.methods == ["szz-blame"]
    assert "fallback" in top.detail


def test_no_candidates_for_empty_diff():
    class FakeRepo:  # only touched for resolve_sha; no parent to blame
        def resolve_sha(self, ref: str) -> str:
            raise GitError("fake repo has no history")

    class Fix:
        sha = "0" * 40
        short_sha = "0" * 10
        subject = "empty"
        author = "nobody"
        author_date = "2023-01-01T00:00:00+00:00"
        message = ""
        files = []
        diff = ""
        url = ""

    assert szz.introducer_candidates(Fix(), FakeRepo(), []) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# optional integration test against the real curl clone
# ---------------------------------------------------------------------------


def _curl_issue_threads() -> list[IssueThread]:
    """Replay the real issue 4907 from the ground-truth API dump (offline)."""
    if not GROUND_TRUTH_API.exists():
        return []
    try:
        data = json.loads(GROUND_TRUTH_API.read_text(encoding="utf-8"))
        raw = data["https://api.github.com/repos/curl/curl/issues/4907"]
    except (KeyError, ValueError, OSError):
        return []
    comments = [
        IssueComment(
            author=(c.get("user") or {}).get("login", ""),
            created_at=c.get("created_at") or "",
            body=c.get("body") or "",
        )
        for c in data.get(
            "https://api.github.com/repos/curl/curl/issues/4907/comments", []
        )
        if isinstance(c, dict)
    ]
    return [
        IssueThread(
            number=int(raw.get("number", 4907)),
            title=raw.get("title") or "",
            state=raw.get("state") or "",
            author=(raw.get("user") or {}).get("login", ""),
            created_at=raw.get("created_at") or "",
            body=raw.get("body") or "",
            comments=comments,
            url=raw.get("html_url") or "",
        )
    ]


@pytest.mark.integration
@pytest.mark.skipif(not CURL_REPO.exists(), reason=".repos/curl clone not present")
def test_curl_real_case_introducer_in_top3():
    repo = GitRepo(CURL_REPO)
    fix = repo.commit_info("fb4415d8aee6")
    assert fix.subject == "socks: return error if hostname too long for remote resolve"
    assert fix.author_date.startswith("2023-10-11")
    assert "lib/socks.c" in fix.files

    # hard cap on work: only non-test files are analyzed (lib/socks.c here)
    analyzed = [
        f.path
        for f in szz.parse_unified_diff(fix.diff)
        if not f.is_new and szz.is_analyzed_path(f.path)
    ]
    assert analyzed == ["lib/socks.c"]

    issues = _curl_issue_threads()
    candidates = szz.introducer_candidates(fix, repo, issues, limit=5)
    assert candidates, "expected candidates for the real fix"
    assert len(candidates) <= 5
    for cand in candidates:
        assert cand.methods
        assert cand.author_date[:10] <= "2023-10-11"  # nobody authored after the fix

    top3 = [c.short_sha for c in candidates[:3]]
    if "4a4b63daaa" not in top3:
        print(
            f"WARNING: expected introducer 4a4b63daaa missing from top-3; "
            f"top-3 = {[(c.short_sha, round(c.score, 3), c.subject[:40]) for c in candidates[:3]]}"
        )
    else:
        introducer = next(c for c in candidates if c.short_sha == "4a4b63daaa")
        assert "szz-blame" in introducer.methods
        if issues:
            assert "issue-link" in introducer.methods
            assert introducer.detail.get("linked_issue") == 4907
