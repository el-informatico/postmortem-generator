"""Structural checks for .github/workflows/postmortem.yml (piece 3) and the
scripts/bob-postmortem.sh wrapper.

What this honestly verifies: the file exists, uses spaces only, and carries
the markers the CI design depends on. When PyYAML is installed the file is
additionally parsed as YAML and the trigger/job/step structure is asserted.
It does NOT prove GitHub would accept or run the workflow — only a real
Actions run shows that.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # string-check fallback only
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "postmortem.yml"
WRAPPER = REPO_ROOT / "scripts" / "bob-postmortem.sh"

REQUIRED_MARKERS = (
    "workflow_dispatch:",
    "upload-artifact",
    "BOB_API_KEY",
    "GITHUB_TOKEN",
    "fetch-depth: 0",
    "pip install -e .",
    ".repos/curl",
)


def test_workflow_file_exists():
    assert WORKFLOW.is_file()


def test_workflow_required_markers_present():
    text = WORKFLOW.read_text(encoding="utf-8")
    for marker in REQUIRED_MARKERS:
        assert marker in text, f"missing workflow marker: {marker}"
    assert "\t" not in text, "workflow YAML must not mix tabs into indentation"


@pytest.mark.skipif(yaml is None, reason="PyYAML not installed; string checks only")
def test_workflow_yaml_structure():
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)

    # PyYAML (YAML 1.1) parses the `on:` key as boolean True.
    triggers = doc.get(True) or doc.get("on") or {}
    assert "workflow_dispatch" in triggers
    assert "push" in triggers
    assert triggers["push"]["branches"] == ["main"]
    assert "data/cases/**" in triggers["push"]["paths"]

    inputs = triggers["workflow_dispatch"]["inputs"]
    assert inputs["case"]["default"] == "data/cases/curl-cve-2023-38545.json"
    assert inputs["subject_repo_url"]["default"] == "https://github.com/curl/curl"
    assert inputs["mode"]["default"] == "auto"
    assert set(inputs["mode"]["options"]) == {"auto", "bob", "deterministic"}
    assert inputs["offline"]["default"] is False

    job = doc["jobs"]["postmortem"]
    steps = job["steps"]
    assert len(steps) >= 5

    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["fetch-depth"] == 0  # full history of the workflow repo

    setup = next(s for s in steps if str(s.get("uses", "")).startswith("actions/setup-python"))
    assert setup["with"]["python-version"] == "3.12"

    install = next(s for s in steps if "pip install -e ." in s.get("run", ""))
    assert install is not None

    run_step = next(s for s in steps if "bob-postmortem postmortem" in s.get("run", ""))
    assert "--case" in run_step["run"]
    assert "--local-repo .repos/curl" in run_step["run"]
    assert "GITHUB_TOKEN" in run_step["env"]
    assert "BOB_API_KEY" in run_step["env"]

    upload = next(s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact"))
    assert upload["with"]["name"] == "postmortem"
    assert "eval-output" in str(upload["with"]["path"])


def test_bob_postmortem_wrapper_is_executable():
    """scripts/bob-postmortem.sh exists, is chmod +x, and delegates to the
    console script (IBM Bob has no native subcommand mechanism)."""
    assert WRAPPER.is_file()
    assert os.access(WRAPPER, os.X_OK), "run: chmod +x scripts/bob-postmortem.sh"
    text = WRAPPER.read_text(encoding="utf-8")
    assert text.startswith("#!"), "wrapper needs a shebang"
    assert 'exec bob-postmortem postmortem "$@"' in text
