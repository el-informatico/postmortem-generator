"""Tests for piece 3 — the CLI (pmg.shell.cli).

(a) argument-parsing unit tests run standalone: they monkeypatch
    cli.run_pipeline, so pmg.collector / pmg.bob / pmg.eval are never touched.
(b)/(c) full-pipeline tests import the sibling pieces inside the test
    functions and skip cleanly while those pieces are unfinished
    (_pieces_available()); they run for real once the pieces land.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from pmg.contracts import CaseConfig
from pmg.shell import cli

REPO_ROOT = Path(__file__).resolve().parents[1]
CURL_CASE = REPO_ROOT / "data" / "cases" / "curl-cve-2023-38545.json"


def _pieces_available() -> bool:
    """Guarded import of the sibling pieces; False while they are unfinished.

    Importing e.g. `pmg.collector` alone is not enough — an empty directory
    under a regular package still imports as a namespace package — so the
    public callables themselves are imported.
    """
    try:
        from pmg.bob import generate_postmortem, render_markdown, validate_linkage  # noqa: F401
        from pmg.collector import collect_case  # noqa: F401
        from pmg.eval import evaluate, render_report  # noqa: F401
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# (a) argument parsing
# ---------------------------------------------------------------------------


class TestArgParsing:
    """main() builds the right CaseConfig and defaults; run_pipeline is faked."""

    @staticmethod
    def _capture(monkeypatch) -> dict:
        captured: dict = {}

        def fake_run_pipeline(args, case):
            captured["args"] = args
            captured["case"] = case
            return 0

        monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)
        return captured

    def test_trio_form_builds_caseconfig(self, monkeypatch):
        captured = self._capture(monkeypatch)
        rc = cli.main(
            [
                "postmortem",
                "--repo", "acme/widget",
                "--issue", "7", "--issue", "9",
                "--fix-sha", "deadbeef1234",
            ]
        )
        assert rc == 0
        case = captured["case"]
        assert isinstance(case, CaseConfig)
        assert case.name == "acme/widget-deadbee"  # <repo>-<fixsha7>
        assert case.repo == "acme/widget"
        assert case.issues == [7, 9]
        assert case.fix_sha == "deadbeef1234"
        assert captured["args"].out == "eval-output/acme/widget-deadbee"
        assert captured["args"].mode == "auto"
        assert captured["args"].offline is False
        assert captured["args"].cache_dir == "data/cache"
        assert captured["args"].max_diff_bytes == 200000
        assert captured["args"].skip_eval is False
        assert captured["args"].bob_max_cost is None  # uncapped by default

    def test_bob_max_cost_parsed(self, monkeypatch):
        captured = self._capture(monkeypatch)
        rc = cli.main(
            [
                "postmortem", "--case", str(CURL_CASE),
                "--mode", "bob", "--bob-max-cost", "2.5",
            ]
        )
        assert rc == 0
        assert captured["args"].bob_max_cost == 2.5

    def test_direct_flag_form_matches_subcommand_form(self, monkeypatch):
        captured = self._capture(monkeypatch)
        rc = cli.main(
            ["--repo", "acme/widget", "--issue", "7", "--fix-sha", "deadbeef1234"]
        )
        assert rc == 0
        assert captured["case"].name == "acme/widget-deadbee"
        assert captured["case"].issues == [7]

    def test_case_form_loads_real_curl_case(self, monkeypatch):
        captured = self._capture(monkeypatch)
        rc = cli.main(["postmortem", "--case", str(CURL_CASE)])
        assert rc == 0
        case = captured["case"]
        assert case.name == "curl-cve-2023-38545"
        assert case.repo == "curl/curl"
        assert case.issues == [4907]
        assert case.fix_sha == "fb4415d8aee6"
        assert case.local_repo == ".repos/curl"
        assert captured["args"].out == "eval-output/curl-cve-2023-38545"

    def test_local_repo_overrides_case(self, monkeypatch):
        captured = self._capture(monkeypatch)
        rc = cli.main(
            ["postmortem", "--case", str(CURL_CASE), "--local-repo", "/tmp/curl"]
        )
        assert rc == 0
        assert captured["case"].local_repo == "/tmp/curl"

    @pytest.mark.parametrize(
        "argv",
        [
            ["postmortem"],  # no case source at all
            ["postmortem", "--repo", "acme/widget", "--fix-sha", "abc1234"],  # no --issue
            ["postmortem", "--issue", "1", "--fix-sha", "abc1234"],  # no --repo
            ["postmortem", "--repo", "acme/widget", "--issue", "1"],  # no --fix-sha
            ["postmortem", "--repo", "nowhere", "--issue", "1", "--fix-sha", "abc"],  # not OWNER/NAME
            [  # --case combined with the trio
                "postmortem", "--case", str(CURL_CASE),
                "--repo", "acme/widget", "--issue", "1", "--fix-sha", "abc1234",
            ],
            ["postmortem", "--case", "does/not/exist.json"],  # missing file
            ["postmortem", "--nope"],  # unknown flag
        ],
    )
    def test_bad_args_exit_2(self, argv, monkeypatch):
        # run_pipeline must never be reached; a real call would be loud.
        monkeypatch.setattr(
            cli, "run_pipeline",
            lambda a, c: pytest.fail("run_pipeline reached with bad args"),
        )
        with pytest.raises(SystemExit) as excinfo:
            cli.main(argv)
        assert excinfo.value.code == 2

    def test_help_exits_zero(self, capsys):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["postmortem", "--help"])
        assert excinfo.value.code == 0
        assert "--fix-sha" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Synthetic git repo helper for the E2E tests
# ---------------------------------------------------------------------------


def _git(repo: Path, *git_args: str, date: str | None = None) -> str:
    """Run git in `repo` with a fixed identity (and optional fixed dates).

    Returns stdout of the command.
    """
    env = dict(os.environ)
    env.update(
        GIT_AUTHOR_NAME="Tester",
        GIT_AUTHOR_EMAIL="tester@example.com",
        GIT_COMMITTER_NAME="Tester",
        GIT_COMMITTER_EMAIL="tester@example.com",
    )
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(
        ["git", "-C", str(repo), *git_args],
        check=True, capture_output=True, text=True, env=env,
    )
    return proc.stdout.strip()


def _make_synthetic_repo(repo: Path) -> tuple[str, str]:
    """Three commits: A initial README, B introduces the vulnerable memcpy
    (2020-02-14), C fixes it (2023-10-11). Returns (introducer, fix) full SHAs.
    """
    _git(repo, "init", "-q")
    (repo / "README.md").write_text("# synthetic case\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "chore: initial import")

    src = repo / "src"
    src.mkdir()
    (src / "x.c").write_text(
        '#include <string.h>\n'
        'int resolve(char *dst, const char *host, size_t host_len) {\n'
        '    memcpy(dst, host, host_len);\n'
        '    return 0;\n'
        '}\n',
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "feat: add socks resolve",
         date="2020-02-14T00:00:00")
    introducer = _git(repo, "rev-parse", "HEAD")

    (src / "x.c").write_text(
        '#include <string.h>\n'
        'int resolve(char *dst, const char *host, size_t host_len) {\n'
        '    if (host_len > 255)\n'
        '        return -1;\n'
        '    memcpy(dst, host, host_len);\n'
        '    return 0;\n'
        '}\n',
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fix: bounds check",
         date="2023-10-11T00:00:00")
    fix = _git(repo, "rev-parse", "HEAD")
    return introducer, fix


# ---------------------------------------------------------------------------
# (b) full offline E2E + (c) offline cache miss — need the sibling pieces
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _pieces_available(),
    reason="sibling pieces (pmg.collector/pmg.bob/pmg.eval) not finished yet",
)
def test_offline_e2e_synthetic_repo(tmp_path, capsys):
    """End-to-end offline run over a tiny synthetic repo: exit 0 and all
    artifacts written; the honesty rule shows in postmortem.md."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _introducer, fix = _make_synthetic_repo(repo)

    cfg = tmp_path / "case.json"
    CaseConfig(
        name="synthetic-e2e",
        repo="example/synthetic",
        issues=[],
        fix_sha=fix,
        local_repo=str(repo),
    ).save(cfg)

    gt = tmp_path / "ground_truth.json"
    shutil.copyfile(REPO_ROOT / "tests" / "fixtures" / "ground_truth.sample.json", gt)

    out = tmp_path / "out"
    rc = cli.main(
        [
            "postmortem",
            "--case", str(cfg),
            "--local-repo", str(repo),
            "--offline",
            "--ground-truth", str(gt),
            "--out", str(out),
            "--mode", "deterministic",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0, f"stdout={captured.out}\nstderr={captured.err}"

    for name in ("evidence.json", "postmortem.json", "postmortem.md",
                 "linkage.json", "metrics.md", "eval_report.json"):
        assert (out / name).is_file(), f"missing artifact: {name}"

    markdown = (out / "postmortem.md").read_text(encoding="utf-8")
    assert "No evidence" in markdown  # impact honesty: git has no impact data

    metrics_md = (out / "metrics.md").read_text(encoding="utf-8")
    assert "introducer" in metrics_md.lower()

    assert "postmortem:" in captured.out  # human summary line


@pytest.mark.skipif(
    not _pieces_available(),
    reason="sibling pieces (pmg.collector/pmg.bob/pmg.eval) not finished yet",
)
def test_bob_max_cost_forwarded_to_generator(tmp_path, monkeypatch):
    """--bob-max-cost reaches generate_postmortem as max_cost= for Bob/auto
    runs, and is NOT forwarded for deterministic runs (that orchestrator
    takes no kwargs). The recorder delegates to the deterministic floor so
    the pipeline completes without the bob binary."""
    from pmg.bob import generate_postmortem as real_generate

    repo = tmp_path / "repo"
    repo.mkdir()
    _introducer, fix = _make_synthetic_repo(repo)
    cfg = tmp_path / "case.json"
    CaseConfig(
        name="max-cost-fwd", repo="example/synthetic", issues=[],
        fix_sha=fix, local_repo=str(repo),
    ).save(cfg)

    seen: list[dict] = []

    def recording_generate(evidence, mode="auto", **kwargs):
        seen.append({"mode": mode, **kwargs})
        return real_generate(evidence, mode="deterministic")

    import pmg.bob as bob_mod
    monkeypatch.setattr(bob_mod, "generate_postmortem", recording_generate)

    common = ["postmortem", "--case", str(cfg), "--offline",
              "--skip-eval", "--out", str(tmp_path / "out")]
    rc = cli.main([*common, "--mode", "bob", "--bob-max-cost", "2.5"])
    assert rc == 0
    rc = cli.main([*common, "--mode", "deterministic", "--bob-max-cost", "2.5"])
    assert rc == 0

    assert seen == [
        {"mode": "bob", "max_cost": 2.5},   # forwarded as an orchestrator kwarg
        {"mode": "deterministic"},          # not forwarded (no such kwarg there)
    ]


@pytest.mark.skipif(
    not _pieces_available(),
    reason="sibling pieces (pmg.collector/pmg.bob/pmg.eval) not finished yet",
)
def test_offline_cache_miss_exits_3(tmp_path, capsys):
    """--offline with an empty cache and an issue to fetch -> exit 3 + hint."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _introducer, fix = _make_synthetic_repo(repo)

    cfg = tmp_path / "case.json"
    CaseConfig(
        name="cache-miss",
        repo="example/synthetic",
        issues=[1],  # issue thread must come from the (empty) API cache
        fix_sha=fix,
        local_repo=str(repo),
    ).save(cfg)

    cache = tmp_path / "cache"
    cache.mkdir()

    rc = cli.main(
        [
            "postmortem",
            "--case", str(cfg),
            "--local-repo", str(repo),
            "--offline",
            "--cache-dir", str(cache),
            "--out", str(tmp_path / "out"),
            "--skip-eval",
        ]
    )
    assert rc == 3
    err = capsys.readouterr().err
    assert "refresh_cache" in err  # the actionable hint
