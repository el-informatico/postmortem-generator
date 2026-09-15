"""postmortem-generator — repo-centric incident postmortem generation.

Four pieces (see docs/CONTRACTS.md):
1. ``pmg.collector``  — deterministic evidence collector (no AI).
2. ``pmg.bob``        — IBM Bob Agent-mode orchestration + SRE template (AI layer).
3. ``pmg.shell``      — ``bob postmortem`` CLI + GitHub Action entry point.
4. ``pmg.eval``       — evaluation harness against a real human postmortem.
"""

__version__ = "0.1.0"

# CI note: pushes to pmg/** trigger the smoke workflow, which always runs in
# deterministic mode (no Bobcoin spend) — see .github/workflows/postmortem.yml.
