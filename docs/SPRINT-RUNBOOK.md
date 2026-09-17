# SPRINT RUNBOOK — IBM Bob 2.0 hackathon (lablab.ai)

Window: **Fri 25-Sep-2026 15:00 UTC → Sun 27-Sep-2026 15:00 UTC** (48h, solo).
Repo: the postmortem-generator checkout (WSL; `~/projects/postmortem-generator`). All times below are **UTC**.

Strategy in one line: the deterministic floor is already submission-complete
(175 tests, 3-case corpus, UI, video v1, CI YAML) — the sprint's only job is to
**spend Bobcoins to beat the narrative metrics honestly** (root cause, action
items, line agreement) and to package Bob-session evidence. If Bob fails at any
point, the submission is never at risk; we ship the floor.

Companion docs (read before Fri):
- `docs/research/hackathon-status-2026-09-15.md` + its "Sprint-start checklist" section (tracks/judges/Bobcoins/pre-existence re-check)
- `docs/research/ibm-bob-notes.md` (Bob CLI mechanics, export procedure, unknowns)
- `docs/BOBCOIN-BUDGET.md` (budget model + cut ladder; caps referenced below as `<CAP>`)

Ground rules (all 48h):
- **Never contact organizers** (no email, no DMs, no Discord questions to staff).
- **Never fabricate evidence** — no invented screenshots, no invented metrics.
- Push/publication is **user-gated**: request an explicit "YES" before any `git push`. Until then everything stays local; the last pre-sprint state is already on GitHub.
- Clock: keep a UTC clock visible next to the terminal. Treat **Sun 15:00 UTC as the cliff** (ignore the 21:00Z artifact in the page JSON).
- Commit at the end of every phase (hooks: commit-msg, pre-commit, `scripts/guard-sensitive-content.sh` — they block secrets).

---

## 1. Prerequisites & access checklist (fill "verify at" on the day)

| # | Item | How to verify | Verify at (UTC) |
|---|------|---------------|-----------------|
| 1 | lablab.ai registration complete + team joined/formed (solo team OK; limit 6) — **registration closes at kickoff** | <https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon> shows you as registered | ☐ ____ |
| 2 | IBMid / IBM Bob 2.0 login works | login at <https://bob.ibm.com/login> (SSO/IBMid) | ☐ ____ |
| 3 | Bob IDE **Agent mode** available | open IDE, mode dropdown shows Agent/Plan/Ask | ☐ ____ |
| 4 | Bob Shell installed, `bob --version` works, Node >= 24 | `bob --version && node --version` | ☐ ____ |
| 5 | `BOB_API_KEY` minted (**Inference** scope, Bob web portal) and exported | `echo ${BOB_API_KEY:+set}` → `set` | ☐ ____ |
| 6 | Smoke passes | `bob run "reply with ok" --format json` → exit 0, `type:"result"`, `last_message` ~ ok | ☐ ____ |
| 7 | Git repo clean, last pre-sprint state pushed (user-gated) | `git status --porcelain` empty; `git log --oneline -1` matches origin | ☐ ____ |
| 8 | `scripts/verify_sprint_ready.sh` green (READY OFFLINE) | `bash scripts/verify_sprint_ready.sh` | ☐ ____ |
| 9 | lablab Discord open read-only (announcements only) | <https://discord.gg/lablabai> | ☐ ____ |
| 10 | Deadline sanity: /live still says "Sep 27, 15:00 UTC" | <https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon/live> | ☐ ____ |

---

## 2. T-1 — Thu 24-Sep pre-flight (optional block)

- [ ] Watch the "Prompt, Build, Ship" workshop recording (BJ Hargrave, IBM Research) — <https://ibm-bobday.bemyapp.com/> — focus on Bob 2.0 setup/access mechanics. (Time listings disagree between sources: BeMyApp says 11:00–12:30 ET, developer.ibm.com says 12:00 ET, both for 24-Sep — re-check the day before; treat the recording, not the live slot, as the deliverable.)
- [ ] Sleep. Seriously: two planned sleep windows exist in the 48h plan; banking rest now costs nothing.
- [ ] Food plan for 48h (prep ahead; no shopping trips mid-sprint).
- [ ] Machine updates OFF: `sudo apt-mark hold` on anything auto-updating, pause WSL/Windows updates, notifications off, disk >= 5 GB free (`.repos/` + `eval-output/` + video workspace).
- [ ] Re-run `bash scripts/verify_sprint_ready.sh` one last time → READY OFFLINE.

