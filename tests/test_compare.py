"""Tests for pmg.eval.compare.evaluate — every metric's heuristic.

Deterministic and offline: ground truth comes from
tests/fixtures/ground_truth.sample.json, evidence from
tests/fixtures/evidence.sample.json, and postmortems are built directly
via the make_pm helper (no dependency on pieces 1-3).
"""
from __future__ import annotations

import copy

import pytest

from pmg.contracts import METRIC_NAMES, Claim, Evidence
from pmg.eval import evaluate
from test_eval import FIXTURES, load_sample_gt, make_pm, sec


@pytest.fixture()
def gt() -> dict:
    return load_sample_gt()


# ---------------------------------------------------------------------------
# introducer_top1 / introducer_top5
# ---------------------------------------------------------------------------

def test_introducer_top1_exact_short_sha(gt: dict) -> None:
    rep = evaluate(make_pm(), gt)
    assert rep.metric("introducer_top1") is True
    assert rep.metric("introducer_top5") is True


def test_introducer_top1_full_sha_matches_after_sha10(gt: dict) -> None:
    pm = make_pm(
        root_cause=(
            "The flaw was introduced in commit "
            "4a4b63daaaa08d3e5e9dc9e0f7d7b7d3f9952bce (February 2020)."
        )
    )
    rep = evaluate(pm, gt)
    assert rep.metric("introducer_top1") is True


def test_introducer_wrong_sha(gt: dict) -> None:
    pm = make_pm(root_cause="The bug was introduced in commit 9686d94d1a in early 2017.")
    rep = evaluate(pm, gt)
    assert rep.metric("introducer_top1") is False
    assert rep.metric("introducer_top5") is False


def test_introducer_top5_when_sha_listed_fifth(gt: dict) -> None:
    pm = make_pm(
        root_cause=(
            "Candidates: 1111111aaa then 2222222bbb then 3333333ccc then "
            "4444444ddd then finally 4a4b63daaa."
        )
    )
    rep = evaluate(pm, gt)
    assert rep.metric("introducer_top1") is False
    assert rep.metric("introducer_top5") is True


def test_introducer_no_sha_stated(gt: dict) -> None:
    pm = make_pm(root_cause="The origin of the bug remains unattributed to any single change.")
    rep = evaluate(pm, gt)
    assert rep.metric("introducer_top1") is False
    detail = next(m.detail for m in rep.metrics if m.name == "introducer_top1")
    assert "no introducer sha stated" in detail


def test_introducer_with_evidence_fix_sha_quoted_first_still_top1(gt: dict) -> None:
    """The fix sha routinely appears in root_cause before the candidate sha
    (diff excerpt intro) — with evidence supplied, the metric must commit to
    the best-ranked candidate mentioned, not the incidental first token."""
    evidence = Evidence.load(FIXTURES / "evidence.sample.json")
    pm = make_pm(
        root_cause=(
            "The fix diff of fb4415d8ae shows what was fixed. The evidence is "
            "consistent with the bug being introduced in 4a4b63daaa (2020-02-14)."
        )
    )
    rep = evaluate(pm, gt, evidence=evidence)
    assert rep.metric("introducer_top1") is True
    assert rep.metric("introducer_top5") is True


def test_introducer_with_evidence_prefers_best_ranked_candidate(gt: dict) -> None:
    """Several candidates mentioned: the committed introducer is the one with
    the best evidence rank, even when a lower-ranked one is quoted first."""
    evidence = Evidence.load(FIXTURES / "evidence.sample.json")
    pm = make_pm(
        root_cause=(
            "Candidates considered: 9686d94d1a (older, weak) and 4a4b63daaa "
            "(top-ranked). The evidence is consistent with 4a4b63daaa."
        )
    )
    rep = evaluate(pm, gt, evidence=evidence)
    assert rep.metric("introducer_top1") is True


def test_introducer_with_evidence_no_candidate_mentioned_falls_back(gt: dict) -> None:
    evidence = Evidence.load(FIXTURES / "evidence.sample.json")
    pm = make_pm(root_cause="The bug was introduced in commit 9686d94d1a in early 2017.")
    rep = evaluate(pm, gt, evidence=evidence)
    assert rep.metric("introducer_top1") is False


def test_introducer_detail_lists_sha_tokens_considered(gt: dict) -> None:
    pm = make_pm(root_cause="Bisect blames 9686d94d1a and 4a4b63daaa among others.")
    rep = evaluate(pm, gt)
    assert rep.detail["introducer"]["sha_tokens_considered"] == ["9686d94d1a", "4a4b63daaa"]
    assert rep.detail["introducer"]["gt_sha10"] == "4a4b63daaa"
    assert rep.metric("introducer_top1") is False  # wrong sha committed to first
    assert rep.metric("introducer_top5") is True


# ---------------------------------------------------------------------------
# timeline_recall / timeline_precision
# ---------------------------------------------------------------------------

