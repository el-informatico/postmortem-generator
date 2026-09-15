"""Piece 2 tests — orchestrators: deterministic fallback + Bob plumbing.

Fully offline: the real ``bob`` binary does NOT exist on this machine, which
is exactly the auto-fallback path under test. Bob-side logic is tested via
the parse/normalize functions directly, never by shelling out.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pmg.bob import (
    BobOrchestrator,
    BobUnavailableError,
    DeterministicOrchestrator,
    generate_postmortem,
    normalize_postmortem,
    parse_bob_result,
    render_markdown,
    validate_linkage,
)
from pmg.contracts import (
    NO_EVIDENCE_PHRASE,
    SECTION_IDS,
    Evidence,
    Postmortem,
)

FIXTURE = Path(__file__).parent / "fixtures" / "evidence.sample.json"


@pytest.fixture(scope="module")
def evidence() -> Evidence:
    return Evidence.load(FIXTURE)


@pytest.fixture(scope="module")
def det_pm(evidence: Evidence) -> Postmortem:
    return DeterministicOrchestrator(evidence).generate()


# -- (a) deterministic orchestrator -----------------------------------------


def test_deterministic_all_eight_sections_canonical_order(det_pm: Postmortem) -> None:
    assert [s.id for s in det_pm.sections] == list(SECTION_IDS)
    assert det_pm.generated_by == "deterministic-fallback"
    assert det_pm.case == "curl-cve-2023-38545"


def test_deterministic_honesty_sections_red_no_claims(det_pm: Postmortem) -> None:
    for sid in ("impact", "detection"):
        section = det_pm.section(sid)
        assert section is not None
        assert section.badge == "red"
        assert NO_EVIDENCE_PHRASE in section.body
        assert section.claims == []


def test_deterministic_impact_says_why_no_evidence(det_pm: Postmortem) -> None:
    impact = det_pm.section("impact")
    detection = det_pm.section("detection")
    assert "telemetry" in impact.body
    assert "not recorded" in detection.body


def test_deterministic_timeline_one_claim_per_event(det_pm: Postmortem, evidence: Evidence) -> None:
    timeline = det_pm.section("timeline")
    assert timeline is not None
    assert timeline.badge == "green"
    assert len(timeline.claims) == len(evidence.timeline)
    for claim in timeline.claims:
        assert any(r.startswith("event:") for r in claim.refs)
    dates = [c.text.split(" — ")[0] for c in timeline.claims]
    assert dates == sorted(dates)
    assert "**2023-10-11**" in timeline.body  # dated markdown list


def test_deterministic_root_cause_mentions_top_candidate(det_pm: Postmortem) -> None:
    rc = det_pm.section("root_cause")
    assert rc is not None
    assert rc.badge == "yellow"
    assert "4a4b63daaa" in rc.body
    assert "consistent with the bug being introduced in 4a4b63daaa" in rc.body
    assert "hostname_len > 255" in rc.body  # key diff lines quoted


def test_deterministic_summary_resolution_green_grounded(det_pm: Postmortem) -> None:
    summary = det_pm.section("summary")
    resolution = det_pm.section("resolution")
    assert summary.badge == "green" and resolution.badge == "green"
    assert "fb4415d8ae" in summary.body
    assert "lib/socks.c" in resolution.body


def test_deterministic_action_items_grounded(det_pm: Postmortem) -> None:
    ai = det_pm.section("action_items")
    assert ai is not None
    # fixture fix files include tests/unit/unit1620.c + tests/data/test728
    assert len(ai.claims) >= 1
    assert len(ai.claims) <= 3
    assert any("unit1620" in c.text for c in ai.claims)
    assert any("#4907" in c.text for c in ai.claims)  # linked issue exists
    assert all(c.refs for c in ai.claims)


def test_deterministic_lessons_latency_from_candidate(det_pm: Postmortem) -> None:
    lessons = det_pm.section("lessons")
    assert lessons is not None
    assert lessons.badge == "yellow"
    assert "candidate evidence suggests ~" in " ".join(
        c.text for c in lessons.claims
    ).lower() or "Candidate evidence suggests ~" in " ".join(
        c.text for c in lessons.claims
    )


def test_deterministic_meta_and_markdown(det_pm: Postmortem) -> None:
    assert "generated_at" in det_pm.meta
    assert det_pm.meta["wall_clock_seconds"] >= 0.0
    assert det_pm.meta["generator"] == "deterministic-fallback"
    assert det_pm.meta["evidence_notes"]  # evidence meta notes passthrough
    assert det_pm.markdown.strip()
    assert render_markdown(det_pm).strip()
    assert "🟢" in det_pm.markdown and "🔴" in det_pm.markdown


def test_deterministic_honesty_invariant_every_claim_valid(
    det_pm: Postmortem, evidence: Evidence
) -> None:
    """Every deterministic claim must link to valid evidence — rate 1.0."""
    report = validate_linkage(det_pm, evidence)
    assert report.total_claims > 0
    assert report.valid_claims == report.total_claims
    assert report.rate == 1.0
    assert report.invalid == []


# -- (b) auto mode falls back offline ----------------------------------------


def test_auto_mode_falls_back_deterministic(
    evidence: Evidence, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOB_API_KEY", raising=False)
    pm = generate_postmortem(evidence, mode="auto")
    assert pm.generated_by == "deterministic-fallback"
    assert pm.meta["fallback_reason"]  # bob absent on this machine
    assert "bob binary not found" == pm.meta["fallback_reason"]
    assert [s.id for s in pm.sections] == list(SECTION_IDS)


def test_deterministic_mode_explicit(evidence: Evidence) -> None:
    pm = generate_postmortem(evidence, mode="deterministic")
    assert pm.generated_by == "deterministic-fallback"
    assert "fallback_reason" not in pm.meta


def test_unknown_mode_raises(evidence: Evidence) -> None:
    with pytest.raises(ValueError):
        generate_postmortem(evidence, mode="nope")


# -- (c) bob mode raises when unavailable ------------------------------------


def test_bob_mode_raises_binary_missing(
    evidence: Evidence, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOB_API_KEY", raising=False)
    with pytest.raises(BobUnavailableError) as excinfo:
        generate_postmortem(
            evidence, mode="bob", bob_bin="definitely-not-a-bob-binary"
        )
    assert excinfo.value.reason == "bob binary not found"


def test_bob_orchestrator_preflight_api_key_missing(
    evidence: Evidence, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOB_API_KEY", raising=False)
    orch = BobOrchestrator(evidence, bob_bin="env", api_key=None)  # env exists
    with pytest.raises(BobUnavailableError) as excinfo:
        orch.generate()
    assert excinfo.value.reason == "BOB_API_KEY not set"


def test_bob_unavailable_error_carries_reason() -> None:
    err = BobUnavailableError("boom")
    assert err.reason == "boom"
    assert isinstance(err, RuntimeError)


# -- (d) parse + normalize (no shelling out) ---------------------------------


def test_parse_bob_result_envelope_with_fenced_last_message() -> None:
    payload = {
        "findings": [{"text": "socks fix landed", "refs": ["fix"]}],
        "confidence_notes": "high",
    }
    envelope = {
        "type": "result",
        "status": "success",
        "stats": {"task_id": "t1", "total_tokens": 12, "session_costs": 0.1},
        "last_message": "```json\n" + json.dumps(payload) + "\n```",
    }
    assert parse_bob_result(json.dumps(envelope)) == payload


def test_parse_bob_result_bare_last_message() -> None:
    envelope = {
        "type": "result",
        "stats": {},
        "last_message": json.dumps({"findings": [], "confidence_notes": "n"}),
    }
    assert parse_bob_result(json.dumps(envelope))["findings"] == []


def test_parse_bob_result_dict_last_message() -> None:
    envelope = {"last_message": {"findings": []}}
    assert parse_bob_result(json.dumps(envelope)) == {"findings": []}


def test_parse_bob_result_unparseable() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_bob_result("total garbage, not json")
    assert str(excinfo.value).startswith("unparseable bob output:")
    assert "total garbage" in str(excinfo.value)


def test_parse_bob_result_missing_last_message() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_bob_result(json.dumps({"type": "result", "stats": {}}))
    assert str(excinfo.value).startswith("unparseable bob output:")


def _fake_synth_payload() -> dict:
    return {
        "case": "curl-cve-2023-38545",
        "title": "Postmortem: SOCKS5 heap overflow",
        "sections": [
            {
                "id": "summary",
                "title": "Summary",
                "badge": "green",
                "body": "A fix landed.",
                "claims": [{"text": "Fix landed.", "refs": ["fix"]}],
            },
            {
                "id": "impact",
                "title": "Impact",
                "badge": "green",
                "body": "No users were affected.",  # model invention attempt
                "claims": [{"text": "zero users affected", "refs": ["fix"]}],
            },
            # detection omitted entirely
            {
                "id": "mystery-section",  # unknown id -> folded into lessons
                "title": "Mystery",
                "badge": "purple",  # invalid badge
                "body": "Stray analysis note.",
                "claims": [],
            },
        ],
    }


def test_normalize_inserts_missing_honesty_sections_red(evidence: Evidence) -> None:
    pm = normalize_postmortem(_fake_synth_payload(), evidence)
    assert [s.id for s in pm.sections] == list(SECTION_IDS)
    detection = pm.section("detection")
    assert detection is not None
    assert detection.badge == "red"
    assert NO_EVIDENCE_PHRASE in detection.body
    assert detection.claims == []


def test_normalize_forces_invented_impact_to_red(evidence: Evidence) -> None:
    pm = normalize_postmortem(_fake_synth_payload(), evidence)
    impact = pm.section("impact")
    assert impact is not None
    assert impact.badge == "red"          # repo evidence cannot ground impact
    assert NO_EVIDENCE_PHRASE in impact.body
    assert impact.claims == []            # red sections make no claims
    # the model's invented impact story is discarded, not kept as body text
    assert "No users were affected" not in impact.body


def test_normalize_badges_clamped_and_unknown_ids_folded_to_lessons(
    evidence: Evidence,
) -> None:
    pm = normalize_postmortem(_fake_synth_payload(), evidence)
    lessons = pm.section("lessons")
    assert lessons is not None
    assert "Stray analysis note." in lessons.body  # unknown section folded in
    for section in pm.sections:
        assert section.badge in ("green", "yellow", "red")
    summary = pm.section("summary")
    assert summary is not None
    assert summary.badge == "green"  # valid badge untouched
    assert summary.claims[0].refs == ["fix"]


def test_normalize_produces_markdown_and_meta(evidence: Evidence) -> None:
    pm = normalize_postmortem(_fake_synth_payload(), evidence, meta={"x": 1})
    assert pm.generated_by == "ibm-bob-agents"
    assert pm.markdown.strip()
    assert pm.meta["x"] == 1
    assert pm.meta["generator"] == "ibm-bob-agents"
