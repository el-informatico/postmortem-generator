# Contracts — how the four pieces fit together

Single source of truth for cross-module interfaces. The data shapes live in
`pmg/contracts.py` (stdlib-only, importable everywhere). This file fixes the
**responsibilities, public functions and file ownership** so the pieces can be
built and tested independently.

## Pipeline

```
CaseConfig ──▶ pmg.collector.collect_case() ──▶ Evidence
                                                   │
                                    pmg.bob.generate_postmortem(evidence, mode)
                                                   │
                                              Postmortem ──▶ pmg.eval.evaluate()
                                                                   │
                                                             EvalReport
```

The CLI (`pmg.shell.cli`, entry point `bob-postmortem`) chains all four and
must work fully offline: `collect (cached/offline) → generate (deterministic
fallback when Bob is unavailable) → eval (when ground truth exists)`.

## Piece boundaries & public API

| Piece | Module | Public function | Owns |
|---|---|---|---|
| 1. Collector | `pmg.collector` | `collect_case(case: CaseConfig, cache_dir: Path, offline: bool = False, repo_path: Path \| None = None, max_diff_bytes: int = 200_000) -> Evidence` | `pmg/collector/**`, `scripts/refresh_cache.py` |
| 2. Orchestration | `pmg.bob` | `generate_postmortem(evidence: Evidence, mode: str = "auto") -> Postmortem` (+ `ROLES`, `render_markdown(pm) -> str`, `validate_linkage(pm, evidence) -> LinkageReport`) | `pmg/bob/**`, `.bob/**` (Bob command/modes config) |
| 3. Shell/CI | `pmg.shell` | `main(argv: list[str] | None = None) -> int` — subcommand `postmortem` | `pmg/shell/**`, `.github/workflows/postmortem.yml` |
| 4. Eval harness | `pmg.eval` | `evaluate(pm: Postmortem, ground_truth: dict, human_text: str \| None = None, evidence: Evidence \| None = None) -> EvalReport` (+ `render_report(report) -> str`, `save_report(report, out_dir) -> tuple[Path, Path]`, `load_ground_truth(path)`) | `pmg/eval/**` |

`mode` for piece 2: `"auto"` (use Bob if configured/available, else
deterministic), `"bob"`, `"deterministic"`. The deterministic fallback fills
the SRE template from `Evidence` only — it is the offline/no-AI floor and
MUST obey the honesty rule.

## Honesty rule (binding for piece 2, checked by piece 4)

Git/repository data contains **no** user impact, no telemetry, no detection
story. For sections `impact` and `detection` (`HONESTY_SECTIONS` in
contracts): unless external evidence was explicitly ingested, emit badge
`red` and a body containing the phrase `No evidence` (e.g. *"No evidence in
repository data — impact requires incident telemetry, alerts or reports"*).
Never invent numbers, dates or affected-user claims. The eval harness fails
`honesty_check` otherwise.

Badges: `green` = all claims have ≥1 valid evidence ref · `yellow` = grounded
but some claims unreferenced · `red` = no evidence (must say so).

## Evidence reference ids (claim → evidence linkage)

`Evidence.ref_ids()` produces the valid id set:
- `fix`, `case`
- `commit:<short_sha>` (the fix commit)
- `candidate:<short_sha>` (each introducer candidate)
- `issue:<n>`, `issue:<n>#comment:<k>` (k = 0-based index in `comments`)
- `event:<i>` (i = index in `evidence.timeline`)

Claims carry `refs: list[str]`; `pmg.bob.validate_linkage` validates them;
`claim_linkage_rate` in the eval is computed strictly when the caller passes
`evidence` (a claim counts as linked iff its refs are non-empty AND all of
them are in `Evidence.ref_ids()`), else leniently (non-empty refs).

## Eval metrics (canonical names, see `METRIC_NAMES`)

`introducer_top1`, `introducer_top5` (exact SHA-10 match vs ground truth),
`timeline_recall`, `timeline_precision` (date within ±3 days **and** content
token Jaccard ≥ 0.3, or same commit sha), `action_item_overlap` (best-match
token coverage ≥ 0.35 counts as covered), `root_cause_match` (token overlap
0..1), `honesty_check` (bool), `claim_linkage_rate`, `line_agreement`
(sentence-level recall over human postmortem text, threshold Jaccard ≥ 0.35),
`wall_clock_seconds`. All comparisons deterministic, AI-free, documented in
the report `detail`.

## File layout

```
pmg/contracts.py        shared types (this doc's implementation)
pmg/collector/          piece 1: github_api.py (cached REST), git_local.py,
                        szz.py (SZZ-lite), collect.py (orchestration)
pmg/bob/                piece 2: roles.py, orchestrator.py (Bob + deterministic),
                        template.py (SRE template + badges), linkage.py
pmg/shell/cli.py        piece 3: `bob postmortem --repo --issue --fix-sha`
pmg/eval/               piece 4: ground_truth.py, compare.py, report.py
data/cases/*.json       case configs (curl-cve-2023-38545.json)
data/ground_truth/      human postmortem material for eval (advisory, blog,
                        github-api.json, ground_truth.json)
data/cache/             GitHub API disk cache (gitignored, rebuildable)
tests/                  pytest; unit tests run offline with fixtures in
                        tests/fixtures/; @integration marks tests that need
                        .repos/curl
```

## Ground truth JSON (data/ground_truth/ground_truth.json)

Shape (produced by research, consumed by `pmg.eval.ground_truth.load`):

```json
{
  "case": "curl-cve-2023-38545",
  "cve": "CVE-2023-38545",
  "summary": "...",
  "severity": {"cvss": "...", "quoted": "..."},
  "root_cause": {"statement": "...", "quote": "...", "source": "url"},
  "introducer": {"full_sha": "...", "short_sha": "4a4b63daaa", "subject": "...",
                  "author": "...", "author_date": "2020-02-14", "closes_issue": 4907,
                  "released_in": {"version": "7.69.0", "date": "2020-03-11", "source": "url"}},
  "fix": {"full_sha": "...", "short_sha": "fb4415d8aee6", "subject": "...",
           "author_date": "2023-10-11",
           "released_in": {"version": "8.3.0", "date": "2023-10-11", "source": "url"}},
  "detection": {"who": "...", "how": "...", "date": "...", "quote": "...", "source": "url"},
  "impact": {"quotes": ["..."], "sources": ["url"],
             "not_derivable_from_git": ["user impact", "telemetry", "detection"]},
  "timeline": [{"date": "YYYY-MM-DD", "event": "...", "source": "advisory|blog|github-api"}],
  "action_items": [{"item": "...", "source": "url|null"}],
  "duration_in_days_undetected": {"value": 1315, "quote": "...", "source": "url"},
  "sources": {"advisory": "url", "blog": "url", "commits_api": ["url"], "issue_api": ["url"]}
}
```

## Conventions

- Python ≥3.10, **stdlib only** at runtime (urllib for GitHub API, subprocess
  for git). pytest for tests. No network in unit tests — GitHub responses are
  replayed from `data/cache/` or fixtures.
- GitHub API: `urllib.request` with optional `GITHUB_TOKEN` env var; on-disk
  cache keyed by request URL under `cache_dir`; `offline=True` never touches
  the network and raises a clear error on cache miss.
- git access: always via `subprocess` against `case.local_repo`.
- Every public function has a docstring; every module states which piece it
  belongs to.
