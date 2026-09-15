#!/usr/bin/env python3
"""Warm the GitHub API disk cache for a case (piece 1 support script).

Fetches the issue and comment threads a case needs so that collection can
run fully offline afterwards. Online only — exits non-zero on failure.

Usage:
    python3 scripts/refresh_cache.py [--case PATH] [--cache-dir DIR]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:  # allow running without installing pmg
    sys.path.insert(0, str(PROJECT_ROOT))

from pmg.collector.errors import CollectorError  # noqa: E402
from pmg.collector.github_api import warm_cache  # noqa: E402
from pmg.contracts import CaseConfig  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Warm the GitHub API cache for a case (online only)."
    )
    parser.add_argument(
        "--case",
        default=str(PROJECT_ROOT / "data" / "cases" / "curl-cve-2023-38545.json"),
        help="path to the case config JSON (default: the curl CVE case)",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(PROJECT_ROOT / "data" / "cache"),
        help="cache directory to populate (default: data/cache)",
    )
    args = parser.parse_args(argv)

    try:
        case = CaseConfig.load(args.case)
        urls = warm_cache(case, Path(args.cache_dir))
    except (CollectorError, OSError, ValueError) as exc:
        print(f"refresh_cache failed: {exc}", file=sys.stderr)
        return 1

    for url in urls:
        print(url)
    print(f"cached {len(urls)} URL(s) under {args.cache_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
