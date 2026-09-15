"""Tests for pmg.eval ground-truth loading, plus the shared make_pm helper
used by test_compare.py and test_report.py.

All tests are deterministic and offline: fixtures live in tests/fixtures/
and Postmortem objects are constructed directly (no dependency on pieces
1-3).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from pmg.contracts import SECTION_IDS, Postmortem, Section
from pmg.eval import ground_truth as gtmod
from pmg.eval.ground_truth import GroundTruthError, human_text, load, sentences

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
REAL_GT_DIR = ROOT / "data" / "ground_truth"


# ---------------------------------------------------------------------------
# shared helpers (imported by test_compare.py / test_report.py)
# ---------------------------------------------------------------------------

DEFAULT_BODIES = {
    "summary": "curl CVE-2023-38545 is a heap overflow in the SOCKS5 proxy handshake.",
    "impact": (
        "No evidence in repository data — impact requires incident telemetry, "
        "alerts or reports."
    ),
    "timeline": (
        "- 2020-01-29: Issue #4907 opened: make SOCKS connect phase non-blocking\n"
        "- 2020-02-14: Commit 4a4b63daaa introduces the SOCKS5 remote-resolve code "
        "later found vulnerable (closes #4907)\n"
        "- 2023-10-11: Commit fb4415d8aee6 fixes the heap overflow (CVE-2023-38545)"
    ),
    "root_cause": (
        "The heap overflow was introduced in commit 4a4b63daaa which made the "
        "SOCKS5 connect phase non-blocking."
    ),
    "detection": (
        "No evidence in repository data — the detection story requires the "
        "advisory or the report itself."
    ),
    "resolution": (
        "Fixed in commit fb4415d8aee6 by returning an error when the hostname "
        "is too long for remote resolve."
    ),
    "action_items": "- Code audit to detect similar unbounded copies",
    "lessons": "State machines whose locals are re-initialized per invocation deserve extra review.",
}

# The default postmortem is HONEST: the honesty sections carry badge "red"
# with a "No evidence" body (repository data cannot ground them).
DEFAULT_BADGES = {"impact": "red", "detection": "red"}


def sec(section_id: str, body: str = "", badge: str = "green", claims=()) -> Section:
    """Build a Section with a title derived from its id."""
    return Section(
        id=section_id,
        title=section_id.replace("_", " ").title(),
        badge=badge,
        body=body,
        claims=list(claims),
    )


def make_pm(**overrides) -> Postmortem:
    """Construct a Postmortem with all 8 sections and honest defaults.

    Overrides: a section id mapped to a Section (used as-is), a body string,
    or None to drop the section; plus ``case``, ``generated_by``, ``title``,
    ``markdown`` and ``meta``.
    """
    sections: list[Section] = []
    for section_id in SECTION_IDS:
        override = overrides.pop(section_id, "...unset...")
        if override is None:
            continue
        if isinstance(override, Section):
            sections.append(override)
        else:
            body = DEFAULT_BODIES[section_id] if override == "...unset..." else str(override)
            sections.append(sec(section_id, body, badge=DEFAULT_BADGES.get(section_id, "green")))
    markdown = overrides.pop(
        "markdown",
        "# Postmortem\n\n"
        + "\n\n".join(f"## {s.id}\n\n{s.body}" for s in sections),
    )
    pm = Postmortem(
        case=overrides.pop("case", "curl-cve-2023-38545"),
        title=overrides.pop("title", "Postmortem: curl CVE-2023-38545"),
        generated_by=overrides.pop("generated_by", "test-generator"),
        sections=sections,
        markdown=markdown,
        meta=overrides.pop("meta", {}),
    )
    assert not overrides, f"unknown make_pm overrides: {sorted(overrides)}"
    return pm


def load_sample_gt() -> dict:
    return json.loads((FIXTURES / "ground_truth.sample.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# ground_truth.load
# ---------------------------------------------------------------------------

def test_load_accepts_sample() -> None:
    gt = load(FIXTURES / "ground_truth.sample.json")
    assert gt["case"] == "curl-cve-2023-38545"
    assert gt["introducer"]["short_sha"] == "4a4b63daaa"
    assert isinstance(gt["timeline"], list) and len(gt["timeline"]) == 3


def test_load_accepts_real_ground_truth() -> None:
    gt = load(REAL_GT_DIR / "ground_truth.json")
    assert gt["case"] == "curl-cve-2023-38545"
    assert gt["fix"]["short_sha"] == "fb4415d8aee6"


def test_load_reports_every_missing_key(tmp_path: Path) -> None:
    gt = load_sample_gt()
    del gt["root_cause"]
    del gt["introducer"]["short_sha"]
    p = tmp_path / "gt.json"
    p.write_text(json.dumps(gt), encoding="utf-8")
    with pytest.raises(GroundTruthError) as exc:
        load(p)
    assert "root_cause" in str(exc.value)
    assert "introducer.short_sha" in str(exc.value)


def test_load_rejects_non_json(tmp_path: Path) -> None:
    p = tmp_path / "gt.json"
    p.write_text("not json {", encoding="utf-8")
    with pytest.raises(GroundTruthError):
        load(p)


def test_load_rejects_non_list_timeline(tmp_path: Path) -> None:
    gt = load_sample_gt()
    gt["timeline"] = {"date": "2020-02-14"}
    p = tmp_path / "gt.json"
    p.write_text(json.dumps(gt), encoding="utf-8")
    with pytest.raises(GroundTruthError) as exc:
        load(p)
    assert "timeline" in str(exc.value)


# ---------------------------------------------------------------------------
# ground_truth.human_text
# ---------------------------------------------------------------------------

def test_human_text_concatenates_files_and_strips_html_comments(tmp_path: Path) -> None:
    (tmp_path / "advisory.md").write_text(
        "<!-- fetched 2026 -->\nAdvisory text about the heap overflow.", encoding="utf-8"
    )
    (tmp_path / "blog.md").write_text("Blog text about the postmortem.", encoding="utf-8")
    text = human_text({"case": "x"}, tmp_path)
    assert text is not None
    assert "<!--" not in text
    assert "Advisory text about the heap overflow." in text
    assert "Blog text about the postmortem." in text
    assert text.index("Advisory") < text.index("Blog")


def test_human_text_none_when_no_dir_or_no_files(tmp_path: Path) -> None:
    assert human_text({"case": "x"}) is None
    assert human_text({"case": "x"}, tmp_path) is None  # dir exists, files do not


def test_human_text_survives_one_file_only(tmp_path: Path) -> None:
    (tmp_path / "blog.md").write_text("Only the blog exists.", encoding="utf-8")
    assert human_text({"case": "x"}, tmp_path) == "Only the blog exists."


def test_human_text_on_real_ground_truth_dir() -> None:
    text = human_text({"case": "curl-cve-2023-38545"}, REAL_GT_DIR)
    assert text is not None
    assert "CVE-2023-38545" in text
    assert "<!--" not in text


# ---------------------------------------------------------------------------
# ground_truth.sentences
# ---------------------------------------------------------------------------

def test_sentences_drops_headers_short_and_link_only_lines() -> None:
    text = "\n".join(
        [
            "# CVE-2023-38545 advisory page header",
            "Short line.",
            "[some anchor](https://example.com/only-link)",
            "https://example.com/bare/urlonly",
            (
                "The advisory explains the heap buffer overflow in detail. "
                "The blog describes how the SOCKS5 handshake bug happened!"
            ),
        ]
    )
    result = sentences(text)
    assert len(result) == 2
    assert result[0].startswith("The advisory explains")
    assert result[1].startswith("The blog describes")


def test_sentences_keeps_link_text_lines_with_real_content() -> None:
    text = (
        "Read the official curl advisory description of the SOCKS5 hostname "
        "overflow before upgrading deployments."
    )
    assert sentences(text) == [text]


def test_sentences_empty_and_none_safe() -> None:
    assert sentences("") == []
    assert sentences("\n\n# only a header\n") == []


def test_module_docstring_documents_heuristics() -> None:
    # the harness must stay self-documenting for judges
    assert "40" in gtmod.__doc__  # min content-token chars threshold documented
    assert "advisory.md" in gtmod.__doc__