TIMELINE_BODY = (
    "- 2023-01-05: Commit 4a4b63daaa landed in master\n"           # matches gt#1 via sha
    "- 2020-03-12: curl 7.69.0 released with the bug present in the wild\n"  # gt#2: ±1 day + jaccard
    "- 2017-03-01: SOCKS5 remote resolve support was added\n"      # matches nothing
)


def test_timeline_recall_and_precision_exact_fractions(gt: dict) -> None:
    pm = make_pm(timeline=TIMELINE_BODY)
    rep = evaluate(pm, gt)
    # gt#1 (2020-02-14 introducer) matched via sha, gt#2 (2020-03-11 release)
    # matched via date+jaccard, gt#3 (2023-10-11 fix) unmatched.
    assert rep.metric("timeline_recall") == 2 / 3
    assert rep.metric("timeline_precision") == 2 / 3
    table = rep.detail["timeline"]["gt_events"]
    assert len(table) == 3
    assert table[2]["matched_generated"] is None
    assert table[0]["rule"] == "sha match"
    assert table[1]["rule"].startswith("date ±1d")


def test_timeline_date_off_by_30_days_does_not_match(gt: dict) -> None:
    pm = make_pm(timeline="- 2020-04-10: curl 7.69.0 released with the bug everywhere already")
    rep = evaluate(pm, gt)
    assert rep.metric("timeline_recall") == 0.0
    assert rep.metric("timeline_precision") == 0.0


def test_timeline_section_present_but_empty(gt: dict) -> None:
    pm = make_pm(timeline="")
    rep = evaluate(pm, gt)
    assert rep.metric("timeline_recall") == 0.0
    assert rep.metric("timeline_precision") == 0.0
    detail = next(m.detail for m in rep.metrics if m.name == "timeline_precision")
    assert "no generated timeline entries" in detail


# ---------------------------------------------------------------------------
# action_item_overlap
# ---------------------------------------------------------------------------

def test_action_item_overlap_half_covered(gt: dict) -> None:
    gt2 = copy.deepcopy(gt)
    gt2["action_items"] = [
        {"item": "Code audit to detect similar unbounded copies"},
        {"item": "Adopt memory safe languages for new curl components"},
    ]
    pm = make_pm(action_items="- Code audit to detect similar unbounded copies")
    rep = evaluate(pm, gt2)
    assert rep.metric("action_item_overlap") == 0.5
    pairs = rep.detail["action_items"]["pairs"]
    assert pairs[0]["covered"] is True and pairs[0]["best_score"] == 1.0
    assert pairs[1]["covered"] is False and pairs[1]["best_generated"] is None


def test_action_item_overlap_none_when_gt_empty(gt: dict) -> None:
    gt2 = copy.deepcopy(gt)
    gt2["action_items"] = []
    rep = evaluate(make_pm(), gt2)
    assert rep.metric("action_item_overlap") is None


# ---------------------------------------------------------------------------
# root_cause_match
# ---------------------------------------------------------------------------

def test_root_cause_identical_text_scores_one(gt: dict) -> None:
    gt_text = gt["root_cause"]["statement"] + " " + gt["root_cause"]["quote"]
    pm = make_pm(root_cause=sec("root_cause", gt_text))
    rep = evaluate(pm, gt)
    assert rep.metric("root_cause_match") == 1.0


def test_root_cause_unrelated_text_scores_near_zero(gt: dict) -> None:
    pm = make_pm(root_cause="Puppies play in the garden.")
    rep = evaluate(pm, gt)
    assert rep.metric("root_cause_match") < 0.1


# ---------------------------------------------------------------------------
# honesty_check
# ---------------------------------------------------------------------------

def test_honesty_red_badge_with_no_evidence_phrase(gt: dict) -> None:
    rep = evaluate(make_pm(), gt)  # defaults: impact/detection red + "No evidence"
    assert rep.metric("honesty_check") is True


def test_honesty_green_badge_without_external_ref_fails(gt: dict) -> None:
    pm = make_pm(
        impact=sec(
            "impact",
            "Severity was rated high for many deployments.",
            badge="green",
            claims=[Claim("Advisory rates it HIGH", ["advisory"])],
        )
    )
    rep = evaluate(pm, gt)
    assert rep.metric("honesty_check") is False
    assert rep.detail["honesty"]["impact"]["pass"] is False


def test_honesty_green_badge_with_http_ref_passes(gt: dict) -> None:
    pm = make_pm(
        impact=sec(
            "impact",
            "Severity was rated high for many deployments.",
            badge="green",
            claims=[Claim("Advisory rates it HIGH", ["https://curl.se/docs/CVE-2023-38545.html"])],
        )
    )
    assert evaluate(pm, gt).metric("honesty_check") is True


def test_honesty_green_badge_with_external_prefix_ref_passes(gt: dict) -> None:
    pm = make_pm(
        detection=sec(
            "detection",
            "Reported privately to the project.",
            badge="yellow",
            claims=[Claim("Reported 2023-09-30", ["external:advisory"])],
        )
    )
    assert evaluate(pm, gt).metric("honesty_check") is True


