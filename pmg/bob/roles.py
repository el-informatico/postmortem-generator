"""Piece 2 — Bob subagent roles for postmortem generation.

IBM Bob 2.0 has no native subcommand mechanism and its built-in subagents
come in ``explore``/``general`` flavors only, so each role here is realized
twice:

* as a prompt builder for a dedicated ``bob run --chat-mode=<slug> --format
  json`` process launched in parallel by the orchestrator (clean context per
  role — docs/research/ibm-bob-notes.md sections 2-3), and
* as a custom Bob chat mode in ``.bob/custom_modes.yaml`` with the same
  slug/charter.

Every role receives ONLY its relevant slice of the ``Evidence`` plus the full
list of valid evidence reference ids; the honesty rules are binding.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from pmg.contracts import Evidence

# code-reviewer sees the fix diff truncated to ~8000 chars
DIFF_MAX_CHARS = 8000

# Binding rules sentence — must appear verbatim in every role prompt.
HONESTY_RULES = (
    "Use ONLY the provided evidence. Every claim MUST carry refs from the "
    "provided ref list. If evidence is missing for something, say "
    "'No evidence' — never invent dates, numbers, impact or detection "
    "stories. Output ONLY valid JSON per the output contract."
)

ANALYST_OUTPUT_CONTRACT = (
    '{"findings": [{"text": "<one factual claim>", "refs": ["<evidence ref id>"]}], '
    '"confidence_notes": "<what the evidence supports and what it does not>"}'
)

SYNTH_OUTPUT_CONTRACT = (
    '{"case": "<case name>", "title": "<postmortem title>", "sections": '
    '[{"id": "<one of summary|impact|timeline|root_cause|detection|'
    'resolution|action_items|lessons>", "title": "<section title>", '
    '"badge": "<green|yellow|red>", "body": "<markdown body>", '
    '"claims": [{"text": "<claim>", "refs": ["<evidence ref id>"]}]}]} '
    "— badges: green = every claim carries a valid evidence ref; "
    "yellow = grounded but some claims lack refs; red = no evidence, the "
    "body must say 'No evidence' and the section must make no claims. "
    "impact and detection are red unless the provided evidence actually "
    "contains them."
)

SYNTH_ROLE_ID = "sre-synthesizer"
_DEFAULT_ANALYST_ROLE_IDS = ("commit-archaeologist", "document-analyst", "code-reviewer")


@dataclass(frozen=True)
class RoleDef:
    """Declarative definition of one subagent role (Bob custom chat mode)."""

    id: str                      # stable role id (also the mode slug key)
    slug: str                    # Bob chat-mode slug (.bob/custom_modes.yaml)
    name: str                    # human/mode display name
    charter: str                 # what this role does and does not do
    inputs: tuple[str, ...]      # evidence slice names the role receives
    output_contract: str         # JSON shape the role must emit


ROLES: list[RoleDef] = [
    RoleDef(
        id="commit-archaeologist",
        slug="commit-archaeologist",
        name="Commit Archaeologist",
        charter=(
            "Dig through git history around the fix commit. Identify which "
            "commit(s) most likely introduced the bug the fix addresses: "
            "when the vulnerable code entered the repository, why it was "
            "added (commit messages, linked issues), and rank the introducer "
            "candidates using the provided SZZ-lite signals "
            "(methods/score/blamed lines). Do not speculate beyond the "
            "provided commits and timeline."
        ),
        inputs=("introducer_candidates", "fix_commit", "timeline"),
        output_contract=ANALYST_OUTPUT_CONTRACT,
    ),
    RoleDef(
        id="document-analyst",
        slug="document-analyst",
        name="Document Analyst",
        charter=(
            "Read the linked issue thread and any advisories or "
            "decision-record documents in the evidence. Establish what was "
            "asked, what was decided, and what was reported — as document "
            "understanding, quoting the documents. Do not infer repository "
            "state that is not written in the documents."
        ),
        inputs=("issues",),
        output_contract=ANALYST_OUTPUT_CONTRACT,
    ),
    RoleDef(
        id="code-reviewer",
        slug="code-reviewer",
        name="Code Reviewer",
        charter=(
            "Review the fix diff with repository context. Establish what "
            "exactly changed in the fix commit, why the change addresses "
            "the bug described in the evidence, and what residual risk the "
            "change leaves open. Ground every statement in the provided "
            "diff and commit metadata only."
        ),
        inputs=("fix_commit",),
        output_contract=ANALYST_OUTPUT_CONTRACT,
    ),
    RoleDef(
        id="sre-synthesizer",
        slug="sre-synthesizer",
        name="SRE Synthesizer",
        charter=(
            "Merge the analyst findings and the evidence into the SRE "
            "postmortem template. Every section carries an honesty badge, "
            "every claim links to evidence refs, and sections without "
            "evidence say 'No evidence' instead of inventing content. "
            "impact and detection come out red unless the evidence truly "
            "contains them."
        ),
        inputs=("introducer_candidates", "fix_commit", "issues", "timeline"),
        output_contract=SYNTH_OUTPUT_CONTRACT,
    ),
]

ROLE_BY_ID: dict[str, RoleDef] = {r.id: r for r in ROLES}


def _analyst_role_ids() -> tuple[str, ...]:
    """The analyst roles to fan out on (default: all three).

    Overridable without code changes via the PMG_ANALYST_ROLES env var
    (comma-separated role ids) — the low-quota contingency from the sprint
    cut ladder (docs/BOBCOIN-BUDGET.md §5 rung 4):
    ``PMG_ANALYST_ROLES=document-analyst`` runs the cheap 2-role curl
    configuration. Read once at import time, so set it before launch.
    """
    env = os.environ.get("PMG_ANALYST_ROLES", "").strip()
    if not env:
        return _DEFAULT_ANALYST_ROLE_IDS
    ids = tuple(part.strip() for part in env.split(",") if part.strip())
    if not ids:
        raise ValueError("PMG_ANALYST_ROLES is set but contains no role ids")
    unknown = [i for i in ids if i not in _DEFAULT_ANALYST_ROLE_IDS]
    if unknown:
        raise ValueError(
            f"PMG_ANALYST_ROLES has unknown role id(s) {unknown}; "
            f"valid analyst roles: {list(_DEFAULT_ANALYST_ROLE_IDS)}"
        )
    return ids


ANALYST_ROLE_IDS = _analyst_role_ids()


def _truncate(text: str, limit: int) -> str:
    """Truncate *text* to *limit* chars with an explicit marker."""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [diff truncated at %d chars]" % limit


def _fix_commit_dict(evidence: Evidence, include_diff: bool) -> dict[str, Any] | None:
    """Fix commit as a dict; diff only for the code-reviewer (truncated).

    ``None`` for issues-only cases (no fix commit in repository data) — the
    prompt then carries an explicit null and the role must not invent a fix.
    """
    if evidence.fix_commit is None:
        return None
    d = evidence.fix_commit.to_dict()
    if include_diff:
        d["diff"] = _truncate(d.get("diff", ""), DIFF_MAX_CHARS)
    else:
        d.pop("diff", None)
    return d


def evidence_slice(role: RoleDef, evidence: Evidence) -> dict[str, Any]:
    """Build the evidence slice relevant to *role* (no invention anywhere).

    commit-archaeologist: candidates + fix commit (no diff) + timeline;
    document-analyst: issue threads; code-reviewer: fix commit incl. the
    diff truncated to ~DIFF_MAX_CHARS chars; sre-synthesizer: everything
    except the raw diff.
    """
    slice_: dict[str, Any] = {}
    for name in role.inputs:
        if name == "fix_commit":
            slice_["fix_commit"] = _fix_commit_dict(
                evidence, include_diff=(role.id == "code-reviewer")
            )
        elif name == "introducer_candidates":
            slice_["introducer_candidates"] = [
                c.to_dict() for c in evidence.introducer_candidates
            ]
        elif name == "issues":
            slice_["issues"] = [i.to_dict() for i in evidence.issues]
        elif name == "timeline":
            slice_["timeline"] = [e.to_dict() for e in evidence.timeline]
    if role.id == SYNTH_ROLE_ID:
        slice_["case"] = evidence.case.to_dict()
        slice_["meta"] = evidence.meta
    return slice_


def build_role_prompt(role: RoleDef, evidence: Evidence) -> str:
    """Render the full prompt for *role* over *evidence*.

    The prompt contains the charter, the honesty rules (verbatim), the exact
    list of valid evidence reference ids, the JSON output contract and the
    role's evidence slice as JSON.
    """
    ref_list = sorted(evidence.ref_ids())
    slice_json = json.dumps(evidence_slice(role, evidence), indent=2)
    return (
        "You are {name}, a subagent role in the postmortem-generation "
        "pipeline for case {case}.\n"
        "\n"
        "## Charter\n{charter}\n"
        "\n"
        "## Binding rules\n{rules}\n"
        "\n"
        "## Valid evidence reference ids (the ONLY refs a claim may carry)\n"
        "{refs}\n"
        "\n"
        "## Output contract (your entire reply is ONE valid JSON object)\n"
        "{contract}\n"
        "\n"
        "## Evidence\n"
        "```json\n{slice}\n```\n"
        "\n"
        "Analyze the evidence above and reply with the JSON object defined "
        "by the output contract, nothing else."
    ).format(
        name=role.name,
        case=evidence.case.name,
        charter=role.charter,
        rules=HONESTY_RULES,
        refs=", ".join(ref_list),
        contract=role.output_contract,
        slice=slice_json,
    )