---

## 3. Hour 0 gates — Fri 25-Sep 15:00–15:45 UTC (in order)

### (a) Re-verify event status (15:00–15:20) — links in `docs/research/hackathon-status-2026-09-15.md` §"Sprint-start checklist"

- [ ] /live page: did **tracks** leave "TBA"? New judges (IBM side)? Deadline still Sun 15:00 UTC?
- [ ] Kickoff stream / event page: **September Bobcoin figure** published? If a number appears, write it into §5 below and re-check the caps in `docs/BOBCOIN-BUDGET.md`.
- [ ] S3 bucket `https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/?list-type=2` — a **September rules/guide PDF**? If yes, read the **pre-existing-code / pre-developed-technology** clause before any work is claimed as sprint work. Also check the "original and MIT-compliant" fine print — if it explicitly requires MIT, decide then whether to add an MIT license file alongside Apache-2.0 (both permissive; 5-minute change, do not let it eat time).
- [ ] Record findings in a scratch note (not committed): tracks ____ / judges ____ / Bobcoins ____ / rules-PDF ____.

### (b) Kickoff stream (15:35 UTC, "Hackathon Guide" item)

- [ ] Join from the event page; listen for: access mechanics, Bobcoin allotment, video length cap, submission-form surprises. No questions to organizers.

### (c) Bob smoke test (as soon as access is confirmed, target by 16:00)

```bash
export BOB_API_KEY=<inference-scope key>
bob --version && node --version          # expect Shell 2.0.x, Node >= 24
bob run "reply with ok" --format json    # exit 0, type:"result", last_message ~ "ok"
```

- [ ] Smoke passes. Log its `stats.session_costs` (if any) as session 0 in the tracker (§5).

### (d) Record Bobcoin starting balance

- [ ] Bob IDE: gauge top-right / Settings → General / Bobalytics → starting balance = ____ coins at ____ UTC. First row of the tracker (§5).

### (e) DECISION GATE — pre-existing code policy (by 15:45)

- [ ] September rules still silent / permissive (May precedent: original submission + pre-developed technology allowed respecting licenses) → **proceed as planned**: sprint work = Bob integration (pieces 2-3 live), narrative-metric deltas, evidence packaging — all on top of the openly-documented pre-sprint base (git history + `STATUS.md`).
- [ ] September rules **forbid** pre-existing code → execute the documented pivot: the sprint deliverable becomes *only* what is built/changed inside the window (Bob orchestration sessions, metric deltas, evidence), with the pre-sprint base disclosed in the submission text as the openly-documented starting point — or, if the clause is absolute, scope the entry down to the Bob-integration layer alone. **NEVER hide or redate pre-sprint work.** Decide within 30 min; write the decision down; move on.

---

## 4. Phase plan for the 48h

Mapped to the brief's PLAN 48H; reality: brief hours 0-6 (collector), 20-30 (eval) are **pre-sprint complete**, pieces 2-3 are skeletons → the sprint front-loads Bob sessions.

| Window (UTC) | Phase | Brief mapping | Bobcoin spend |
|---|---|---|---|
| Fri 15:00–15:45 | P0 gates (§3) | VERIFICAR AL INICIO | smoke only |
| Fri 15:45–17:00 | P1 offline baseline re-verify | hours 0-6 (done) | **0** |
| Fri 17:00–21:00 | P2 first Bob run on curl + budget calibration | hours 6-20 | 4 sessions (3 analysts + synth) |
| Fri 21:00–23:00 | P3 eval delta + prompt iteration #1 | hours 6-20 | per budget |
| Fri 23:00–Sat 06:00 | sleep window 1 (alarm set) | — | 0 |
| Sat 06:00–11:00 | P3 iteration #2 → K2 decision (§7) | hours 20-30 (eval deltas) | per budget |
| Sat 11:00–15:00 | P4 secondary cases (budget-gated: log4j, then gitlab) | hours 6-20 for cases 2-3 | per cut ladder |
| Sat 15:00–18:00 | P5 CI Action demo run + UI rebuild + README metrics | hours 20-30 (Bob Shell/CI) | 1 capped run |
| Sat 18:00–21:00 | P6 evidence packaging: `bob_sessions/` complete | hours 40-48 prep | 0 |
| Sat 21:00–Sun 03:00 | P7 video decision (+ optional re-record); slide deck | hours 40-48 | 0 |
| Sun 03:00–09:00 | sleep window 2 (alarm set) | — | 0 |
| Sun 09:00–12:00 | P8 final verify + freeze | hours 40-48 | 0 |
| Sun 12:00–13:00 | P9 SUBMIT (hard internal deadline 13:00) | hours 40-48 | 0 |
| Sun 13:00–15:00 | buffer only — emergency use, cliff at 15:00 | — | 0 |

