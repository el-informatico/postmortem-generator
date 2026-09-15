"""Piece 2 tests — claim -> evidence linkage validation (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pmg.bob.linkage import validate_linkage
from pmg.contracts import (
    Claim,
    Evidence,
    Postmortem,
    Section,
)

FIXTURE = Path(__file__).parent / "fixtures" / "evidence.sample.json"


@pytest.fixture(scope="module")
def evidence() -> Evidence:
    return Evidence.load(FIXTURE)


def _pm_with_claims(*claims: Claim, section_id: str = "summary") -> Postmortem:
    return Postmortem(
        case="curl-cve-2023-38545",
        title="t",
        generated_by="deterministic-fallback",
        sections=[
            Section(
                id=section_id,
                title="Summary",
                badge="yellow",
                body="b",
                claims=list(claims),
            )
        ],
    )


def test_all_valid_claims_rate_one(evidence: Evidence) -> None:
    pm = _pm_with_claims(
        Claim(text="a", refs=["fix"]),
        Claim(text="b", refs=["candidate:4a4b63daaa", "commit:fb4415d8ae"]),
        Claim(text="c", refs=["issue:4907#comment:1", "event:2", "case"]),
    )
    report = validate_linkage(pm, evidence)
    assert report.total_claims == 3
    assert report.valid_claims == 3
    assert report.rate == 1.0
    assert report.invalid == []


def test_mixed_claims_exact_rate_and_bad_refs(evidence: Evidence) -> None:
    pm = _pm_with_claims(
        Claim(text="valid", refs=["fix"]),
        Claim(text="bad ref", refs=["fix", "candidate:deadbeef"]),
        Claim(text="empty refs", refs=[]),
    )
    report = validate_linkage(pm, evidence)
    assert report.total_claims == 3
    assert report.valid_claims == 1
    assert report.rate == pytest.approx(1 / 3)
    assert len(report.invalid) == 2
    bad = next(i for i in report.invalid if "bad ref" in i.claim_text)
    assert bad.section_id == "summary"
    assert bad.bad_refs == ["candidate:deadbeef"]
    empty = next(i for i in report.invalid if "empty refs" in i.claim_text)
    assert empty.bad_refs == []  # missing linkage itself is the finding


def test_invalid_refs_reported_per_section(evidence: Evidence) -> None:
    pm = Postmortem(
        case="c",
        title="t",
        generated_by="deterministic-fallback",
        sections=[
            Section(
                id="timeline",
                title="Timeline",
                badge="red",
                body="b",
                claims=[Claim(text="t1", refs=["event:99", "not-a-ref"])],
            ),
            Section(
                id="root_cause",
                title="Root Cause",
                badge="red",
                body="b",
                claims=[Claim(text="t2", refs=["candidate:4a4b63daaa"])],
            ),
        ],
    )
    report = validate_linkage(pm, evidence)
    assert report.total_claims == 2
    assert report.valid_claims == 1
    assert report.rate == 0.5
    assert report.invalid[0].section_id == "timeline"
    assert report.invalid[0].claim_text == "t1"
    assert sorted(report.invalid[0].bad_refs) == ["event:99", "not-a-ref"]


def test_no_claims_rate_zero(evidence: Evidence) -> None:
    pm = _pm_with_claims()
    report = validate_linkage(pm, evidence)
    assert report.total_claims == 0
    assert report.valid_claims == 0
    assert report.rate == 0.0
    assert report.invalid == []
