"""Ground-truth loading and text preparation for the eval harness (piece 4).

The ground truth is the REAL human postmortem of the case under test (curl
CVE-2023-38545): a JSON file with the verified facts (introducer sha, fix
sha, timeline, action items, root cause) plus optional human-written prose
(advisory.md, blog.md). This module loads and validates the JSON shape and
turns the prose into comparable sentences.

Everything here is deterministic and AI-free; the only text processing is
regex-based sentence splitting and the shared token helpers from
``pmg.contracts``.

Heuristics (documented, deterministic):

- ``load``: ``json.load`` + shape validation. Required keys: ``case``,
  ``introducer.short_sha``, ``fix.short_sha``, ``timeline`` (list),
  ``action_items`` (list), ``root_cause``. Missing keys raise
  ``GroundTruthError`` naming every missing key. ``introducer`` and ``fix``
  may be explicitly ``null`` (issues-only ground truth, e.g. an operational
  incident with no code fix — the JSON documents why). Nulls elsewhere are
  tolerated (the eval treats them as absent data).
- ``human_text``: concatenation of ``advisory.md`` + ``blog.md`` +
  ``postmortem.md`` from the ground-truth directory (in that order) when
  any exist; HTML comments are stripped. Returns ``None`` when the
  directory is not given or none of the files exists.
- ``sentences``: split text on newlines, then on ``[.!?]`` followed by
  whitespace. Drop markdown header lines (``#``), link-only / nav-cruft
  lines (no content tokens left after removing markdown links, bare URLs
  and HTML tags), and fragments whose sorted content tokens join to fewer
  than 40 characters.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pmg.contracts import content_tokens

__all__ = ["GroundTruthError", "load", "human_text", "sentences"]


class GroundTruthError(ValueError):
    """Raised when the ground-truth JSON has a missing/invalid shape."""


# Required top-level keys and (container, leaf) nested keys in ground truth.
_REQUIRED_TOP = ("case", "timeline", "action_items", "root_cause")
_REQUIRED_NESTED = (("introducer", "short_sha"), ("fix", "short_sha"))
_REQUIRED_LISTS = ("timeline", "action_items")

# --- deterministic text helpers -------------------------------------------
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")   # [anchor](target) — whole thing
_URL_RE = re.compile(r"https?://\S+")
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# A sentence fragment must have >= this many characters of (sorted, joined)
# content tokens to be worth comparing.
_MIN_CONTENT_CHARS = 40


def load(path: Path) -> dict:
    """Load and shape-validate a ground-truth JSON file.

    Args:
        path: path to a ground-truth JSON file (see docs/CONTRACTS.md for
            the shape; ``tests/fixtures/ground_truth.sample.json`` is a
            trimmed sample of ``data/ground_truth/ground_truth.json``).

    Returns:
        The parsed dict, unchanged.

    Raises:
        GroundTruthError: if the file is not valid JSON or is missing any
            required key. The message lists ALL missing keys at once.
    """
    raw = Path(path).read_text(encoding="utf-8")
    try:
        gt = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GroundTruthError(f"ground truth {path} is not valid JSON: {exc}") from exc
    if not isinstance(gt, dict):
        raise GroundTruthError(f"ground truth {path} must be a JSON object, got {type(gt).__name__}")

    missing: list[str] = [k for k in _REQUIRED_TOP if k not in gt]
    for container, leaf in _REQUIRED_NESTED:
        if container not in gt:
            missing.append(f"{container}.{leaf}")
            continue
        sub = gt.get(container)
        if sub is None:
            continue  # explicit null = documented absence (issues-only case)
        if not isinstance(sub, dict) or leaf not in sub:
            missing.append(f"{container}.{leaf}")
    if missing:
        raise GroundTruthError(f"ground truth {path} missing required keys: {', '.join(missing)}")

    for key in _REQUIRED_LISTS:
        if not isinstance(gt[key], list):
            raise GroundTruthError(
                f"ground truth {path}: key '{key}' must be a list, got {type(gt[key]).__name__}"
            )
    return gt


def human_text(gt: dict, ground_truth_dir: Path | None = None) -> str | None:
    """Return the human-written postmortem prose, or ``None`` if absent.

    Concatenates ``advisory.md``, ``blog.md`` and ``postmortem.md`` (in that
    order) from ``ground_truth_dir`` when they exist, stripping HTML comments
    and trimming whitespace. ``gt`` is accepted for signature symmetry (the
    file list is fixed) and currently unused.

    Returns ``None`` when the directory is not given or neither file exists.
    """
    if ground_truth_dir is None:
        return None
    parts: list[str] = []
    for name in ("advisory.md", "blog.md", "postmortem.md"):
        p = Path(ground_truth_dir) / name
        if p.is_file():
            text = p.read_text(encoding="utf-8")
            text = _HTML_COMMENT_RE.sub("", text).strip()
            if text:
                parts.append(text)
    if not parts:
        return None
    return "\n\n".join(parts)


def _has_content_tokens(fragment: str) -> bool:
    """True if the fragment keeps any content token after removing markdown
    links (anchor included), bare URLs and HTML tags (link-only/nav cruft)."""
    residue = _URL_RE.sub(" ", _MD_LINK_RE.sub(" ", _HTML_TAG_RE.sub(" ", fragment)))
    return bool(content_tokens(residue))


def sentences(text: str) -> list[str]:
    """Deterministically split ``text`` into comparable sentence fragments.

    Heuristic (see module docstring): split on newlines, then on ``[.!?]``
    followed by whitespace; drop empty lines, markdown headers, link-only /
    nav-cruft lines, and fragments whose sorted content tokens join to
    fewer than ``_MIN_CONTENT_CHARS`` characters.
    """
    out: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not _has_content_tokens(stripped):
            continue
        for fragment in _SENTENCE_SPLIT_RE.split(stripped):
            fragment = fragment.strip()
            if not fragment:
                continue
            if len(" ".join(sorted(content_tokens(fragment)))) < _MIN_CONTENT_CHARS:
                continue
            out.append(fragment)
    return out