def test_honesty_missing_section_fails_and_names_it(gt: dict) -> None:
    rep = evaluate(make_pm(impact=None), gt)
    assert rep.metric("honesty_check") is False
    assert rep.detail["honesty"]["impact"]["reason"] == "section missing"


# ---------------------------------------------------------------------------
# claim_linkage_rate
# ---------------------------------------------------------------------------

def _claim_pm(*claim_specs: tuple[str, list[str]]):
    claims = [Claim(text, refs) for text, refs in claim_specs]
    return make_pm(summary=sec("summary", "Summary body text.", claims=claims))


def test_claim_linkage_strict_mode_with_evidence(gt: dict) -> None:
    ev = Evidence.load(FIXTURES / "evidence.sample.json")
    pm = _claim_pm(
        ("The fix commit closed the overflow.", ["fix"]),
        ("The introducer candidate is 4a4b63daaa.", ["candidate:4a4b63daaa"]),
        ("Issue 999 discussed the flaw.", ["issue:999"]),
    )
    rep = evaluate(pm, gt, evidence=ev)
    assert rep.metric("claim_linkage_rate") == pytest.approx(2 / 3)
    invalid = rep.detail["claim_linkage"]["invalid"]
    assert len(invalid) == 1 and invalid[0]["refs"] == ["issue:999"]


def test_claim_linkage_strict_rejects_empty_and_mixed_refs(gt: dict) -> None:
    ev = Evidence.load(FIXTURES / "evidence.sample.json")
    pm = _claim_pm(
        ("Valid claim.", ["fix"]),
        ("No refs at all.", []),
        ("Mixed valid and invalid refs.", ["fix", "issue:999"]),
    )
    rep = evaluate(pm, gt, evidence=ev)
    assert rep.metric("claim_linkage_rate") == pytest.approx(1 / 3)


def test_claim_linkage_lenient_mode_without_evidence(gt: dict) -> None:
    pm = _claim_pm(("Referenced claim.", ["fix"]), ("Another referenced claim.", ["event:0"]), ("Unreferenced claim.", []))
    rep = evaluate(pm, gt)
    assert rep.metric("claim_linkage_rate") == pytest.approx(2 / 3)
    assert "lenient" in rep.detail["claim_linkage"]["mode"]


def test_claim_linkage_no_claims(gt: dict) -> None:
    rep = evaluate(make_pm(), gt)  # default sections have no claims
    assert rep.metric("claim_linkage_rate") == 0.0


# ---------------------------------------------------------------------------
# line_agreement
# ---------------------------------------------------------------------------

S1 = "The heap overflow occurred in the SOCKS5 proxy handshake code of curl."
S2 = "Daniel Stenberg wrote the vulnerable state machine change back in early 2020."


def test_line_agreement_half(gt: dict) -> None:
    pm = make_pm(markdown="# Postmortem\n\n" + S1 + "\n")
    rep = evaluate(pm, gt, human_text=S1 + " " + S2)
    assert rep.metric("line_agreement") == 0.5
    assert rep.detail["line_agreement"]["total"] == 2
    assert rep.detail["line_agreement"]["matched"] == 1


def test_line_agreement_none_without_human_text(gt: dict) -> None:
    rep = evaluate(make_pm(), gt)
    assert rep.metric("line_agreement") is None


# ---------------------------------------------------------------------------
# wall_clock_seconds
# ---------------------------------------------------------------------------

def test_wall_clock_from_meta(gt: dict) -> None:
    rep = evaluate(make_pm(meta={"wall_clock_seconds": 41.5}), gt)
    assert rep.metric("wall_clock_seconds") == 41.5


def test_wall_clock_absent(gt: dict) -> None:
    assert evaluate(make_pm(), gt).metric("wall_clock_seconds") is None


# ---------------------------------------------------------------------------
# robustness: missing sections never raise; all 10 metrics always present
# ---------------------------------------------------------------------------

def test_missing_sections_never_raise(gt: dict) -> None:
    pm = make_pm(timeline=None, action_items=None, root_cause=None, impact=None, detection=None)
    rep = evaluate(pm, gt)
    assert [m.name for m in rep.metrics] == list(METRIC_NAMES)
    assert rep.metric("timeline_recall") == 0.0
    assert rep.metric("timeline_precision") == 0.0
    assert rep.metric("action_item_overlap") == 0.0
    assert rep.metric("root_cause_match") == 0.0
    assert rep.metric("introducer_top1") is False
    assert rep.metric("honesty_check") is False
    for name in ("timeline_recall", "root_cause_match"):
        detail = next(m.detail for m in rep.metrics if m.name == name)
        assert "section missing" in detail


def test_report_identity_fields(gt: dict) -> None:
    pm = make_pm(generated_by="deterministic-fallback")
    rep = evaluate(pm, gt)
    assert rep.case == "curl-cve-2023-38545"
    assert rep.generated_by == "deterministic-fallback"
