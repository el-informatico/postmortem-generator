# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. SPDX-License-Identifier:
# Apache-2.0 — see the LICENSE file at the repository root.
"""Tests for scripts/build_ui.py — the offline single-file demo UI (piece 5).

Runs fully offline: against a synthesized tmp fixture (always) and against the
real committed curl output (skipped when eval-output/ is absent).

Add the scripts/ dir to sys.path the same way other tests import across files.
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = PROJECT_ROOT / "scripts" / "build_ui.py"

_spec = importlib.util.spec_from_file_location("build_ui", _SCRIPT)
assert _spec is not None and _spec.loader is not None
build_ui = importlib.util.module_from_spec(_spec)
sys.modules["build_ui"] = build_ui
_spec.loader.exec_module(build_ui)

REAL_CASE_DIR = PROJECT_ROOT / "eval-output" / "curl-cve-2023-38545"
REAL_GT_DIR = PROJECT_ROOT / "data" / "ground_truth"

_URL_RE = re.compile(r"https?://[^\s\"'<>)\\]+")


# ---------------------------------------------------------------------------
# synthesized fixture
# ---------------------------------------------------------------------------

def _section(sid: str, title: str, badge: str, body: str, claims: list[dict]) -> dict:
    return {"id": sid, "title": title, "badge": badge, "body": body, "claims": claims}


FIXTURE_PM = {
    "case": "fixture-case",
    "title": "Fixture: something broke in the socks path",
    "generated_by": "deterministic-fallback",
    "sections": [
        _section("summary", "Summary", "green", "Case **fixture-case**: fixed by `abc1234567`.", [
            {"text": "Fixed by commit abc1234567.", "refs": ["fix", "commit:abc1234567"]},
        ]),
        _section("impact", "Impact", "red",
                 "No evidence in repository data — impact needs telemetry. This section makes no claims.", []),
        _section("timeline", "Timeline", "green", "", [
            {"text": "2024-01-01 — Candidate introducer commit feed0000: introduce bug",
             "refs": ["event:0", "candidate:feed0000"]},
            {"text": "2024-05-01 — Issue #7 opened by r: the bug", "refs": ["event:1", "issue:7"]},
            {"text": "2024-05-05 — Fix commit abc1234567: fix the thing", "refs": ["event:2", "fix"]},
        ]),
        _section("detection", "Detection", "red",
                 "No evidence in repository data — how it was found is not recorded in git.", []),
        _section("resolution", "Resolution", "green", "Fixed in commit abc1234567.", [
            {"text": "Files changed: a.py.", "refs": ["commit:abc1234567"]},
        ]),
    ],
    "markdown": "unused-by-ui",
    "meta": {"generated_at": "2026-09-15T00:00:00+00:00", "wall_clock_seconds": 0.5,
             "generator": "deterministic-fallback"},
}

FIXTURE_EV = {
    "case": {"name": "fixture-case", "repo": "example/demo", "issues": [7],
             "fix_sha": "abc1234567", "local_repo": "", "expected_introducer_sha": "feed0000"},
    "fix_commit": {
        "sha": "abc1234567deadbeef000000000000000000ffff", "short_sha": "abc1234567",
        "subject": "fix the thing", "author": "A Dev", "author_date": "2024-05-05T10:00:00+00:00",
        "message": "fix the thing", "files": ["a.py"], "diff": "diff --git a/a.py",
        "url": "https://github.com/example/demo/commit/abc1234567deadbeef",
    },
    "issues": [{"number": 7, "title": "the bug", "state": "closed", "author": "r",
                "created_at": "2024-05-01T00:00:00Z", "body": "it broke", "comments": [],
                "url": ""}],
    "introducer_candidates": [
        {"sha": "feed00000000000000000000000000000000beef", "short_sha": "feed0000",
         "subject": "introduce bug", "author": "B Dev", "author_date": "2024-01-01T09:00:00+00:00",
         "methods": ["szz-blame"], "score": 0.6, "detail": {}},
    ],
    "timeline": [
        {"date": "2024-01-01", "kind": "commit", "description": "Candidate introducer commit feed0000: introduce bug",
         "ref": "candidate:feed0000"},
        {"date": "2024-05-01", "kind": "issue", "description": "Issue #7 opened by r: the bug", "ref": "issue:7"},
        {"date": "2024-05-05", "kind": "commit", "description": "Fix commit abc1234567: fix the thing", "ref": "fix"},
    ],
    "meta": {"collected_at": "2026-09-15T00:00:00Z", "offline": True, "sources": [], "notes": ""},
}

FIXTURE_EVAL = {
    "case": "fixture-case", "generated_by": "deterministic-fallback",
    "metrics": [
        {"name": "introducer_top1", "value": True, "detail": "sha match"},
        {"name": "timeline_recall", "value": 0.66, "detail": "2/3"},
        {"name": "honesty_check", "value": True, "detail": "both red"},
        {"name": "claim_linkage_rate", "value": 1.0, "detail": "5/5"},
    ],
    "detail": {"dropped": "by the builder"},
}

FIXTURE_HUMAN = """<!--
Source: https://example.com/human-postmortem
Cached for offline evaluation.
-->

