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
from pmg.bob import orchestrator
from pmg.contracts import (
    NO_EVIDENCE_PHRASE,
    SECTION_IDS,
    CaseConfig,
    CommitInfo,
    Evidence,
    IntroducerCandidate,
    IssueThread,
    Postmortem,
    ReleaseInfo,
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


def test_deterministic_timeline_milestones(det_pm: Postmortem, evidence: Evidence) -> None:
    timeline = det_pm.section("timeline")
    assert timeline is not None
    assert timeline.badge == "green"
    # narrative curation: milestone entries only, every claim linked to
    # valid evidence ids, dates sorted (UTC-normalized)
    assert len(timeline.claims) >= 1
    valid_ids = evidence.ref_ids()
    for claim in timeline.claims:
        assert claim.refs and set(claim.refs) <= valid_ids
    dates = [c.text.split(" — ")[0] for c in timeline.claims]
    assert dates == sorted(dates)
    # dated markdown list; the fixture fix is authored 2023-10-11T00:00+02:00
    # which normalizes to UTC day 2023-10-10 (GT/GitHub API dates are UTC —
    # the real curl case stays on 2023-10-11)
    assert "**2023-10-10**" in timeline.body
    # lower-ranked SZZ candidates are root-cause material, not timeline rows
    assert "9686d94d1a" not in timeline.body


def test_deterministic_root_cause_mentions_top_candidate(det_pm: Postmortem) -> None:
    rc = det_pm.section("root_cause")
    assert rc is not None
    assert rc.badge == "yellow"
    assert "4a4b63daaa" in rc.body
    assert "consistent with the bug being introduced in 4a4b63daaa" in rc.body
    # the fix's own words for the failure are quoted (message strings or the
    # commit message explanation) — not just our paraphrase
    assert rc.body.count('"') >= 2
    # key diff lines are quoted in the resolution (what changed), not here
    resolution = det_pm.section("resolution")
    assert resolution is not None
    assert "hostname_len > 255" in resolution.body


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


# ---------------------------------------------------------------------------
# narrative helpers + milestone curation (B7)
# ---------------------------------------------------------------------------


class TestNarrativeHelpers:
    def test_diff_message_strings_joins_c_continuations(self) -> None:
        diff = (
            '-      infof(data, "SOCKS5: server resolving disabled for hostnames of "\n'
            '-            "length > 255 [actual len=%zu]", hostname_len);\n'
            '+      failf(data, "SOCKS5: the destination hostname is too long to be "\n'
            '+            "resolved remotely by the proxy.");\n'
        )
        out = orchestrator._diff_message_strings(diff)
        assert out[0] == (
            "+",
            "SOCKS5: the destination hostname is too long to be "
            "resolved remotely by the proxy.",
        )
        assert out[1] == (
            "-",
            "SOCKS5: server resolving disabled for hostnames of "
            "length > 255 [actual len=%zu]",
        )

    def test_diff_message_strings_keeps_args_separate(self) -> None:
        # separate call arguments (no trailing space) never merge
        diff = '+ log("{}", "{}", value, other);\n'
        assert orchestrator._diff_message_strings(diff) == []

    def test_fix_message_segments_paragraphs_and_trailers(self) -> None:
        msg = (
            "socks: return error if hostname too long for remote resolve\n"
            "\n"
            "Prior to this change the state machine attempted to change the "
            "remote resolve to a local resolve. Unfortunately that did not "
            "work as intended and caused a security issue.\n"
            "\n"
            "Bug: https://curl.se/docs/CVE-2023-38545.html\n"
        )
        segs = orchestrator._fix_message_segments(msg)
        assert segs == [
            "Prior to this change the state machine attempted to change "
            "the remote resolve to a local resolve.",
            "Unfortunately that did not work as intended and caused a "
            "security issue.",
        ]

    def test_fix_message_segments_bullets(self) -> None:
        msg = (
            "Restrict LDAP access via JNDI (#608)\n"
            "\n"
            "* Restrict LDAP access via JNDI\n"
            "* Disable most JNDI protocols\n"
            "* LOG4J2-3201 - Limit the protocols JNDI can use by default. "
            "Limit the servers and classes that can be accessed via LDAP.\n"
        )
        segs = orchestrator._fix_message_segments(msg)
        assert "Restrict LDAP access via JNDI" in segs
        assert "Disable most JNDI protocols" not in segs  # < 5 words
        assert any(s.startswith("LOG4J2-3201 - Limit") for s in segs)

    def test_issue_checklist_items(self) -> None:
        body = (
            "Issues and their updates:\n"
            "\n"
            "- :white_check_mark: Update PS1 across all hosts to more "
            "clearly differentiate between hosts and environments (#1094)\n"
            " - sub-bullet detail that must not become an item (#0000)\n"
            "- a plain bullet with no issue reference\n"
            "- :large_orange_diamond: Removal of users by spam should not "
            "hard delete https://gitlab.com/gitlab-org/gitlab-ce/issues/27581\n"
        )
        items = orchestrator._issue_checklist_items(body)
        assert len(items) == 2
        assert items[0].startswith("Update PS1 across all hosts")
        assert items[1].startswith("Removal of users by spam")
        # emoji markers stripped
        assert ":white_check_mark:" not in items[0]

    def test_tag_project(self) -> None:
        assert orchestrator._tag_project("curl-7_69_0") == "curl"
        assert orchestrator._tag_project("log4j-2.15.0") == "log4j"
        assert orchestrator._tag_project("rel/2.15.0") == ""
        assert orchestrator._tag_project("v1.2.3") == ""


def _b7_evidence() -> Evidence:
    """In-memory curl-shaped evidence exercising the B7 curation paths."""
    return Evidence(
        case=CaseConfig(name="curl-cve-2023-38545", repo="curl/curl",
                        issues=[4907], fix_sha="fb4415d8ae"),
        fix_commit=CommitInfo(
            sha="f" * 40, short_sha="fb4415d8ae", subject="socks: return "
            "error if hostname too long for remote resolve",
            author="Jay Satiro", author_date="2023-10-11T05:34:19Z",
            message="subject\n\nbody explaining the change in full sentences\n",
            files=["lib/socks.c", "tests/data/test728"], diff="--- a\n+++ b\n",
            url="https://github.com/curl/curl/commit/x",
            committer_date="2023-10-11T05:34:19Z",
        ),
        issues=[
            IssueThread(
                number=4907, title="socks: make the connect phase "
                "non-blocking", state="closed", author="bagder",
                created_at="2020-02-11T06:38:35Z",
                body="Removes two entries from KNOWN_BUGS.",
                closed_at="2020-02-16T23:09:09Z", merged_at="",
                is_pull_request=True,
            )
        ],
        introducer_candidates=[
            IntroducerCandidate(
                sha="4" * 40, short_sha="4a4b63daaa",
                subject="socks: make the connect phase non-blocking",
                author="Daniel Stenberg",
                author_date="2020-02-14T15:16:54Z",
                methods=["szz-blame", "issue-link"], score=0.7,
                committer_date="2020-02-16T23:08:48Z",
            ),
            IntroducerCandidate(
                sha="a" * 40, short_sha="a304051620",
                subject="lib: more conn->data cleanups",
                author="Someone", author_date="2021-01-18T11:56:50Z",
                methods=["szz-blame"], score=0.5,
            ),
        ],
        releases=[
            ReleaseInfo(
                tag="curl-7_69_0", version="7.69.0", date="2020-03-04",
                contains_sha="4" * 40, role="introducer-candidate",
            ),
            ReleaseInfo(
                tag="curl-8_4_0", version="8.4.0", date="2023-10-11",
                contains_sha="f" * 40, role="fix",
            ),
        ],
        timeline=[],
    )


def test_b7_milestone_curation_merges_push_and_close() -> None:
    pm = DeterministicOrchestrator(_b7_evidence()).generate()
    timeline = pm.section("timeline")
    assert timeline is not None and timeline.badge == "green"
    body = timeline.body

    # push of the top candidate and the same-day PR close share ONE line
    push_line = [ln for ln in body.splitlines() if "pushed" in ln]
    assert len(push_line) == 1
    assert "4a4b63daaa" in push_line[0]
    assert "PR #4907 closed (unmerged)" in push_line[0]
    assert "2020-02-16" in push_line[0]

    # releases named with the tag-derived project prefix
    assert "curl 7.69.0 released" in body
    assert "curl 8.4.0 released" in body

    # lower-ranked candidates never reach the narrative timeline
    assert "a304051620" not in body

    # every claim linked; dates sorted
    valid = _b7_evidence().ref_ids()
    for claim in timeline.claims:
        assert claim.refs and set(claim.refs) <= valid
    dates = [c.text.split(" — ")[0] for c in timeline.claims]
    assert dates == sorted(dates)


def test_b7_action_items_upgrade_and_apply() -> None:
    pm = DeterministicOrchestrator(_b7_evidence()).generate()
    ai = pm.section("action_items")
    assert ai is not None and ai.badge == "yellow"
    texts = [c.text for c in ai.claims]
    assert any(
        t.startswith("Upgrade to curl 8.4.0") for t in texts
    )
    assert any(t.startswith("Apply the patch to your local version") for t in texts)
    assert any("test728" in t for t in texts)  # regression test item
    # all refs valid
    valid = _b7_evidence().ref_ids()
    for claim in ai.claims:
        assert claim.refs and set(claim.refs) <= valid


def test_b7_root_cause_quotes_fix_message() -> None:
    ev = _b7_evidence()
    ev.fix_commit.message = (
        "socks: return error if hostname too long for remote resolve\n"
        "\n"
        "Prior to this change the state machine attempted to change the "
        "remote resolve to a local resolve. Unfortunately that did not work "
        "as intended and caused a security issue.\n"
        "\n"
        "Bug: https://curl.se/docs/CVE-2023-38545.html\n"
    )
    pm = DeterministicOrchestrator(ev).generate()
    rc = pm.section("root_cause")
    assert rc is not None and rc.badge == "yellow"
    assert "The fix commit message explains:" in rc.body
    assert "state machine" in rc.body  # author's own words, quoted
    assert "consistent with the bug being introduced in 4a4b63daaa" in rc.body
