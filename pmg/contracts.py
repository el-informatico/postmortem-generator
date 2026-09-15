"""Shared contracts for the four pieces of postmortem-generator.

This module is the single source of truth for the data shapes that cross
module boundaries. Keep it dependency-free (stdlib only) and stable: the
collector (piece 1), the Bob orchestration (piece 2), the CLI (piece 3) and
the evaluation harness (piece 4) all code against these types.

Serialization convention: every contract object has ``to_dict()`` /
``from_dict()`` and ``save(path)`` / ``load(path)`` round-tripping through
plain JSON, so any piece can be run offline from cached files.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Generic helpers (deterministic, no AI anywhere in contracts/eval)
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[a-z0-9]+")


def normalize_tokens(text: str) -> set[str]:
    """Lowercase word-token set, ignoring punctuation. Deterministic."""
    return set(_WORD_RE.findall(text.lower()))


def jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two token sets; 0.0 for two empty sets."""
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def overlap_ratio(a: set[str], b: set[str]) -> float:
    """|a ∩ b| / |a| — how much of set a is covered by b."""
    if not a:
        return 0.0
    return len(a & b) / len(a)


def sha10(sha: str) -> str:
    """Normalize a commit SHA (full or short) to its first 10 hex chars."""
    return (sha or "").strip().lower()[:10]


STOPWORDS = {
    "the", "a", "an", "of", "to", "in", "and", "or", "for", "on", "is",
    "was", "it", "its", "this", "that", "with", "as", "by", "at", "be",
    "are", "from", "not", "no", "if", "when", "which", "into", "than",
}


def content_tokens(text: str) -> set[str]:
    """normalize_tokens minus stopwords — used by eval text comparison."""
    return normalize_tokens(text) - STOPWORDS


# ---------------------------------------------------------------------------
# Case configuration
# ---------------------------------------------------------------------------


@dataclass
class CaseConfig:
    """One incident case: repo, related issue(s) and the fix commit."""

    name: str                       # e.g. "curl-cve-2023-38545"
    repo: str                       # "owner/name" on GitHub
    issues: list[int]               # GitHub issue numbers related to the case
    fix_sha: str                    # fix commit SHA (short or full)
    local_repo: str = ""            # path to a local clone (offline mode)
    expected_introducer_sha: str = ""  # ground truth; ONLY used by the eval

    # -- persistence --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaseConfig":
        return cls(
            name=d["name"],
            repo=d["repo"],
            issues=list(d.get("issues", [])),
            fix_sha=d["fix_sha"],
            local_repo=d.get("local_repo", ""),
            expected_introducer_sha=d.get("expected_introducer_sha", ""),
        )

    @classmethod
    def load(cls, path: str | Path) -> "CaseConfig":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8"
        )


# ---------------------------------------------------------------------------
# Piece 1 — evidence (collector output)
# ---------------------------------------------------------------------------


@dataclass
class CommitInfo:
    """A git commit with the information the analysis needs."""

    sha: str            # full 40-char sha
    short_sha: str      # <=10 chars, used as ref key
    subject: str
    author: str
    author_date: str    # ISO-8601 (author date, not commit date)
    message: str        # full commit message
    files: list[str]
    diff: str           # `git show` unified diff (may be truncated by caller)
    url: str = ""       # GitHub commit URL when repo is on GitHub

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CommitInfo":
        return cls(**d)


@dataclass
class IssueComment:
    author: str
    created_at: str     # ISO-8601
    body: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IssueComment":
        return cls(**d)


@dataclass
class IssueThread:
    """A GitHub issue with its comment thread (document understanding input)."""

    number: int
    title: str
    state: str
    author: str
    created_at: str     # ISO-8601
    body: str
    comments: list[IssueComment] = field(default_factory=list)
    url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IssueThread":
        return cls(
            number=d["number"],
            title=d["title"],
            state=d["state"],
            author=d["author"],
            created_at=d["created_at"],
            body=d["body"],
            comments=[IssueComment.from_dict(c) for c in d.get("comments", [])],
            url=d.get("url", ""),
        )


# SZZ-lite methods. A candidate is proposed by one or more of these; the
# score combines them (see pmg/collector/szz.py).
SZZ_METHODS = ("szz-blame", "log-S", "issue-link")