# Human postmortem

We **investigated** for ninety minutes and [found the cause](https://example.com/doc).

- item one
- item two

DISTINCTIVE-HUMAN-SENTENCE with <script>alert(1)</script> injection attempt.
"""


def make_fixture(root: Path) -> tuple[Path, Path]:
    """Create eval-output/fixture-case + ground truth; return (eval_dir, gt_dir)."""
    case_dir = root / "eval-output" / "fixture-case"
    case_dir.mkdir(parents=True)
    (case_dir / "postmortem.json").write_text(json.dumps(FIXTURE_PM, indent=1), encoding="utf-8")
    (case_dir / "evidence.json").write_text(json.dumps(FIXTURE_EV, indent=1), encoding="utf-8")
    (case_dir / "eval_report.json").write_text(json.dumps(FIXTURE_EVAL, indent=1), encoding="utf-8")
    gt_dir = root / "gt"
    (gt_dir / "fixture-case").mkdir(parents=True)
    (gt_dir / "fixture-case" / "human.md").write_text(FIXTURE_HUMAN, encoding="utf-8")
    (gt_dir / "fixture-case" / "notes.md").write_text("provenance notes must be excluded", encoding="utf-8")
    return root / "eval-output", gt_dir


def run_build(tmp_path: Path, out_name: str = "index.html", cases: str = "fixture-case",
              eval_dir: Path | None = None, gt_dir: Path | None = None) -> Path:
    if eval_dir is None or gt_dir is None:
        eval_dir, gt_dir = make_fixture(tmp_path)
    out = tmp_path / out_name
    rc = build_ui.main(["--cases", cases, "--eval-dir", str(eval_dir),
                        "--ground-truth", str(gt_dir), "--out", str(out)])
    assert rc == 0
    return out


# ---------------------------------------------------------------------------
# generic page invariants
# ---------------------------------------------------------------------------

def assert_no_external_resources(html: str) -> None:
    """The page must fetch nothing from the network: no external scripts,
    stylesheets, images, imports or font/url() references."""
    for pattern in ('<script src=', '<link ', "@import", "url(http", "srcset=",
                    "<img ", "<iframe", "<source "):
        assert pattern not in html, f"external-resource pattern leaked: {pattern}"


def assert_urls_from_data_only(html: str, input_texts: list[str]) -> None:
    """Every http(s) URL in the output must be a GitHub link (built from case
    data) or appear verbatim in the build inputs (human text carries its own
    source links)."""
    import html as html_mod

    allowed = set()
    for text in input_texts:
        allowed.update(_URL_RE.findall(text))
    for url in set(_URL_RE.findall(html_mod.unescape(html))):
        assert url in allowed or url.startswith("https://github.com/"), f"unexpected URL: {url}"


def extract_case_blob(html: str, case: str) -> dict:
    m = re.search(
        rf'<script type="application/json" id="case-{re.escape(case)}">(.*?)</script>',
        html, re.S,
    )
    assert m, f"case JSON blob missing for {case}"
    return json.loads(m.group(1))


# ---------------------------------------------------------------------------
# fixture tests
# ---------------------------------------------------------------------------

def test_build_fixture_basic(tmp_path: Path) -> None:
    out = run_build(tmp_path)
    assert out.is_file()
    html = out.read_text(encoding="utf-8")
    assert "fixture-case" in html
    assert html.count('class="tl-item') == 3  # one per evidence timeline event
    assert "provenance notes must be excluded" not in html  # notes.md excluded
    blob = extract_case_blob(html, "fixture-case")
    assert blob["repo"] == "example/demo"
    assert len(blob["evidence"]["timeline"]) == 3
    assert "markdown" not in blob["postmortem"]  # slimmed
    assert "diff" not in blob["evidence"]["fix_commit"]


def test_build_fixture_honesty_sections_red(tmp_path: Path) -> None:
    html = run_build(tmp_path).read_text(encoding="utf-8")
    for sid in ("impact", "detection"):
        m = re.search(rf'<section class="pm-section b-(\w+)" data-section="{sid}">', html)
        assert m and m.group(1) == "red", f"{sid} must carry a red badge"
    assert "No evidence" in html


def test_build_fixture_human_markdown_present_and_safe(tmp_path: Path) -> None:
    html = run_build(tmp_path).read_text(encoding="utf-8")
    assert "DISTINCTIVE-HUMAN-SENTENCE" in html          # side-by-side human text
    assert "<script>alert" not in html                    # injection escaped...
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html  # ...not dropped
    assert "<strong>investigated</strong>" in html        # bold
    assert "<li>item one</li>" in html                    # lists
    assert '<a href="https://example.com/doc"' in html    # links
    assert "cached from <a href=" in html                 # provenance line


def test_build_fixture_metrics_rows_match_eval_json(tmp_path: Path) -> None:
    html = run_build(tmp_path).read_text(encoding="utf-8")
    rows = re.findall(r'<tr data-metric="([^"]+)">', html)
    assert rows == [m["name"] for m in FIXTURE_EVAL["metrics"]]
    assert "✓ pass" in html and "0.66" in html
    assert "claim linkage 100%" in html  # header pill from claim_linkage_rate


def test_build_fixture_header_meta(tmp_path: Path) -> None:
    html = run_build(tmp_path).read_text(encoding="utf-8")
    assert "generator: deterministic-fallback" in html
    assert "generated in 500 ms" in html        # wall_clock_seconds = 0.5
    assert build_ui.HUMAN_BASELINE in html      # shown when wall clock present


def test_build_fixture_ref_resolution(tmp_path: Path) -> None:
    html = run_build(tmp_path).read_text(encoding="utf-8")
    cand_sha = FIXTURE_EV["introducer_candidates"][0]["sha"]
    fix_url = FIXTURE_EV["fix_commit"]["url"]
    # candidate ref -> real GitHub commit URL for the candidate sha
    assert f"https://github.com/example/demo/commit/{cand_sha}" in html
    # issue ref without explicit url -> issues/<n> link derived from the repo
    assert 'data-href="https://github.com/example/demo/issues/7"' in html
    # fix chip uses the commit url carried by the evidence
    assert f'href="{fix_url}"' in html
    # fix + top introducer candidate are visually distinguished
    assert "is-fix" in html and "is-top" in html


def test_build_deterministic_byte_identical(tmp_path: Path) -> None:
    eval_dir, gt_dir = make_fixture(tmp_path)
    out1 = run_build(tmp_path, "a.html", eval_dir=eval_dir, gt_dir=gt_dir)
    out2 = run_build(tmp_path, "b.html", eval_dir=eval_dir, gt_dir=gt_dir)
    assert out1.read_bytes() == out2.read_bytes()


def test_build_fixture_offline_no_external_resources(tmp_path: Path) -> None:
    html = run_build(tmp_path).read_text(encoding="utf-8")
    assert_no_external_resources(html)
    inputs = [FIXTURE_HUMAN, json.dumps(FIXTURE_EV), json.dumps(FIXTURE_PM)]
    assert_urls_from_data_only(html, inputs)


def test_build_multi_case_switcher(tmp_path: Path) -> None:
    eval_dir, gt_dir = make_fixture(tmp_path)
    second = eval_dir / "second-case"
    second.mkdir()
    pm2 = dict(FIXTURE_PM, case="second-case",
               sections=[_section("summary", "Summary", "green", "Second case body.", [])])
    (second / "postmortem.json").write_text(json.dumps(pm2), encoding="utf-8")
    (second / "evidence.json").write_text(json.dumps(FIXTURE_EV), encoding="utf-8")

    out = tmp_path / "multi.html"
    rc = build_ui.main(["--eval-dir", str(eval_dir), "--ground-truth", str(gt_dir), "--out", str(out)])
    assert rc == 0
    html = out.read_text(encoding="utf-8")
    assert html.count('class="tab" data-case-tab=') == 2      # tab per case (JS selector excluded)
    assert html.count('<article class="case" data-case-article=') == 2
    assert re.search(r'<article[^>]*data-case-article="second-case"[^>]* hidden', html)  # 2nd hidden
    # exactly one human doc for fixture-case -> no per-doc tabs rendered
    assert html.count("data-doc-tab=") == 0


def test_missing_postmortem_json_fails_clearly(tmp_path: Path, capsys) -> None:
    eval_dir, gt_dir = make_fixture(tmp_path)
    broken = eval_dir / "broken-case"
    broken.mkdir()
    (broken / "evidence.json").write_text(json.dumps(FIXTURE_EV), encoding="utf-8")
    rc = build_ui.main(["--cases", "broken-case", "--eval-dir", str(eval_dir),
                        "--ground-truth", str(gt_dir), "--out", str(tmp_path / "x.html")])
    assert rc != 0
    err = capsys.readouterr().err
    assert "broken-case" in err and "postmortem.json" in err


def test_unknown_case_fails(tmp_path: Path, capsys) -> None:
    eval_dir, gt_dir = make_fixture(tmp_path)
    rc = build_ui.main(["--cases", "nope", "--eval-dir", str(eval_dir),
                        "--ground-truth", str(gt_dir), "--out", str(tmp_path / "x.html")])
    assert rc != 0
    assert "unknown case" in capsys.readouterr().err


def test_no_cases_found_fails(tmp_path: Path, capsys) -> None:
    empty = tmp_path / "eval-output"
    empty.mkdir()
    gt = tmp_path / "gt"
    gt.mkdir()
    rc = build_ui.main(["--eval-dir", str(empty), "--ground-truth", str(gt),
                        "--out", str(tmp_path / "x.html")])
    assert rc != 0
    assert "no cases" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# real curl case (committed pipeline output)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not (REAL_CASE_DIR / "postmortem.json").is_file(),
                    reason="real curl case output not present")
def test_build_real_curl_case(tmp_path: Path) -> None:
    out = tmp_path / "index.html"
    # pin the case under test: the UI embeds EVERY case under eval-output/
    # by default, and the corpus now also carries the secondary cases
    # (log4j, gitlab) whose timelines would change the counts below.
    rc = build_ui.main(["--cases", "curl-cve-2023-38545", "--out", str(out)])
    assert rc == 0
    html = out.read_text(encoding="utf-8")

    evidence = json.loads((REAL_CASE_DIR / "evidence.json").read_text(encoding="utf-8"))
    eval_report = json.loads((REAL_CASE_DIR / "eval_report.json").read_text(encoding="utf-8"))

    assert "curl-cve-2023-38545" in html
    # timeline: one track item per evidence event
    assert html.count('class="tl-item') == len(evidence["timeline"]) == 5
    # honesty sections red with "No evidence"
    for sid in ("impact", "detection"):
        m = re.search(rf'<section class="pm-section b-(\w+)" data-section="{sid}">', html)
        assert m and m.group(1) == "red"
    assert "No evidence" in html
    # human baseline side-by-side: blog + advisory text present
    assert "How I made a heap overflow in curl" in html
    assert "Project curl Security Advisory" in html
    # metrics rows == metrics in the eval json
    rows = re.findall(r'<tr data-metric="([^"]+)">', html)
    assert rows == [m["name"] for m in eval_report["metrics"]]
    assert len(rows) == 10
    # header meta
    assert "generator: deterministic-fallback" in html
    assert "200 µs" in html                      # wall_clock_seconds = 0.0002
    assert build_ui.HUMAN_BASELINE in html
    # real evidence links resolve to GitHub
    assert "https://github.com/curl/curl/commit/fb4415d8aee6c1045be932a34fe6107c2f5ed147" in html
    assert "https://github.com/curl/curl/issues/4907" in html or "pull/4907" in html
    # offline single file
    assert_no_external_resources(html)
    gt_texts = [(REAL_GT_DIR / n).read_text(encoding="utf-8")
                for n in ("blog.md", "advisory.md")]
    assert_urls_from_data_only(html, gt_texts + [json.dumps(evidence)])

    # deterministic rebuild
    out2 = tmp_path / "again.html"
    assert build_ui.main(["--cases", "curl-cve-2023-38545", "--out", str(out2)]) == 0
    assert out.read_bytes() == out2.read_bytes()
