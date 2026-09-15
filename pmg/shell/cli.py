"""Piece 3 — the ``bob postmortem`` command-line interface.

Console script ``bob-postmortem`` (pyproject ``[project.scripts]``). IBM Bob's
CLI has no native subcommand mechanism (docs/research/ibm-bob-notes.md §3):
custom commands are ``.bob/commands/*.md`` slash commands for ``bob chat``.
The literal ``bob postmortem --repo X --issue N --fix-sha ABC`` UX therefore
ships as this wrapper (see scripts/bob-postmortem.sh for the alias/symlink
trick). The entry point accepts both the explicit subcommand form
``bob-postmortem postmortem ...`` and the direct flag form
``bob-postmortem --repo ...``.

Pipeline (docs/CONTRACTS.md), with per-stage timing on stderr:

    CaseConfig -> pmg.collector.collect_case  -> Evidence
               -> pmg.bob.generate_postmortem -> Postmortem
               -> pmg.bob.validate_linkage    -> LinkageReport
               -> files under --out
               -> pmg.eval.evaluate (when ground truth is found)

The sibling pieces are imported lazily inside run_pipeline so this module
(and its argument-parsing tests) keep working while they are unfinished.

Stdlib only. Exit codes: 0 ok, 2 usage (argparse), 3 offline cache miss,
4 Bob unavailable, 5 unexpected error.
"""
from __future__ import annotations

import argparse
import contextlib
import inspect
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

from pmg.contracts import CaseConfig

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CACHE_MISS = 3
EXIT_BOB_UNAVAILABLE = 4
EXIT_UNEXPECTED = 5

DEFAULT_CACHE_DIR = "data/cache"
DEFAULT_GROUND_TRUTH = Path("data/ground_truth/ground_truth.json")

_BADGE_EMOJI = {"green": "✅", "yellow": "🟡", "red": "🔴"}


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse parser for the ``postmortem`` subcommand."""
    parser = argparse.ArgumentParser(
        prog="bob-postmortem",
        description="Generate an incident postmortem from repository evidence "
        "(deterministic collector -> IBM Bob agents / deterministic fallback "
        "-> evaluation against ground truth).",
        epilog="Exit codes: 0 ok, 2 usage, 3 offline cache miss, 4 Bob "
        "unavailable, 5 unexpected error. Example: "
        "bob-postmortem postmortem --repo curl/curl --issue 4907 "
        "--fix-sha fb4415d8aee6 --local-repo .repos/curl",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{postmortem}")
    p = sub.add_parser(
        "postmortem", help="generate a postmortem for one incident case"
    )
    p.add_argument(
        "--case", metavar="PATH",
        help="case config JSON (alternative to the --repo/--issue/--fix-sha trio)",
    )
    p.add_argument(
        "--repo", metavar="OWNER/NAME",
        help="GitHub repository of the incident (trio form)",
    )
    p.add_argument(
        "--issue", action="append", type=int, metavar="N",
        help="related GitHub issue number (repeat for multiple issues)",
    )
    p.add_argument(
        "--fix-sha", metavar="SHA", help="fix commit SHA, short or full (trio form)"
    )
    p.add_argument(
        "--local-repo", metavar="PATH",
        help="local clone of the subject repo (overrides case.local_repo)",
    )
    p.add_argument(
        "--out", metavar="DIR",
        help="output directory (default: eval-output/<case-name>)",
    )
    p.add_argument(
        "--cache-dir", metavar="DIR", default=DEFAULT_CACHE_DIR,
        help=f"GitHub API disk cache (default: {DEFAULT_CACHE_DIR})",
    )
    p.add_argument(
        "--offline", action="store_true",
        help="never touch the network (the GitHub cache must be warm)",
    )
    p.add_argument(
        "--mode", choices=("auto", "bob", "deterministic"), default="auto",
        help="generation mode (default: auto — use Bob when available, else "
        "the deterministic generator)",
    )
    p.add_argument(
        "--ground-truth", metavar="PATH", default=None,
        help="ground truth JSON for evaluation (default: "
        "data/ground_truth/ground_truth.json when it exists)",
    )
    p.add_argument(
        "--max-diff-bytes", type=int, default=200_000, metavar="N",
        help="truncate commit diffs beyond this many bytes (default: 200000)",
    )
    p.add_argument(
        "--skip-eval", action="store_true",
        help="skip evaluation even when ground truth exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point (console script ``bob-postmortem``); returns exit code."""
    parser = build_parser()
    raw = list(sys.argv[1:] if argv is None else argv)
    # Accept both `bob-postmortem postmortem ...` and the direct flag form:
    # prepend the subcommand unless the caller already spelled it out.
    if not raw or raw[0] != "postmortem":
        raw = ["postmortem", *raw]
    args = parser.parse_args(raw)

    _validate(parser, args)
    case = _build_case(args)
    if not args.out:
        args.out = f"eval-output/{case.name}"
    if args.ground_truth is None and DEFAULT_GROUND_TRUTH.is_file():
        args.ground_truth = str(DEFAULT_GROUND_TRUTH)

    try:
        return run_pipeline(args, case)
    except SystemExit:
        raise
    except Exception as exc:  # CLI boundary: any surprise becomes exit 5
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED


