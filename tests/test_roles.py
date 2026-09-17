"""Piece 2 tests — subagent role prompts (offline, no Bob)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pmg.bob.roles import (
    ANALYST_ROLE_IDS,
    SYNTH_ROLE_ID,
    HONESTY_RULES,
    ROLES,
    _analyst_role_ids,
    _DEFAULT_ANALYST_ROLE_IDS,
    build_role_prompt,
)
from pmg.contracts import Evidence

FIXTURE = Path(__file__).parent / "fixtures" / "evidence.sample.json"


@pytest.fixture(scope="module")
def evidence() -> Evidence:
    return Evidence.load(FIXTURE)


@pytest.fixture(scope="module")
def prompts(evidence: Evidence) -> dict[str, str]:
    return {role.id: build_role_prompt(role, evidence) for role in ROLES}


def test_four_roles_with_expected_ids() -> None:
    assert [r.id for r in ROLES] == [
        "commit-archaeologist",
        "document-analyst",
        "code-reviewer",
        "sre-synthesizer",
    ]
    for role in ROLES:
        assert role.slug == role.id  # slug matches .bob/custom_modes.yaml
        assert role.charter and role.inputs and role.output_contract


def test_every_prompt_carries_honesty_rules_and_json_contract(
    prompts: dict[str, str],
) -> None:
    for role_id, prompt in prompts.items():
        assert HONESTY_RULES in prompt, role_id
        assert "Use ONLY the provided evidence" in prompt
        assert "never invent dates, numbers, impact or detection stories" in prompt
        assert "JSON" in prompt


def test_every_prompt_carries_exact_ref_list(prompts: dict[str, str]) -> None:
    for prompt in prompts.values():
        assert "candidate:4a4b63daaa" in prompt  # full evidence.ref_ids() list
        assert "issue:4907#comment:1" in prompt
        assert "event:2" in prompt
        assert "commit:fb4415d8ae" in prompt


def test_commit_archaeologist_prompt(evidence: Evidence) -> None:
    prompt = build_role_prompt(ROLES[0], evidence)
    assert "git history" in prompt.lower()
    assert "4a4b63daaa" in prompt          # candidate sha in the evidence slice
    assert "szz-blame" in prompt           # candidate methods
    assert "0.97" in prompt                # candidate score
    assert "hostname_len" not in prompt    # no raw diff for this role
    assert '"introducer_candidates"' in prompt
    assert '"timeline"' in prompt


def test_document_analyst_prompt(evidence: Evidence) -> None:
    prompt = build_role_prompt(ROLES[1], evidence)
    assert "SOCKS: make the connect phase non-blocking" in prompt  # issue title
    assert "non-blocking SOCKS connect" in prompt                  # issue body
    assert "Fixed in commit 4a4b63daaa" in prompt                  # comment body
    assert '"issues"' in prompt
    assert "hostname_len" not in prompt                            # no diff
    assert '"introducer_candidates"' not in prompt                 # candidates not in slice


def test_code_reviewer_prompt(evidence: Evidence) -> None:
    prompt = build_role_prompt(ROLES[2], evidence)
    assert "fix diff" in prompt.lower()   # charter mentions the diff
    assert "hostname_len > 255" in prompt  # diff hunk present
    assert "@@" in prompt                  # unified diff context
    assert '"fix_commit"' in prompt
    assert '"diff"' in prompt
    assert '"introducer_candidates"' not in prompt  # candidates not in slice
    assert '"issues"' not in prompt


def test_sre_synthesizer_prompt(evidence: Evidence) -> None:
    prompt = build_role_prompt(ROLES[3], evidence)
    assert "4a4b63daaa" in prompt                      # candidates included
    assert "SOCKS: make the connect phase non-blocking" in prompt  # issues included
    assert '"timeline"' in prompt
    assert "hostname_len" not in prompt                # but not the raw diff
    assert "sections" in prompt                        # postmortem-shaped contract
    assert "badge" in prompt


def test_role_partition_analysts_vs_synth() -> None:
    analyst_ids = {r.id for r in ROLES if r.id in ANALYST_ROLE_IDS}
    synth = [r for r in ROLES if r.id == SYNTH_ROLE_ID]
    assert len(analyst_ids) == 3
    assert len(synth) == 1
    assert analyst_ids | {SYNTH_ROLE_ID} == {r.id for r in ROLES}


def test_analyst_role_ids_env_override(monkeypatch) -> None:
    """PMG_ANALYST_ROLES shrinks the fan-out with no code change (sprint
    cut-ladder rung 4, docs/BOBCOIN-BUDGET.md §5); bad ids fail loudly."""
    assert ANALYST_ROLE_IDS == _DEFAULT_ANALYST_ROLE_IDS  # unset -> 3 roles
    monkeypatch.setenv("PMG_ANALYST_ROLES", "document-analyst")
    assert _analyst_role_ids() == ("document-analyst",)
    monkeypatch.setenv("PMG_ANALYST_ROLES", " document-analyst , code-reviewer ")
    assert _analyst_role_ids() == ("document-analyst", "code-reviewer")
    monkeypatch.setenv("PMG_ANALYST_ROLES", "sre-synthesizer")
    with pytest.raises(ValueError, match="unknown role"):
        _analyst_role_ids()
    monkeypatch.setenv("PMG_ANALYST_ROLES", ", ,")
    with pytest.raises(ValueError, match="no role ids"):
        _analyst_role_ids()
