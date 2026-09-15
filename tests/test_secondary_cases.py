"""Secondary real-world cases: issues-only collection + optional-fix semantics.

Covers the two corpus extensions — the GitLab 2017 database outage (an
operational incident with NO fix commit: the "incident without code"
honesty path) and the log4j CVE-2021-44228 case config — against the
optional-fix semantics of the contracts (``CaseConfig.fix_sha`` may be "",
``Evidence.fix_commit`` may be ``None``).

Fully offline: the GitHub cache for the issues-only case is a hand-written
fixture (the real case's cache is hand-seeded from the GitLab.com REST API
because GitHub hosts no such repository — see
data/ground_truth/gitlab-2017-db-outage/NOTES.md), and the deterministic
generator/eval never touch the network.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from pmg.bob import DeterministicOrchestrator, validate_linkage
from pmg.collector import OfflineCacheMiss, collect_case
from pmg.contracts import METRIC_NAMES, CaseConfig, Evidence
from pmg.eval import evaluate
from pmg.eval.ground_truth import load as load_gt

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "data" / "cases"
GT_DIRS = {
    "log4j-cve-2021-44228": ROOT / "data" / "ground_truth" / "log4j-cve-2021-44228",
    "gitlab-2017-db-outage": ROOT / "data" / "ground_truth" / "gitlab-2017-db-outage",
}

API_BASE = "https://api.github.com/repos/gitlab-com/infrastructure"


# ---------------------------------------------------------------------------
# fixture GitHub cache for issue 1684 (hand-written, GitHub issue JSON shape)
# ---------------------------------------------------------------------------


def _write_cache(cache_dir: Path, url: str, body: object) -> None:
    key = hashlib.sha256(url.encode()).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text(
        json.dumps(
            {"url": url, "fetched_at": "2026-09-15T00:00:00Z",
             "status": 200, "body": body, "next_url": ""}
        ),
        encoding="utf-8",
    )


def seed_issue_cache(cache_dir: Path) -> None:
    """Minimal issue #1684 fixture: the issue plus two comments."""
    _write_cache(
        cache_dir,
        f"{API_BASE}/issues/1684",
        {
            "number": 1684,
            "title": "[meta] Listing all issues related to Jan 31st outage "
                     "to track their progress",
            "state": "closed",
            "user": {"login": "ernstvn-gitlab"},
            "created_at": "2017-04-28T01:22:26Z",
            "body": "Tracking all the issues that were spawned from or "
                    "referenced in the Jan 31st outage blog post-mortem.",
            "html_url": "https://gitlab.com/gitlab-com/infrastructure/-/issues/1684",
        },
    )
    _write_cache(
        cache_dir,
        f"{API_BASE}/issues/1684/comments?per_page=100",
        [
            {
                "user": {"login": "jarv"},
                "created_at": "2017-05-02T18:00:00Z",
                "body": "Hourly LVM snapshots (#1098) are live: snapshots are "
                        "now taken every hour instead of once per 24 hours.",
            },
            {
                "user": {"login": "ernstvn-gitlab"},
                "created_at": "2018-01-22T08:55:00Z",
                "body": "Closing: the tracked remediation issues are done or "
                        "superseded (WAL-E replaced the pg_dump-only path).",
            },
        ],
    )


GITLAB_CASE = CaseConfig(
    name="gitlab-2017-db-outage",
    repo="gitlab-com/infrastructure",
    issues=[1684],
    fix_sha="",           # issues-only: no fix commit in repository data
    local_repo="",        # and therefore no local repo required
)


# ---------------------------------------------------------------------------
# (a) issues-only collect_case
# ---------------------------------------------------------------------------


