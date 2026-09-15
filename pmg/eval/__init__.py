"""pmg.eval — piece 4: the evaluation harness (deterministic, AI-free).

Compares a generated postmortem against the real human postmortem of the
case (curl CVE-2023-38545) and produces a metrics report. Every heuristic
is documented in the module docstrings (``compare.py``) and repeated in
each ``Metric.detail`` at runtime, so the report is self-explaining.
"""
from pmg.eval.compare import evaluate
from pmg.eval.ground_truth import GroundTruthError, human_text, sentences
from pmg.eval.ground_truth import load as load_ground_truth
from pmg.eval.report import render_report, save_report

__all__ = [
    "evaluate",
    "render_report",
    "save_report",
    "load_ground_truth",
    "human_text",
    "sentences",
    "GroundTruthError",
]