def _validate(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    """Cross-flag validation; usage problems exit 2 via parser.error()."""
    has_trio_part = (
        args.repo is not None or args.issue is not None or args.fix_sha is not None
    )
    if args.case and has_trio_part:
        parser.error("--case cannot be combined with --repo/--issue/--fix-sha")
    if not args.case and not (args.repo and args.issue and args.fix_sha):
        parser.error(
            "provide either --case PATH or all of --repo OWNER/NAME --issue N "
            "--fix-sha SHA"
        )
    if args.repo and "/" not in args.repo:
        parser.error("--repo must look like OWNER/NAME")
    if args.case and not Path(args.case).is_file():
        parser.error(f"--case file not found: {args.case}")
    if args.ground_truth is not None and not Path(args.ground_truth).is_file():
        parser.error(f"--ground-truth file not found: {args.ground_truth}")


def _build_case(args: argparse.Namespace) -> CaseConfig:
    """Load --case, or synthesize a CaseConfig from the trio (name: <repo>-<fixsha7>)."""
    if args.case:
        case = CaseConfig.load(args.case)
    else:
        fix_sha = args.fix_sha.strip()
        case = CaseConfig(
            name=f"{args.repo}-{fix_sha[:7]}",
            repo=args.repo,
            issues=list(args.issue or []),
            fix_sha=fix_sha,
        )
    if args.local_repo:
        case.local_repo = args.local_repo
    return case


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(args: argparse.Namespace, case: CaseConfig) -> int:
    """Run collect -> generate -> linkage -> files -> (optional) eval.

    Sibling pieces (pmg.collector / pmg.bob / pmg.eval) are imported lazily;
    while they are unfinished this raises RuntimeError (main() maps it to 5).
    """
    mods = _import_pieces()
    out_dir = Path(args.out)

    @contextlib.contextmanager
    def stage(name: str) -> Iterator[None]:
        """Time one pipeline stage and report on stderr when it finishes."""
        t0 = time.perf_counter()
        try:
            yield
        finally:
            timings[name] = time.perf_counter() - t0
            print(f"[timing] {name}: {timings[name]:.2f}s", file=sys.stderr)

    timings: dict[str, float] = {}

    # Stage 1 — deterministic evidence collection.
    collect_kwargs: dict[str, Any] = {}
    if "max_diff_bytes" in inspect.signature(mods.collect_case).parameters:
        collect_kwargs["max_diff_bytes"] = args.max_diff_bytes
    try:
        with stage("collect_case"):
            evidence = mods.collect_case(
                case, cache_dir=Path(args.cache_dir),
                offline=bool(args.offline), **collect_kwargs,
            )
    except Exception as exc:
        if _matches(exc, mods.offline_cache_miss_cls, "OfflineCacheMiss"):
            print(f"error: offline cache miss while collecting evidence: {exc}",
                  file=sys.stderr)
            print("hint: run scripts/refresh_cache.py first, or re-run without "
                  "--offline to fetch fresh data", file=sys.stderr)
            return EXIT_CACHE_MISS
        raise

    # Stage 2 — generate (mode passthrough; auto falls back inside pmg.bob).
    with stage("generate_postmortem"):
        try:
            pm = mods.generate_postmortem(evidence, mode=args.mode)
        except Exception as exc:
            if not _matches(exc, mods.bob_unavailable_cls, "BobUnavailableError"):
                raise
            if args.mode == "bob":
                print(f"error: Bob unavailable (explicit --mode bob): {exc}",
                      file=sys.stderr)
                return EXIT_BOB_UNAVAILABLE
            # auto mode should already have fallen back inside pmg.bob; be safe.
            print(f"[fallback] Bob unavailable in auto mode, retrying "
                  f"deterministic: {exc}", file=sys.stderr)
            pm = mods.generate_postmortem(evidence, mode="deterministic")

    # Stage 3 — claim->evidence linkage, then write all artifacts.
    out_dir.mkdir(parents=True, exist_ok=True)
    with stage("validate_linkage"):
        linkage = mods.validate_linkage(pm, evidence)
    with stage("write_outputs"):
        evidence.save(out_dir / "evidence.json")
        pm.save(out_dir / "postmortem.json")
        markdown = mods.render_markdown(pm)
        (out_dir / "postmortem.md").write_text(
            markdown if markdown.endswith("\n") else markdown + "\n",
            encoding="utf-8",
        )
        (out_dir / "linkage.json").write_text(
            json.dumps(linkage.to_dict(), indent=2) + "\n", encoding="utf-8"
        )

    # Stage 4 — evaluation (unless --skip-eval / no ground truth).
    report = None
    gt_path = Path(args.ground_truth) if args.ground_truth else None
    if args.skip_eval:
        print("eval: skipped (--skip-eval)", file=sys.stderr)
    elif gt_path is None:
        print("eval: skipped (no ground truth found)", file=sys.stderr)
    else:
        with stage("evaluate"):
            gt = mods.load_ground_truth(str(gt_path))
            report = mods.evaluate(
                pm, gt, human_text=_human_text(gt_path), evidence=evidence
            )
        with stage("write_eval"):
            _save_eval_report(mods, report, out_dir)

    # Human summary on stdout: per-section badge line, deliverables, metrics.
    for section in pm.sections:
        print(f"{_BADGE_EMOJI.get(section.badge, '·')} {section.title}")
    print(f"postmortem: {out_dir / 'postmortem.md'}")
    if report is not None:
        summary = " ".join(f"{m.name}={m.value}" for m in report.metrics)
        print(f"metrics: {summary}  (report: {out_dir / 'eval_report.json'})")
    return EXIT_OK


def _import_pieces() -> SimpleNamespace:
    """Lazily import the sibling pieces with clear failure messages.

    Returns a namespace of callables plus optional exception classes (None
    when the sibling module does not define them yet). Raises RuntimeError
    while a piece is still being built (main() maps that to exit code 5).
    """
    try:
        from pmg import bob as bob_mod
        from pmg import collector as collector_mod
        from pmg import eval as eval_mod
        from pmg.bob import generate_postmortem, render_markdown, validate_linkage
        from pmg.collector import collect_case
        from pmg.eval import evaluate, render_report
    except ImportError as exc:
        raise RuntimeError(
            f"sibling piece not importable yet ({exc}); pmg.collector / pmg.bob / "
            "pmg.eval are built in parallel — see docs/CONTRACTS.md"
        ) from exc
    try:
        from pmg.eval import load_ground_truth
    except ImportError:
        try:
            from pmg.eval.ground_truth import load as load_ground_truth
        except ImportError as exc:
            raise RuntimeError(
                f"pmg.eval ground-truth loader not found: {exc}"
            ) from exc
    return SimpleNamespace(
        collect_case=collect_case,
        offline_cache_miss_cls=getattr(collector_mod, "OfflineCacheMiss", None),
        generate_postmortem=generate_postmortem,
        render_markdown=render_markdown,
        validate_linkage=validate_linkage,
        bob_unavailable_cls=getattr(bob_mod, "BobUnavailableError", None),
        evaluate=evaluate,
        render_report=render_report,
        load_ground_truth=load_ground_truth,
        save_report=getattr(eval_mod, "save_report", None),
    )


def _matches(exc: BaseException, cls: type | None, name: str) -> bool:
    """True when exc is an instance of cls (if importable) or its class (or a
    base) is simply named `name` — siblings may not exist yet at import time."""
    if cls is not None and isinstance(exc, cls):
        return True
    return name in {base.__name__ for base in type(exc).__mro__}


def _human_text(gt_path: Path) -> str | None:
    """Human postmortem prose sitting next to the ground truth file (used by
    the line_agreement metric); None when absent. Recognized file names:
    advisory.md, blog.md, postmortem.md."""
    parts: list[str] = []
    for name in ("advisory.md", "blog.md", "postmortem.md"):
        path = gt_path.parent / name
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts) if parts else None


def _save_eval_report(mods: SimpleNamespace, report: Any, out_dir: Path) -> None:
    """Write eval_report.json + metrics.md, preferring pmg.eval.save_report.

    Falls back to report.save()/render_report() — and backfills either file
    if save_report writes different names — so the documented artifacts
    always exist.
    """
    if mods.save_report is not None and \
            len(inspect.signature(mods.save_report).parameters) >= 2:
        try:
            mods.save_report(report, out_dir)
        except Exception as exc:  # noqa: BLE001 — backfill below recovers
            print(f"[warn] save_report failed ({exc}); writing eval files "
                  "manually", file=sys.stderr)
    if not (out_dir / "eval_report.json").is_file():
        report.save(out_dir / "eval_report.json")
    if not (out_dir / "metrics.md").is_file():
        markdown = mods.render_report(report)
        (out_dir / "metrics.md").write_text(
            markdown if markdown.endswith("\n") else markdown + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":  # pragma: no cover — `python -m pmg.shell.cli`
    sys.exit(main())
