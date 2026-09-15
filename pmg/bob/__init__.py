"""Piece 2 — IBM Bob Agent-mode orchestration + SRE template (pmg.bob).

Public API (see docs/CONTRACTS.md):

* :func:`generate_postmortem` — mode dispatch (auto | bob | deterministic).
* :data:`ROLES` / :func:`build_role_prompt` — the 4 subagent roles.
* :func:`render_markdown` — SRE template rendering with honesty badges.
* :func:`validate_linkage` — claim -> evidence linkage report.
"""

from pmg.bob.linkage import validate_linkage
from pmg.bob.orchestrator import (
    BobOrchestrator,
    BobUnavailableError,
    DeterministicOrchestrator,
    generate_postmortem,
    normalize_postmortem,
    parse_bob_result,
)
from pmg.bob.roles import ROLES, RoleDef, build_role_prompt
from pmg.bob.template import (
    BADGE_LINES,
    SECTION_GUIDANCE,
    SECTION_TITLES,
    render_markdown,
)

__all__ = [
    "generate_postmortem",
    "ROLES",
    "build_role_prompt",
    "render_markdown",
    "validate_linkage",
    "DeterministicOrchestrator",
    "BobOrchestrator",
    "BobUnavailableError",
    "RoleDef",
    "normalize_postmortem",
    "parse_bob_result",
    "SECTION_TITLES",
    "SECTION_GUIDANCE",
    "BADGE_LINES",
]
