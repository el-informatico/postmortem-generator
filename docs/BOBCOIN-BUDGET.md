# Bobcoin budget model — IBM Bob 2.0 sprint (Fri 25-Sep 15:00 UTC → Sun 27-Sep 15:00 UTC)

Spend plan for every `bob run` session of the sprint. Session order lives in
`docs/SPRINT-RUNBOOK.md`; this doc owns the caps, the arithmetic, and the
cut ladder. Companion research: `docs/research/ibm-bob-notes.md` §7,
`docs/research/hackathon-status-2026-09-15.md` §3.

Core rule: **the `--bob-max-cost` value IS the exposure limit per session.**
Worst-case spend = sum of caps. Nothing below is a prediction; everything is
either MEASURED (source given) or ASSUMED (numbered, replaced at kickoff).

## 1. Assumptions (numbered; how each is replaced by a real measurement)

| # | Assumption | Basis | Replaced at sprint start by |
|---|---|---|---|
| A1 | Sept quota = **40 Bobcoins** | May guide quote ("40 Bobcoins… automatically applied", DDG snippet) + BeMyApp 40-coin trial. **No Sept figure exists** ("Access details TBA", status doc §3) | Kickoff stream 15:35 UTC Fri ("Hackathon Guide" item), lablab Tools/Resources tab, or the Bob gauge → re-read the trigger table (§6) |
| A2 | Per-session cost unknown pre-event; IBM publishes **no token→Bobcoin conversion** | ibm-bob-notes §7: "cost of a typical multi-agent session NOT DOCUMENTED" | Smoke session + first curl run: `stats.session_costs` (§7 calibration) |
| A3 | 1 Bobcoin ≈ $0.50 | The Register snippet (unverified) | Used only for the sanity floor in §4; drop if disproven |
| A4 | tokens ≈ chars / 4 | Standard heuristic for English/code prose | Smoke envelope's `input_tokens` ÷ prompt chars → real ratio |
| A5 | Prompt sizes measured today stay valid | Evidence is cached (`data/cache/`); prompts embed it | Hour-0 check: `du -b eval-output/*/evidence.json` matches §2 |
| A6 | Analyst findings JSON fed to synthesizer ≈ 6,000 chars (3 roles × ~6 findings) | Estimated; bounded by the output contract in `pmg/bob/roles.py` | Measure the real findings blob after the first curl run |
| A7 | `--max-cost N` unit = Bobcoins | Flag help wording; docs example shows `--max-cost 0.50` (ambiguous — ibm-bob-notes unknown #8) | `bob run --help` at hour 0 + gauge delta after smoke |
| A8 | Sessions are near-single-turn (evidence embedded in prompt; read-only roles) | `build_role_prompt` ships each role its full slice; no exploration needed | `tool_calls` + `total_tokens` vs prompt chars in smoke/curl envelopes |
| A9 | `--bob-max-cost` applies uniformly to all 4 sessions of one CLI invocation | `pmg/shell/cli.py` forwards one value; per-role caps need a code change | Accepted as-is; noted per line in §5 |

## 2. Grounded input sizes (MEASURED 2026-09-16)

Method: `python3` calling `pmg.bob.roles.build_role_prompt(role, Evidence.load(...))`
on the real payloads in `eval-output/<case>/evidence.json` — i.e. the exact
strings the orchestrator puts on each `bob run` argv. Synthesizer "+findings"
adds the estimated A6 blob. Tokens = chars/4 (A4).

| Case | evidence.json | refs | commit-archaeologist | document-analyst | code-reviewer | sre-synthesizer (base / +findings) | Case single-pass input |
|---|---|---|---|---|---|---|---|
| curl-cve-2023-38545 | 10,936 B (10.7 KB) | 22 | 7,229 ch (~1.8K tok) | 1,816 ch (~0.5K) | 5,826 ch (~1.5K) | 8,641 / ~14,806 ch (~2.2K / ~3.7K) | ~29.7K ch ≈ **7.4K tok** |
| log4j-cve-2021-44228 | 192,154 B (187.7 KB) | 332 | 53,443 ch (~13.4K) | 118,079 ch (~29.5K) | 16,201 ch (~4.1K) | 166,494 / ~172,659 ch (~41.6K / ~43.2K) | ~360K ch ≈ **90K tok** |
| gitlab-2017-db-outage | 4,951 B (4.8 KB) | 5 | 1,704 ch (~0.4K) | 4,562 ch (~1.1K) | 1,141 ch (~0.3K) | 6,525 / ~12,690 ch (~1.6K / ~3.2K) | ~20.1K ch ≈ **5.0K tok** |

Measured facts behind the asymmetry: curl fix diff is 3,451 chars (under the
8,000-char cap the code-reviewer applies); log4j's diff is 31,075 chars
(truncated to 8,000 for the reviewer) and its issue thread + 165 timeline
events are what inflate document-analyst and synthesizer; gitlab is
issues-only (no fix commit — archaeologist/reviewer prompts carry an explicit
null). All prompts peak at ~43K tok, far under Bob's 270K context window — no
compaction risk. Output is bounded by the JSON contracts (~0.5–1.5K tok per
analyst, ~2–4K tok for the synthesizer).

## 3. Cost model per session (planning envelope, NOT prediction)

IBM publishes no conversion (A2), so the envelope rests on the one community
datapoint — an intensive interactive **day ≈ 20 Bobcoins** (community.ibm.com
snippet, ibm-bob-notes §7) ≈ 1.5–2.5 coins per multi-turn interactive session —
adjusted down because our sessions are bounded, evidence-embedded, read-only,
single-purpose tasks under hard caps (A8). Sanity floor: at $0.50/coin (A3) and
typical 2026 frontier list prices, the raw tokens of one full case cost
$0.10–1.00 (≈ 0.2–2 coins) — 5–10× under the caps, i.e. caps have headroom.

| Session class | input (tok) | low | median | high | cap used |
|---|---|---|---|---|---|
| smoke (trivial prompt) | <0.1K | 0.1 | 0.25 | 0.5 | 1 |
| gitlab role | ≤3.2K | 0.25 | 0.75 | 2 | 1 |
| curl role | 0.5–3.7K | 0.5 | 1.25 | 3 | 2 |
| log4j light role (arch/reviewer) | 4–13K | 0.75 | 1.75 | 4 | 2 |
| log4j heavy role (doc-analyst/synth) | 30–43K | 1 | 2.5 | 5 | 2 |

Two deliberate policies: log4j heavy roles carry cap < high — a capped-out
session is a controlled failure that triggers the cut ladder, never an
overage. And the pipeline degrades rather than over-spends: an analyst that
dies (cap or error) lands in `meta['role_failures']` and synthesis continues
with survivors; if the synthesizer itself dies, `--mode auto` falls back to
the deterministic generator at zero further Bobcoin cost (`pmg/bob/orchestrator.py`).

## 4. Budget table under the ~40 assumption (A1)

| # | Line (runbook session) | Bob sessions | `--bob-max-cost` | Worst case |
|---|---|---|---|---|
| 1 | S1 smoke — tiny `bob run`, proves auth/envelope/units (A2, A7) | 1 | 1 | 1 |
| 2 | S2 curl full run | 4 | 2 | 8 |
| 3 | S3 curl retry reserve | 2 | 2 | 4 |
| 4 | S5 log4j full run (after eval decision) | 4 | 2 | 8 |
| 5 | S6 gitlab full run (issues-only) | 4 | 1 | 4 |
| 6 | S7 CI / Bob Shell demo — `workflow_dispatch`, `--mode bob` on the smallest case | ≤4 | 1 | 4 |
| 7 | Final polish / re-run reserve | 3 | 1 | 3 |
| — | **Committed worst case** | **22** | | **32** |
| — | Unallocated margin | | | **8 (20%)** |
| — | Assumed quota (A1) | | | **40** |

Arithmetic check: 1 + 8 + 4 + 8 + 4 + 4 + 3 = 32; 32 + 8 = 40; margin
8/40 = 20% ≥ 15%; worst case 32 < 40. Expected (median envelope, reserves
unused): 0.25 + 5 + 0 + 8.5 + 3 + 3 + 2.25 = **22 coins** (curl 4 × 1.25;
log4j 2 heavy × 2.5 + 2 light × 1.75; gitlab/CI 4 × 0.75; polish 3 × 0.75).

Commands (cache is warm; `--offline` keeps the collector off the network):

```bash
# S1 smoke (replace prompt with any trivial JSON-reply instruction)
BOB_API_KEY=... bob run --format json --max-cost 1 "Reply with exactly: {\"ok\": true}"
# S2 / S3 / S5 / S6
bob-postmortem postmortem --case data/cases/curl-cve-2023-38545.json  --mode bob --bob-max-cost 2 --offline
bob-postmortem postmortem --case data/cases/log4j-cve-2021-44228.json --mode bob --bob-max-cost 2 --offline
bob-postmortem postmortem --case data/cases/gitlab-2017-db-outage.json --mode bob --bob-max-cost 1 --offline
```

Footnotes: the cap applies to every session of one invocation (A9). Line 6 is
pre-wired: `.github/workflows/postmortem.yml` takes a `bob_max_cost` dispatch
input (default 1) and forwards it as `--bob-max-cost` for auto/bob dispatch
runs only (verified 2026-09-16; push-trigger runs stay deterministic, §8).

## 5. Cut ladder if the real quota is lower (decide at hour 0–1)

Each rung is cumulative. Committed = remaining worst-case sum.

| Rung | Cut | What the submission loses | Why survivable (judging criteria) |
|---|---|---|---|
| 1 | gitlab Bob run (−4) | Bob-generated third case | Weakest metric gain: issues-only, no diff/candidates for Bob to shine on. Deterministic gitlab row keeps the 3-case corpus table (Presentation). Application of Technology keeps curl+log4j as proof |
| 2 | log4j Bob run (−8) | Second Bob-generated deep case | Deterministic log4j output stays, and the honest SZZ-blindspot story (already documented in STATUS.md) turns the gap into an honesty-rule demo. Corpus breadth intact |
| 3 | CI/Action live demo (−4) | Live Bob-inside-CI proof | YAML + a real push-trigger run (deterministic, zero spend) stay in the repo; demo walks the syntax and the dispatch path. Biggest Application-of-Technology dent — mitigate with the recorded deterministic run |
| 4 | curl shrunk to 2 roles: document-analyst + synthesizer (curl line 8→4) | The 3-role parallel fan-out — a headline Bob 2.0 feature the challenge text names | The archaeologist's introducer finding is already top-1 deterministically; feed that finding to the synthesizer and present the 3-role architecture + role diagrams. Zero code change: `PMG_ANALYST_ROLES=document-analyst bob-postmortem postmortem …` (env override of `ANALYST_ROLE_IDS` in `pmg/bob/roles.py`, tested); the synthesizer already tolerates absent analysts |

Trigger thresholds, re-derived from the table arithmetic (the brief's
suggested 25/15/8/4 do NOT verify against it — corrected here). Rule: a
configuration is viable at quota Q when committed ≤ Q − max(2, 0.15·Q):

| Measured quota Q | Configuration | Committed | Buffer at band floor |
|---|---|---|---|
| ≥ 38 | full plan | 32 | 6 (15.8%) |
| 33–37 | rung 1 | 28 | 5 (15.2%) |
| 24–32 | rungs 1–2 | 20 | 4 (16.7%) |
| 19–23 | rungs 1–3 | 16 | 3 (15.8%) |
| 7–18 | rung 4 (smoke + 2-role curl) | 5 | 2 |
| ≤ 6 | rung 4, smoke folded into session 1 | 4 | 2 at Q=6; below that the caps are the only guarantee (fractional caps are legal — docs show `--max-cost 0.50`; use Q/2 per session) |

Band arithmetic: 32 ≤ 38−5.7 ✓ | 28 ≤ 33−4.95 ✓ | 20 ≤ 24−3.6 ✓ | 16 ≤ 19−2.85 ✓
| 5 ≤ 7−2 ✓. Band edges are mechanical: landing within ~1 coin of an edge
(e.g. Q=18 vs rungs 1–3 at 11% buffer) may justify the bigger configuration —
decide once, log it in the tracker (§9).

## 6. Calibration (hour 1 of the sprint)

1. Hour 0: learn Q (A1) and the `--max-cost` unit (A7, `bob run --help`);
   pick the band from §5.
2. Smoke (S1): read actual spend → fixed per-session overhead. Smoke ≤ 0.5 →
   envelope holds; ≈ 1 (cap) → shift every median up ~2× and treat the quota
   band one notch down.
3. After the first full curl run (S2): expected ≈ 5 (4 × median 1.25). Actual
   ≤ 8 → proceed. Any session at its cap → inspect `meta['role_failures']`,
   apply the next rung BEFORE log4j. Re-scale: projected spend = measured
   per-session cost × remaining sessions (22 total minus sessions run).
4. Read real cost only from these places: `bob run --format json` envelope →
   `stats.session_costs` (plus `total_tokens`, `input_tokens`,
   `output_tokens`, `cache_read_tokens`, `tool_calls`, `duration_ms`); the
   gauge top-right of the Bob panel; Settings → General; Bobalytics. Post-hoc
   audit: `bob --list-tasks` (NDJSON). The orchestrator parses envelopes
   in-memory only — on sprint day, `tee` the raw envelopes to a log (small
   code change) or rely on gauge/`--list-tasks`.

## 7. Non-spend guarantees (zero Bobcoins by construction)

- `--mode deterministic` generation, the whole test suite, UI build
  (`scripts/build_ui.py`), eval harness, video recording, submission prep —
  none invoke the `bob` binary.
- GitHub Action **push trigger runs deterministic mode by design**:
  `postmortem.yml` resolves `inputs.mode || 'deterministic'` (verified
  2026-09-16) — zero spend even with `BOB_API_KEY` set.
- Only lines 1–7 of the §4 table can ever spend, and never past their caps.

## 8. Running tracker (fill on sprint day; referenced by docs/SPRINT-RUNBOOK.md)

Balance starts at the measured quota Q (A1). Balance = Q − cumulative actual.

| # | Session | Case | Role / command | Cap | Actual | Balance | Note |
|---|---|---|---|---|---|---|---|
| 1 | S1 smoke | — | `bob run --max-cost 1` | 1.0 | | | units check (A7) |
| 2 | S2 curl | curl-cve-2023-38545 | commit-archaeologist | 2.0 | | | |
| 3 | S2 curl | curl-cve-2023-38545 | document-analyst | 2.0 | | | |
| 4 | S2 curl | curl-cve-2023-38545 | code-reviewer | 2.0 | | | |
| 5 | S2 curl | curl-cve-2023-38545 | sre-synthesizer | 2.0 | | | calibrate here (§6.3) |
| … | S3–S7 | … | … | … | | | one row per session |