@dataclass
class IntroducerCandidate:
    """A commit that may have introduced the bug fixed by the fix commit."""

    sha: str
    short_sha: str
    subject: str
    author: str
    author_date: str    # ISO-8601
    methods: list[str]  # subset of SZZ_METHODS, in confidence order
    score: float        # 0..1 combined confidence
    detail: dict[str, Any] = field(default_factory=dict)
    # detail keys (informational): blamed_lines, pickaxe_string, linked_issue

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IntroducerCandidate":
        return cls(**d)


@dataclass
class TimelineEvent:
    """One dated event reconstructed from repository data only."""

    date: str           # ISO-8601 date (YYYY-MM-DD)
    kind: str           # "commit" | "issue" | "issue-comment" | "release" | "other"
    description: str
    ref: str            # evidence reference id (see Evidence.ref_ids)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TimelineEvent":
        return cls(**d)


@dataclass
class Evidence:
    """Everything the deterministic collector could establish. No AI, no
    invention: fields with no data stay empty, and the postmortem generator
    must declare 'no evidence' for those sections (honesty rule)."""

    case: CaseConfig
    fix_commit: CommitInfo
    issues: list[IssueThread] = field(default_factory=list)
    introducer_candidates: list[IntroducerCandidate] = field(default_factory=list)
    timeline: list[TimelineEvent] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)
    # meta keys: collected_at, offline (bool), sources (list[str]), notes

    # -- evidence reference ids (claim→evidence linkage targets) -----------
    def ref_ids(self) -> set[str]:
        ids = {"fix", "case"}
        ids.update(f"commit:{c.short_sha}" for c in [self.fix_commit])
        ids.update(f"candidate:{c.short_sha}" for c in self.introducer_candidates)
        for issue in self.issues:
            ids.add(f"issue:{issue.number}")
            for k in range(len(issue.comments)):
                ids.add(f"issue:{issue.number}#comment:{k}")
        ids.update(f"event:{i}" for i in range(len(self.timeline)))
        return ids

    # -- persistence --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case.to_dict(),
            "fix_commit": self.fix_commit.to_dict(),
            "issues": [i.to_dict() for i in self.issues],
            "introducer_candidates": [c.to_dict() for c in self.introducer_candidates],
            "timeline": [e.to_dict() for e in self.timeline],
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Evidence":
        return cls(
            case=CaseConfig.from_dict(d["case"]),
            fix_commit=CommitInfo.from_dict(d["fix_commit"]),
            issues=[IssueThread.from_dict(i) for i in d.get("issues", [])],
            introducer_candidates=[
                IntroducerCandidate.from_dict(c)
                for c in d.get("introducer_candidates", [])
            ],
            timeline=[TimelineEvent.from_dict(e) for e in d.get("timeline", [])],
            meta=d.get("meta", {}),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "Evidence":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Piece 2 — postmortem (orchestration output)
# ---------------------------------------------------------------------------

# Stable section ids (SRE-style template, honesty rule baked in).
SECTION_IDS = (
    "summary",        # executive summary
    "impact",         # user/customer impact      -> usually "no evidence" from git
    "timeline",       # reconstructed from repository data
    "root_cause",     # technical root cause + introducer linkage
    "detection",      # how it was found          -> usually "no evidence" from git
    "resolution",     # the fix
    "action_items",   # prevention plan
    "lessons",        # lessons learned / open questions
)

# Sections that repository data alone cannot ground. The generator MUST emit
# them with badge "red" and a body containing "No evidence" unless external
# evidence (advisory, postmortem doc) was ingested. The eval checks this.
HONESTY_SECTIONS = ("impact", "detection")

BADGES = ("green", "yellow", "red")
# green  = every claim carries at least one valid evidence ref
# yellow = grounded overall, but some claims lack refs
# red    = no evidence — section must say so explicitly and make no claims

NO_EVIDENCE_PHRASE = "No evidence"


@dataclass
class Claim:
    """One factual claim in a postmortem section, linked to its evidence."""

    text: str
    refs: list[str] = field(default_factory=list)  # evidence ref ids

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Claim":
        return cls(text=d["text"], refs=list(d.get("refs", [])))


@dataclass
class Section:
    id: str            # one of SECTION_IDS
    title: str
    badge: str         # one of BADGES
    body: str          # markdown body (what a human reads)
    claims: list[Claim] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Section":
        return cls(
            id=d["id"],
            title=d["title"],
            badge=d["badge"],
            body=d["body"],
            claims=[Claim.from_dict(c) for c in d.get("claims", [])],
        )


@dataclass
class Postmortem:
    case: str                      # case name
    title: str
    generated_by: str              # "deterministic-fallback" | "ibm-bob-agents"
    sections: list[Section] = field(default_factory=list)
    markdown: str = ""             # rendered markdown (must exist; contains badges)
    meta: dict[str, Any] = field(default_factory=dict)
    # meta keys: generated_at, wall_clock_seconds, model/orchestrator info

    def section(self, section_id: str) -> Optional[Section]:
        for s in self.sections:
            if s.id == section_id:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "title": self.title,
            "generated_by": self.generated_by,
            "sections": [s.to_dict() for s in self.sections],
            "markdown": self.markdown,
            "meta": self.meta,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Postmortem":
        return cls(
            case=d["case"],
            title=d["title"],
            generated_by=d["generated_by"],
            sections=[Section.from_dict(s) for s in d.get("sections", [])],
            markdown=d.get("markdown", ""),
            meta=d.get("meta", {}),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "Postmortem":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


# ---------------------------------------------------------------------------
# Piece 2b — claim→evidence linkage report (pmg.bob.validate_linkage output)
# ---------------------------------------------------------------------------


@dataclass
class InvalidClaimRef:
    section_id: str
    claim_text: str
    bad_refs: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InvalidClaimRef":
        return cls(**d)


@dataclass
class LinkageReport:
    total_claims: int
    valid_claims: int
    rate: float                  # valid_claims / total_claims (0.0 if none)
    invalid: list[InvalidClaimRef] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "valid_claims": self.valid_claims,
            "rate": self.rate,
            "invalid": [i.to_dict() for i in self.invalid],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LinkageReport":
        return cls(
            total_claims=d["total_claims"],
            valid_claims=d["valid_claims"],
            rate=d["rate"],
            invalid=[InvalidClaimRef.from_dict(i) for i in d.get("invalid", [])],
        )


# ---------------------------------------------------------------------------
# Piece 4 — evaluation report
# ---------------------------------------------------------------------------


@dataclass
class Metric:
    """One evaluation metric. Values are bool/float/str; detail explains how
    it was computed (the harness is deterministic and AI-free by design)."""

    name: str
    value: Any
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Metric":
        return cls(**d)


# Canonical metric names (README metrics table and eval harness must agree):
METRIC_NAMES = {
    "introducer_top1": "Predicted introducer == ground truth (top-1 candidate)",
    "introducer_top5": "Ground-truth introducer appears in top-5 candidates",
    "timeline_recall": "Recall of ground-truth timeline events (date-window + token overlap)",
    "timeline_precision": "Precision of generated timeline events vs ground truth",
    "action_item_overlap": "Coverage of human action items by generated ones (best token match)",
    "root_cause_match": "Token-overlap score of generated root cause vs documented one (0..1)",
    "honesty_check": "impact/detection declared 'No evidence' (red) instead of invented",
    "claim_linkage_rate": "Share of claims with at least one valid evidence ref",
    "line_agreement": "Sentence-level recall over the human postmortem text",
    "wall_clock_seconds": "End-to-end generation time (human baseline: ~90 min)",
}


@dataclass
class EvalReport:
    case: str
    generated_by: str
    metrics: list[Metric] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)
    # detail keys: matched/unmatched timeline events, action item pairs, etc.

    def metric(self, name: str) -> Any:
        for m in self.metrics:
            if m.name == name:
                return m.value
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "case": self.case,
            "generated_by": self.generated_by,
            "metrics": [m.to_dict() for m in self.metrics],
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EvalReport":
        return cls(
            case=d["case"],
            generated_by=d.get("generated_by", ""),
            metrics=[Metric.from_dict(m) for m in d.get("metrics", [])],
            detail=d.get("detail", {}),
        )

    def save(self, path: str | Path) -> None:
        Path(path).write_text(
            json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    @classmethod
    def load(cls, path: str | Path) -> "EvalReport":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
