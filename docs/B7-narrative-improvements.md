# B7 — Narrative metric improvements (deterministic floor, no AI)

Date: 2026-09-15 (pre-sprint block B7). Goal from the sprint backlog: close
the gap between the `DeterministicOrchestrator` output and the human curl
postmortem on the narrative metrics, with every improvement measured by the
existing eval harness (`eval-output/`), running before/after on all three
corpus cases.

## Anti-washing statement (read first)

**The scoring did not change.** `git diff --stat pmg/eval/` is empty for this
block: metric names, formulas, thresholds (`±3 days`, `jaccard >= 0.3`,
`overlap_ratio >= 0.35`, …) and `METRIC_NAMES` are byte-identical to B6.
Every delta below comes from **better evidence collected** (piece 1) and
**better narrative generated** (piece 2) — the artifact under test changed,
not the ruler.

Where a metric got *worse*, it is reported as such (log4j
`line_agreement`, below, with the reason).

## What changed

### Piece 1 — collector: evidence it always had but dropped

| New evidence | Source (offline) | What it grounds |
|---|---|---|
| `CommitInfo.committer_date`, `IntroducerCandidate.committer_date` | `git show %cI` | "pushed" timeline milestone (author→committer gap = review/merge latency) |
| `IssueThread.closed_at` / `merged_at` / `is_pull_request` | GitHub API cache (already fetched) | issue/PR close events; PR vs Issue wording |
| `Evidence.releases` (`ReleaseInfo`) | `git tag --contains --sort=version:refname`, skipping `-rc/-alpha/-beta/-M` tags | "first release shipping the vulnerable code" / "first release containing the fix" events; the upgrade action item |
| `utc_iso()`/`utc_date()` (contracts) | — | git dates carry local offsets, GitHub API is UTC; day-level logic normalizes to UTC (this alone fixed a one-day drift: curl's introducer committer date is `2020-02-17T00:08:48+01:00` = `2020-02-16T23:08:48Z`) |

### Piece 2 — deterministic orchestrator: narrative curation

- **Timeline = milestones, not raw rows.** The narrative timeline keeps
  issue/PR lifecycle, the *top* introducer candidate (authored + pushed),
  releases and the fix. Lower-ranked SZZ candidates stay in root_cause as
  what they are (candidates); comments posted *after* the resolution are
  follow-up discussion, not incident history (this is what took log4j
  precision from 0.012 to 0.50 — 156 post-disclosure PR comments were
  flooding the timeline). A PR closing the same day a commit was pushed
  merges into one line (curl: "introducer pushed; PR #4907 closed
  (unmerged)" — matching how the human wrote that moment).
- **Root cause = the fix's own words.** The section quotes, verbatim from
  the repository: the human-readable message strings the diff adds/removes
  (C split-string continuations joined), the fix commit message body
  (trailers dropped, longest segments kept — for curl this is literally the
  author's causal explanation: *"Prior to this change the state machine
  attempted to change the remote resolve to a local resolve…"*), and the
  copy site (`memcpy` & friends) when the diff shows one. The raw key-lines
  code block moved to `resolution` (what changed) where it belongs.
- **Action items = recorded follow-ups.** New repo-grounded items:
  "Upgrade to \<first release containing the fix\>" (from tags), "Apply the
  patch to your local version" (the fix commit exists), plus — for
  issues-only/tracking cases — the checklist items **the humans themselves
  recorded** in the issue body (top-level bullets referencing `(#N)` or
  issue URLs; this is the gitlab tracking issue, i.e. exactly where the
  human action items came from). Items expressing advice or opinion the
  repository cannot ground ("better tests could have caught it", "pay a
  bounty") are deliberately NOT invented — that is the honesty rule.

## Before → after (same harness, same ground truth)

| Metric | curl | log4j | gitlab |
|---|---|---|---|
| timeline_recall | 0.375 → **0.75** | 0.25 → 0.25 | 0.091 → **0.182** |
| timeline_precision | 0.60 → **1.00** | 0.012 → **0.50** | 1.00 → 1.00 |
| action_item_overlap | 0.111 → **0.333** | 0.00 → **0.25** | 0.00 → **0.786** |
| root_cause_match | 0.220 → **0.295** | 0.086 → **0.172** | 0.075 → 0.075 |
| honesty_check | ✓ → ✓ | ✓ → ✓ | ✓ → ✓ |
| claim_linkage_rate | 1.00 → 1.00 | 1.00 → 1.00 | 1.00 → 1.00 |
| introducer_top1/top5 | ✓/✓ → ✓/✓ | ✗/✗ → ✗/✗ | n/a → n/a |
| line_agreement | 0.00 → 0.00 | 0.056 → **0.00** ↓ | 0.00 → 0.018 |

### The one regression, explained

log4j `line_agreement` dropped 0.056 → 0.00. The old value was a single
lucky sentence match: a post-disclosure PR comment (2021-12-20, remkop)
quoting the Log4j security page happened to token-match the advisory's
"Source: …" line. That comment is follow-up discussion, now correctly
excluded from the narrative; nothing in the generated postmortem claims
less today than before. Kept as-is deliberately — buying it back would mean
re-adding noise to the timeline.

### Why the remaining gaps are honest ceilings (repo-only, no advisory)

- curl timeline misses: 2023-09-30 private report, 2023-10-03 distros mail
  — exist only in the advisory/blog, not in repository data.
- log4j: introducer `f1a0cac60f` is a documented SZZ-lite blind spot; the
  JIRA/NVD/CISA events are outside repository data.
- gitlab: the outage timeline lives in the blog postmortem; only the
  tracking-issue lifecycle (open/close) is derivable.
- `line_agreement` ≈ 0 across the board: sentence-level agreement with
  human prose is precisely the target reserved for the Bob AI sessions in
  the sprint (the deterministic floor does not paraphrase the advisory —
  it has never read it).

## Reproduce

```bash
# before: git stash / checkout the B6 commit, then per case:
python3.12 -m pmg.shell.cli postmortem --case data/cases/curl-cve-2023-38545.json \
  --mode deterministic --offline --local-repo .repos/curl \
  --ground-truth data/ground_truth/ground_truth.json --out eval-output/curl-cve-2023-38545
# after: same command on this branch; compare eval_report.json metrics.
```

Full suite after the block: **172 tests, 0 failures** (155 carried forward
+ 17 new covering UTC normalization, tag/release selection, lifecycle
mapping, message-string extraction, checklist extraction and milestone
curation).