### P1 — baseline re-verify, OFFLINE-first, before ANY Bobcoin spend (Fri 15:45–17:00)

1. Refresh the (free) GitHub cache while the network is friendly, then regenerate the deterministic floor and check it is unchanged:

```bash
cd ~/projects/postmortem-generator
python3.12 scripts/refresh_cache.py --case data/cases/curl-cve-2023-38545.json

bob-postmortem postmortem --case data/cases/curl-cve-2023-38545.json --mode deterministic \
  --offline --ground-truth data/ground_truth/ground_truth.json --out eval-output/curl-cve-2023-38545
bob-postmortem postmortem --case data/cases/log4j-cve-2021-44228.json --mode deterministic \
  --offline --local-repo .repos/logging-log4j2 \
  --ground-truth data/ground_truth/log4j-cve-2021-44228/ground_truth.json --out eval-output/log4j-cve-2021-44228
bob-postmortem postmortem --case data/cases/gitlab-2017-db-outage.json --mode deterministic \
  --offline --ground-truth data/ground_truth/gitlab-2017-db-outage/ground_truth.json --out eval-output/gitlab-2017-db-outage

git diff --stat eval-output/    # EXPECT: empty (deterministic + warm cache = byte-identical)
```

2. `python3.12 -m pytest -q` → 175 passed. `git diff --stat pmg/eval/` must be empty (no scoring changes — that is the honesty rule for any metric delta this sprint).
3. If anything drifted: stop, fix offline, do not touch Bobcoins. (If `console script not found`, use `scripts/bob-postmortem.sh …` or `python3.12 -m pip install -e .`.)

### P2 — first Bob run on curl (Fri 17:00–21:00)

Session order per case (built into `pmg/bob/orchestrator.py`): **phase 1 = 3 analysts in parallel** (`commit-archaeologist`, `document-analyst`, `code-reviewer` — custom chat modes from `.bob/custom_modes.yaml`), **phase 2 = `sre-synthesizer`** merges. Each session: 900s timeout, `--max-cost` cap forwarded to every `bob run`.

```bash
bob-postmortem postmortem --case data/cases/curl-cve-2023-38545.json \
  --mode bob --bob-max-cost <CAP from docs/BOBCOIN-BUDGET.md> \
  --ground-truth data/ground_truth/ground_truth.json \
  --out eval-output/curl-cve-2023-38545-bob
```

- `-bob` suffix keeps the deterministic baseline intact; never overwrite it.
- Exit codes: 0 ok · 2 usage · 3 cache miss · 4 Bob unavailable · 5 unexpected.
- **After the run: capture discipline (§5 loop), then calibrate the budget** — real cost of these 4 sessions re-scales every cap in `docs/BOBCOIN-BUDGET.md`; update it in place.

### P3 — eval delta + prompt iteration (Fri 21:00–23:00, Sat 06:00–11:00)

- Compare `eval-output/curl-cve-2023-38545-bob/metrics.md` vs the baseline table (§9). The goal: beat **root_cause_match, action_item_overlap, line_agreement** — honestly (linkage must stay 1.0; impact/detection must stay red; `git diff --stat pmg/eval/` stays empty).
- Iteration levers, cheapest first: role prompts in `pmg/bob/roles.py`, output contracts, evidence fed to synthesizer. Re-run only the affected sessions where possible.
- Check `postmortem.json` → `meta.role_failures`: analyst failures don't abort; a failed role is simply absent — decide whether to retry it (same cap, once).

### P4 — secondary cases (Sat 11:00–15:00, budget-gated per §7 K3)

```bash
bob-postmortem postmortem --case data/cases/log4j-cve-2021-44228.json --mode bob \
  --bob-max-cost <CAP> --local-repo .repos/logging-log4j2 \
  --ground-truth data/ground_truth/log4j-cve-2021-44228/ground_truth.json \
  --out eval-output/log4j-cve-2021-44228-bob
# gitlab only if the cut ladder still allows it:
bob-postmortem postmortem --case data/cases/gitlab-2017-db-outage.json --mode bob \
  --bob-max-cost <CAP> \
  --ground-truth data/ground_truth/gitlab-2017-db-outage/ground_truth.json \
  --out eval-output/gitlab-2017-db-outage-bob
```