def test_collect_issues_only_case(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    seed_issue_cache(cache)
    evidence = collect_case(GITLAB_CASE, cache, offline=True)

    assert isinstance(evidence, Evidence)
    assert evidence.fix_commit is None
    assert evidence.introducer_candidates == []
    # timeline from the issue + comments only (no fix/candidate events)
    assert [e.kind for e in evidence.timeline].count("issue") == 1
    assert [e.kind for e in evidence.timeline].count("issue-comment") == 2
    assert not any(e.kind == "commit" for e in evidence.timeline)
    dates = [e.date for e in evidence.timeline]
    assert dates == sorted(dates)
    assert dates[0] == "2017-04-28"
    # every event ref is a valid evidence id (no dangling commit refs)
    ids = evidence.ref_ids()
    assert "case" in ids and "issue:1684" in ids
    assert "issue:1684#comment:0" in ids and "issue:1684#comment:1" in ids
    assert not any(r.startswith("commit:") for r in ids)
    for event in evidence.timeline:
        assert event.ref in ids, f"dangling ref {event.ref}"
    # meta records the issues-only reason
    assert "issues-only case (no fix commit in repository data)" in \
        evidence.meta["notes"]
    # no git source, but the (cached) API source is recorded
    assert not any(s.startswith("git:") for s in evidence.meta["sources"])
    assert any(s.startswith("github-api: cached") for s in evidence.meta["sources"])
    # JSON round-trip keeps fix_commit null
    out = tmp_path / "evidence.json"
    evidence.save(out)
    reloaded = Evidence.load(out)
    assert reloaded.fix_commit is None
    assert reloaded.to_dict() == evidence.to_dict()


def test_issues_only_case_needs_no_local_repo_but_respects_cache_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # fix_sha empty -> no local repo is ever opened, even though none exists
    # under the (chdir'd) working directory.
    monkeypatch.chdir(tmp_path)
    cache = tmp_path / "cache"
    seed_issue_cache(cache)
    evidence = collect_case(GITLAB_CASE, cache, offline=True)
    assert evidence.fix_commit is None

    # ...but the GitHub cache must still be warm for the issue thread
    with pytest.raises(OfflineCacheMiss) as excinfo:
        collect_case(GITLAB_CASE, tmp_path / "empty-cache", offline=True)
    assert "/repos/gitlab-com/infrastructure/issues/1684" in str(excinfo.value)


def test_fix_sha_without_repo_still_errors(tmp_path: Path) -> None:
    """fix_sha set but local_repo missing keeps the existing clear error."""
    case = CaseConfig(
        name="x", repo="example/demo", issues=[], fix_sha="deadbeef",
        local_repo=str(tmp_path / "nope"),
    )
    from pmg.collector import CollectorError

    with pytest.raises(CollectorError, match="local repository"):
        collect_case(case, tmp_path / "cache", offline=True)


# ---------------------------------------------------------------------------
# (b) deterministic postmortem over issues-only evidence (honesty path)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def issues_only_evidence(tmp_path_factory: pytest.TempPathFactory) -> Evidence:
    cache = tmp_path_factory.mktemp("cache")
    seed_issue_cache(cache)
    return collect_case(GITLAB_CASE, cache, offline=True)


def test_issues_only_deterministic_postmortem(issues_only_evidence: Evidence) -> None:
    pm = DeterministicOrchestrator(issues_only_evidence).generate()

    # honesty sections stay red with zero claims
    for sid in ("impact", "detection"):
        section = pm.section(sid)
        assert section is not None and section.badge == "red"
        assert "No evidence" in section.body
        assert section.claims == []

    # resolution is RED "No evidence - no fix commit", zero claims
    resolution = pm.section("resolution")
    assert resolution is not None
    assert resolution.badge == "red"
    assert "no fix commit in repository data" in resolution.body.lower()
    assert resolution.claims == []

    # root cause degrades to an issue-thread-derived statement citing issues
    rc = pm.section("root_cause")
    assert rc is not None
    assert "No fix commit exists" in rc.body
    assert rc.claims and all(
        c.refs == ["issue:1684"] for c in rc.claims
    )

    # summary words it as an ops/community-incident reconstruction
    summary = pm.section("summary")
    assert summary is not None
    assert "operational/community incident" in summary.body

    # lessons skips any introducer->fix latency line
    lessons = pm.section("lessons")
    assert lessons is not None
    joined = " ".join(c.text for c in lessons.claims).lower()
    assert "no introducer-to-fix latency" in joined
    assert "candidate evidence suggests ~" not in joined

    # HONESTY INVARIANT: every claim carries valid refs -> rate 1.0
    report = validate_linkage(pm, issues_only_evidence)
    assert report.total_claims > 0
    assert report.rate == 1.0
    assert report.invalid == []


def test_issues_only_deterministic_root_cause_red_without_issues(
    issues_only_evidence: Evidence,
) -> None:
    ev = Evidence(
        case=issues_only_evidence.case, fix_commit=None,
        meta=issues_only_evidence.meta,
    )  # no issues at all -> root cause must be red, not invented
    pm = DeterministicOrchestrator(ev).generate()
    rc = pm.section("root_cause")
    assert rc is not None and rc.badge == "red"
    assert "No evidence" in rc.body
    assert rc.claims == []


# ---------------------------------------------------------------------------
# (c) eval on the issues-only postmortem against ground truth with nulls
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def gitlab_gt() -> dict:
    return load_gt(GT_DIRS["gitlab-2017-db-outage"] / "ground_truth.json")


def test_ground_truth_with_nulls_loads(gitlab_gt: dict) -> None:
    assert gitlab_gt["case"] == "gitlab-2017-db-outage"
    assert gitlab_gt["introducer"] is None
    assert gitlab_gt["fix"] is None
    assert gitlab_gt["duration_in_days_undetected"] is None
    # the JSON documents WHY introducer/fix are null (ops incident)
    assert "no code change" in gitlab_gt["introducer_is_null_because"]
    assert "no fix commit" in gitlab_gt["fix_is_null_because"]


def test_eval_issues_only_all_ten_metrics_no_crash(
    issues_only_evidence: Evidence, gitlab_gt: dict
) -> None:
    pm = DeterministicOrchestrator(issues_only_evidence).generate()
    report = evaluate(pm, gitlab_gt, evidence=issues_only_evidence)

    names = [m.name for m in report.metrics]
    assert names == list(METRIC_NAMES)  # all 10, canonical order
    by_name = {m.name: m for m in report.metrics}
    assert by_name["honesty_check"].value is True
    assert by_name["claim_linkage_rate"].value == 1.0
    intro = by_name["introducer_top1"]
    assert intro.value is False
    assert "no fix commit / no introducer candidates (issues-only case)" \
        in intro.detail
    assert by_name["introducer_top5"].value is False
    # gt timeline/action_items are real lists -> metrics defined and numeric
    assert isinstance(by_name["timeline_recall"].value, float)
    assert isinstance(by_name["action_item_overlap"].value, float)
    # gt root_cause present -> numeric; wall clock from deterministic PM meta
    assert isinstance(by_name["root_cause_match"].value, float)


def test_eval_tolerates_null_gt_root_cause(issues_only_evidence: Evidence) -> None:
    """Null/empty gt root_cause must yield None (undefined), not a crash."""
    pm = DeterministicOrchestrator(issues_only_evidence).generate()
    gt = {"case": "x", "timeline": [], "action_items": [], "root_cause": None,
          "introducer": None, "fix": None}
    report = evaluate(pm, gt, evidence=issues_only_evidence)
    assert report.metric("root_cause_match") is None
    assert report.metric("timeline_recall") is None
    assert report.metric("action_item_overlap") is None


# ---------------------------------------------------------------------------
# (d) the two new case configs load and match their ground truth case names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_file", ["log4j-cve-2021-44228.json", "gitlab-2017-db-outage.json"]
)
def test_case_configs_load_and_match_ground_truth(case_file: str) -> None:
    case = CaseConfig.load(CASES / case_file)
    gt_path = GT_DIRS[case.name] / "ground_truth.json"
    gt = json.loads(gt_path.read_text(encoding="utf-8"))
    assert case.name == gt["case"]
    assert case.repo and "/" in case.repo
    assert case.issues
    assert case.notes  # provenance notes required for corpus cases


def test_log4j_case_config_shape() -> None:
    case = CaseConfig.load(CASES / "log4j-cve-2021-44228.json")
    assert case.repo == "apache/logging-log4j2"
    assert case.fix_sha.startswith("c77b3cb39312b83b")
    assert case.local_repo == ".repos/logging-log4j2"
    assert case.expected_introducer_sha == "f1a0cac60f"
    gt = json.loads(
        (GT_DIRS["log4j-cve-2021-44228"] / "ground_truth.json").read_text(
            encoding="utf-8"
        )
    )
    assert gt["introducer"]["full_sha"].startswith(case.expected_introducer_sha)
    assert gt["fix"]["full_sha"].startswith(case.fix_sha[:10])


def test_gitlab_case_config_is_issues_only() -> None:
    case = CaseConfig.load(CASES / "gitlab-2017-db-outage.json")
    assert case.fix_sha == ""       # EMPTY: ops incident, no fix commit
    assert case.local_repo == ""
    assert case.expected_introducer_sha == ""
