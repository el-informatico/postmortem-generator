"""Tests for pmg.eval.report — markdown rendering and file output."""
from __future__ import annotations

from pathlib import Path

from pmg.contracts import METRIC_NAMES, EvalReport
from pmg.eval import evaluate, render_report, save_report
from test_compare import TIMELINE_BODY
from test_eval import load_sample_gt, make_pm


def _full_report() -> EvalReport:
    gt = load_sample_gt()
    human = (
        "The heap overflow occurred in the SOCKS5 proxy handshake code of curl. "
        "Daniel Stenberg wrote the vulnerable state machine change back in early 2020."
    )
    return evaluate(make_pm(timeline=TIMELINE_BODY, meta={"wall_clock_seconds": 41.567}), gt, human_text=human)


def test_render_contains_all_metric_rows() -> None:
    md = render_report(_full_report())
    assert "| Metric | Description | Value | Notes |" in md
    for name, description in METRIC_NAMES.items():
        assert f"| {name} |" in md
        assert description in md


def test_render_formats_values() -> None:
    report = _full_report()
    report.metric("timeline_recall")  # sanity: computed
    md = render_report(report)
    assert "# Postmortem evaluation: curl-cve-2023-38545" in md
    assert "test-generator" in md                      # generated_by
    assert "introducer: EXACT ✓" in md                 # summary verdict line
    assert "timeline recall 0.67" in md                # float, 2 decimals
    assert "honest: yes" in md
    assert "✓" in md                                   # boolean True rendering
    assert "41.57" in md                               # wall_clock rounded to 2dp


def test_render_none_value_renders_em_dash() -> None:
    md = render_report(evaluate(make_pm(), load_sample_gt()))
    assert "—" in md  # line_agreement undefined without human text


def test_render_detail_sections() -> None:
    md = render_report(_full_report())
    assert "## Detail" in md
    assert "### Timeline match table" in md
    assert "### Action item best pairs" in md
    assert "### Honesty verdicts" in md
    assert "sha10 tokens considered" in md
    assert "sha match" in md


def test_render_ok_with_empty_detail() -> None:
    report = EvalReport(case="x", generated_by="y", metrics=[], detail={})
    md = render_report(report)
    assert "Postmortem evaluation: x" in md
    assert "not computed" in md  # missing metrics are named, not dropped


def test_save_report_writes_both_files(tmp_path: Path) -> None:
    report = _full_report()
    json_path, md_path = save_report(report, tmp_path)
    assert json_path.name == "eval_report.json" and json_path.is_file()
    assert md_path.name == "metrics.md" and md_path.is_file()
    assert md_path.read_text(encoding="utf-8") == render_report(report)
    loaded = EvalReport.load(json_path)
    assert loaded.case == report.case
    assert [m.name for m in loaded.metrics] == [m.name for m in report.metrics]
    assert loaded.metric("introducer_top1") == report.metric("introducer_top1")
    assert loaded.detail["introducer"]["gt_sha10"] == "4a4b63daaa"


def test_save_report_creates_nested_dir(tmp_path: Path) -> None:
    out = tmp_path / "results" / "curl-cve-2023-38545"
    json_path, md_path = save_report(_full_report(), out)
    assert json_path.is_file() and md_path.is_file()