### P5 — CI/Action demo + UI + README (Sat 15:00–18:00)

- One capped live run of `.github/workflows/postmortem.yml` via `workflow_dispatch` (needs `BOB_API_KEY` as a GitHub secret; **request the user's push YES first**). Evidence lands in `bob_sessions/ci/`. The push-triggered smoke stays deterministic — pushes never spend Bobcoins.
- UI rebuild with the chosen (Bob or deterministic) outputs: `python3.12 scripts/build_ui.py && git add ui/index.html`.
- README: update the metrics table with final numbers (baseline vs Bob where Bob won; keep the deterministic row — honesty is a selling point).

### P6 — evidence packaging (Sat 18:00–21:00)

- [ ] `bob_sessions/` complete: one dir per session (§5 convention), CI evidence, plus the parallel-subagents/aggregate-panel screenshot if the IDE produced one.
- [ ] `bob_sessions/README.md` explaining the convention (judges read this folder explicitly).
- [ ] Cross-check: every session in the tracker (§5) has a dir; every dir has screenshot + `.md`.

### P7 — video decision + slides (Sat 21:00–Sun 03:00)

- Ship **v1** (`~/projects/postmortem-generator-deliverables/video-v1/postmortem-generator-demo-v1.mp4`, 4:27, QA 7/7) UNLESS: (a) Bob-session metrics improved the on-screen story (numbers on screen would now be wrong/stale), or (b) the REQUIRED-EVIDENCE flashes (Bob session screenshots) must be inserted — `bob_sessions/` now exists. Re-record only for those two reasons; the pipeline is proven, budget ≤ 4h incl. QA gate.
- [ ] Slide Presentation is a required form field: assemble a short deck from the video beats + README metrics table + 2-3 UI screenshots. Budget 2h, not more.

### P8 — final verify + freeze (Sun 09:00–12:00)

- [ ] `python3.12 -m pytest -q` green; `bash scripts/verify_sprint_ready.sh` (expect READY OFFLINE; the tree-dirty WARN is fine mid-sprint — commit first).
- [ ] `git status --porcelain` clean after the final commit; guard hook never fired; no secrets ever in tree.
- [ ] Final numbers in README == numbers in `eval-output/` == numbers in video/slides.
- [ ] Request the final user "YES" and push; confirm `Application URL` target is live (repo README, and optionally `ui/index.html` via GitHub Pages).

---

## 5. Bobcoin budget tracker (fill on the day)

Budget model, caps, and the cut ladder live in `docs/BOBCOIN-BUDGET.md` — keep it authoritative; the table below is the sprint-day ledger. Calibrate immediately after P2: **the real cost of the first 4 sessions re-scales every remaining cap** — update the budget doc in place, then re-read the cut ladder before P3/P4 decisions.

| # | Case | Role (chat-mode slug) | `--max-cost` cap | Actual cost (`stats.session_costs`) | Running balance | Timestamp (UTC) |
|---|------|----------------------|------------------|--------------------------------------|-----------------|-----------------|
| 0 | — | smoke (`bob run "reply with ok"`) | — | ____ | ____ | ____ |
| 1 | curl | commit-archaeologist | ____ | ____ | ____ | ____ |
| 2 | curl | document-analyst | ____ | ____ | ____ | ____ |
| 3 | curl | code-reviewer | ____ | ____ | ____ | ____ |
| 4 | curl | sre-synthesizer | ____ | ____ | ____ | ____ |
| 5+ | … | … | ____ | ____ | ____ | ____ |

Starting balance (Bobalytics, §3d): ______ coins at ______ UTC.

### Session loop — capture discipline AFTER EVERY session, BEFORE starting the next

This is a **hard submission requirement** (lablab: "include the screenshots of IBM Bob task session summaries"):

1. Bob IDE → `...` (Views and More Actions) → **History** → select the workspace/task.
2. Click the task header → consumption summary (Context Length, Task ID, Tokens, API Cost) → **screenshot**.
3. Click **Export task history** (download arrow) → `.md` file.
4. Save both as `bob_sessions/session-<NN>-<role>/screenshot.png` + `task-history.md` (e.g. `bob_sessions/session-01-commit-archaeologist/`).
5. Add the tracker row (§5) with the actual cost, and only then start the next session.
6. Shell-side corroboration: `bob --list-tasks` (NDJSON: id/title/status/updatedAt) — keep one dump per phase in `bob_sessions/list-tasks-<phase>.ndjson`.

---

## 6. Kill criteria — tick as evaluated (times are the latest trigger moment)

- [ ] **K0 — Bob smoke** (Fri 16:30 UTC): not passing by 16:30 → 1h fix window (§8 playbooks 1/3/4) → still broken at **17:30** → pivot: deterministic story only. Floor is shippable as-is; sprint becomes evidence/CI/video polish. The submission was never at risk.
- [ ] **K1 — first curl run cost** (Fri 21:00 UTC): the 4-session run exceeded the P2 allocation in `docs/BOBCOIN-BUDGET.md` → halve caps / drop to a single-analyst + synthesizer configuration for further runs, per the cut ladder (`PMG_ANALYST_ROLES=document-analyst` env var — no code change).
- [ ] **K2 — narrative metrics** (Sat 11:00 UTC): after 2 full curl attempts (P2 + P3 iterations) `root_cause_match` / `action_item_overlap` / `line_agreement` still ≤ deterministic baseline → **stop spending on curl prompts**. Keep whichever output is better per metric; remaining budget goes to the CI demo run + evidence quality. Record the honest outcome in README.
- [ ] **K3 — secondary cases** (Sat 11:00 UTC, before P4): remaining balance < cut-ladder threshold for a full 4-session run on log4j → skip gitlab entirely; if < threshold for even one capped run → skip both. Cases ship with deterministic outputs (already complete and honest).
- [ ] **K4 — CI demo** (Sat 17:00 UTC): the `workflow_dispatch` run failed or overspent the cap → keep the YAML + local `bob run` evidence as the CI story; do not retry more than once.
- [ ] **K5 — evidence gap** (Sat 21:00 UTC): any session missing its summary export → re-run a cheap ask-mode summary for that task (§8 playbook 7); never ship `bob_sessions/` with holes.
- [ ] **K6 — submission cliff** (Sun): everything submitted by **13:00 UTC** (2h buffer). At 13:00, whatever is on the platform is the entry. 15:00 UTC is the cliff — the 21:00Z page artifact is ignored.
- [ ] **K7 — pre-existing-code rule flip** (any time rules publish mid-sprint): re-run gate §3(e) decision honestly; disclose, never redate.

---

## 7. Failure-mode playbooks (symptom → diagnosis → action → fallback)

1. **Access denied / login broken** (bob.ibm.com/login loops, IDE won't open) → diagnose: IBmid SSO vs portal; try incognito, then the IDE vs the Shell separately; check Discord announcements (read-only) for an outage notice → action: 1h fix window max (K0) → fallback: deterministic floor; if only the Shell is broken but the IDE works, run roles manually in the IDE with the same `.bob/custom_modes.yaml` modes and export those histories — evidence quality survives, metrics survive via `pmg.eval` on the exported JSON.
2. **Quota lower than expected** (starting balance < budget-doc assumption) → action: apply the cut ladder in `docs/BOBCOIN-BUDGET.md` top-down (secondary cases first, then analyst count, then caps); record the real figure in §5 → fallback: single capped curl run total; floor ships regardless.
3. **API/CLI changed** (flags differ from `docs/research/ibm-bob-notes.md`: `--chat-mode`, `--format`, `--max-cost`, `--accept-license`) → diagnosis: `bob --help && bob run --help` FIRST; compare with `BobOrchestrator._build_command` in `pmg/bob/orchestrator.py` → action: adjust `_build_command` (it is the single place commands are built); the test suite is offline so it stays green; re-run the smoke, then one cheap role session before a full run → fallback: none needed — this is a local fix.
4. **BOB_API_KEY invalid scope** (auth error mentioning team/instance) → diagnosis: general-scope key instead of Inference (general keys require `--team-id`) → action: mint an **Inference**-scope key in the web portal; if forced to stay on a general key, add `--team-id` in `_build_command` (one line + test) → fallback: IDE-interactive sessions (playbook 1).
5. **bob output unparseable** (synthesizer returns prose instead of JSON, exit 5) → diagnosis: check `postmortem.json` → `meta.role_failures` and the last 400 chars of stderr echoed in it → action: `parse_bob_result` is tolerant; retry ONCE with the same cap after tightening the output contract wording in `pmg/bob/roles.py` → fallback: feed the surviving analyst findings through the deterministic generator (hybrid, recorded honestly in meta/README).
6. **GitHub API rate limit during cache refresh** (collector errors, or exit 3 "offline cache miss") → diagnosis: rate ceiling, cache cold for a slot → action: the cache is warm for all 3 cases — run everything `--offline` and retry the refresh hours later (unauthenticated quota resets hourly) → fallback: pure offline all sprint; the baseline was already re-established in P1.
7. **Session summary export missing** (no History entry / export icon greyed) → diagnosis: Shell-origin task not visible in IDE History (verify with `bob --list-tasks` — same task store) → action: locate the task, retry export; if truly absent, run one cheap ask-mode session: "Summarize task <id> per its consumption stats" and screenshot that → fallback: note the gap in `bob_sessions/README.md` — never fabricate.
8. **Machine/WSL failure** (disk, kernel, lost session) → action: the repo's remote on GitHub is the recovery point — request the user's push YES at the end of **every phase** (K-commit discipline); deliverables live in `~/projects/postmortem-generator-deliverables/` (video v1 survives independently); `git clone` + `pip install -e .` + `python3.12 scripts/refresh_cache.py` rebuilds the world (only `data/cache/` warmth and `.repos/` clones are machine-local) → fallback: worst case, submit from any machine with the pushed repo + video URL.

---

## 8. Submission checklist — Sun 27-Sep, start 12:00 UTC at the latest (P9 begins)

Form fields (from `docs/research/hackathon-status-2026-09-15.md` §4):

- [ ] **Project Title** — decided Sat (P7), not Sunday.
- [ ] **Short Description** + **Long Description** — includes the honest arc: deterministic collector/eval floor + Bob 2.0 multi-agent sessions as the upgrade; names Agent mode, parallel tasks, subagents, document understanding (challenge-statement keywords).

  Pre-drafted disclosure paragraph (paste into the Long Description; adapt only if the hour-0 rules gate §3(e) resolves differently):

  > **Pre-existing work:** the deterministic core of this repo — git collector, SZZ-lite introducer search, eval harness, 3-case real corpus, offline UI — was built and pushed before the sprint (open, dated git history; never re-dated). Built during the IBM Bob 2.0 window (Sep 25–27): the IBM Bob integration layer — multi-agent postmortem sessions (Agent mode, parallel tasks, subagents, document understanding), measured metric deltas over the deterministic floor, and the `bob_sessions/` evidence trail.
- [ ] **Technology & Category Tags**.
- [ ] **Cover Image** (UI screenshot or metrics badge card).
- [ ] **Video Presentation** — v1 or re-record per P7 decision.
- [ ] **Slide Presentation** — from P7.
- [ ] **Demo Application Platform** + **Application URL** — repo URL (+ GitHub Pages UI if published).
- [ ] **"Include any code or files where IBM Bob assisted"** — point at `pmg/bob/`, `.bob/`, and `bob_sessions/`.
- [ ] **"Screenshots of IBM Bob task session summaries"** — `bob_sessions/` complete (P6, K5).

Repo final state:

- [ ] `bob_sessions/` committed with README; every tracker row has a dir.
- [ ] README final: architecture, metrics table (baseline + Bob deltas, honest), corpus, UI.
- [ ] LICENSE Apache-2.0 present; headers/guard hook clean (`bash scripts/guard-sensitive-content.sh` passes); no `BOB_API_KEY`/tokens anywhere in `git ls-files`.
- [ ] Final push done with the user's explicit "YES"; CI green on the last commit.
- [ ] **Submit** on lablab.ai; screenshot the confirmation (page + timestamp).
- [ ] **Stop touching the repo.** Judging begins at close; no post-deadline "fixes".

---

## 9. Numbers to beat — deterministic baseline (curl, from `eval-output/curl-cve-2023-38545/metrics.md`)

| Metric | Deterministic floor | Bob-session goal |
|---|---|---|
| introducer_top1 / top5 | ✓ / ✓ | hold (normalizer already discards invented introducers) |
| timeline_recall / precision | 0.75 / 1.00 | hold or improve |
| action_item_overlap | 0.333 | beat honestly |
| root_cause_match | 0.295 | beat honestly |
| line_agreement | 0.00 | beat (primary Bob target) |
| claim_linkage_rate | 1.00 (21/21) | **must hold** |
| honesty_check (impact/detection red) | ✓ | **must hold** |
| wall_clock_seconds | ~0 (baseline human ~90 min) | record actuals |

Secondary cases (deterministic, complete): log4j — precision 0.50, actions 0.25, root_cause 0.172; gitlab — recall 0.182, actions 0.786, precision 1.00. Any Bob delta must keep `git diff --stat pmg/eval/` empty — improvements come from better generation, never from touching the scoring.
