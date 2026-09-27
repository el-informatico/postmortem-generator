<!--
Deck source (canonical) — Incident Postmortem Generator, IBM Bob 2.0 hackathon (lablab.ai, Sep 2026).
Rendered to PDF by scripts/build_deck.py (python3.12 scripts/build_deck.py).
Grammar understood by the builder:
  - slides separated by a lone `---` line
  - `# Title` per slide; `## subtitle` (title slide); bullets `- `; pipe tables
  - directives `::kicker <text>::` and `::layout <name>::`
  - inline **bold** and `code`; badge emoji map to colored dots in the PDF
Rules honored: real metrics only (eval-output/ 2026-09-27), no local paths, no internal infra names, EN.
-->

# Honest Postmortems from Repository Evidence

::kicker IBM BOB 2.0 HACKATHON · LABLAB.AI · SEP 2026::

## From the fix commit to a full incident postmortem — which commit introduced the bug, the timeline, the root cause, the prevention plan. Every claim linked to evidence. Nothing invented.

- 🟢 every claim linked to evidence · 🟡 grounded, some claims unreferenced · 🔴 no evidence (declared)
- Incident Postmortem Generator · solo builder · github.com/el-informatico/postmortem-generator · Apache-2.0

---

# The postmortem nobody has time to write

::kicker PROBLEM::

- An incident ends. The fix is merged. And the postmortem — the document where the team actually learns — never gets written.
- Writing one costs a senior engineer ~90 minutes, weeks after the pager went quiet. So most postmortems simply don't exist.
- Incident-management tools (Rootly, PagerDuty, incident.io, FireHydrant) generate postmortems from the managed incident stack: alerts, Slack threads, timelines.
- Most bug fixes leave none of that behind. There is no incident record to mine — but the repository remembers everything.
- The evidence for the postmortem already exists, untouched, in the issue, the fix commit, and the commit that introduced the bug.

---

# Repo-first postmortems, honesty enforced

::kicker SOLUTION::

- Start from the repository, not the incident stack: give it a repo, the issue behind a bug, and the SHA of the fix — get a full postmortem out.
- Introducer discovery via **SZZ-lite**: blame, pickaxe and issue linkage trace the fix's deleted lines back to the commit that introduced the bug.
- A deterministic collector (GitHub API + git CLI, zero AI) builds the evidence; parallel IBM Bob role agents analyze it; an SRE synthesizer writes the report.
- Every claim carries evidence refs. Every section carries a confidence badge. Sections git cannot ground are declared 🔴 No evidence — the harness FAILS any run that invents them.
- A complement to telemetry-centric AIOps (Instana, Cloud Pak): it closes the post-fix loop those stacks never see. Honesty is enforced, not promised.

---

# Four separable pieces — not a prompt wrapper

::kicker ARCHITECTURE::
::layout architecture::

- 1. COLLECTOR — deterministic, AI-free: GitHub API (cached) · git CLI · SZZ-lite introducer candidates → evidence.json
- 2. IBM BOB ORCHESTRATION — Agent mode: 4 parallel role subagents, binding honesty rules, strict JSON output contracts
- 3. SRE TEMPLATE — every claim carries evidence refs · 🟢🟡🔴 confidence badges · normalizer strips invented impact/detection
- 4. EVALUATION HARNESS — deterministic, AI-free scoring against the real human postmortem

- Ships as `bob postmortem --repo … --issue … --fix-sha …` (Bob Shell slash command) and a post-merge CI step; an offline deterministic fallback runs wherever no key is configured.
- The prompt is the last 10% — the product is the pipeline.

---

# How IBM Bob 2.0 was used

::kicker APPLICATION OF TECHNOLOGY::

- **Agent mode, custom role modes** (`.bob/`): Commit Archaeologist · Document Analyst · Code Reviewer · SRE Synthesizer — parallel subagents, each seeing ONLY its slice of the evidence.
- **Binding honesty rules + output contracts per role**: JSON findings only, refs restricted to the provided evidence ref-id list; a normalizer discards any invented impact or detection text.
- **Document understanding over real issue threads**: curl issue #4907 is a PR that was closed *unmerged* — a tool that assumes "closed means merged" gets this case wrong.
- **Full session evidence trail**: per-task consumption summaries (task ID, tokens, cost) captured in `bob_sessions/` — see the Evidence slide.
- **Measured cost, not estimates**: $0.07 across the four role sessions ($0.10 including the access smoke test) — the 40-Bobcoin sprint budget essentially untouched.
- Scope, stated plainly: deterministic core is pre-sprint work (open, dated git history); the IBM Bob integration layer was built in the sprint window.

---

# Real numbers against the human postmortem — no spin

::kicker METRICS · CURL CVE-2023-38545::

| Metric (vs Daniel Stenberg's hand-written postmortem) | Deterministic floor | IBM Bob 4-role run |
|---|---|---|
| introducer top-1 / top-5 | ✓ exact (4a4b63daaa) | ✓ exact (4a4b63daaa) |
| honesty check (impact & detection red) | ✓ | ✓ |
| claim linkage | 1.00 (21/21) | 1.00 (26/26) |
| timeline recall / precision | 0.75 / 1.00 | 0.75 / 1.00 |
| action-item overlap | 0.33 | 0.22 |
| root-cause match | 0.29 | 0.14 |
| line agreement (human prose) | 0.00 | 0.01 |
| wall clock | <1 s | 56 s (human: ~90 min) |

- Repo-derivable metrics hold at ceiling under agent mode, with a richer report: 26 linked claims vs 21, every timeline entry precise.
- Narrative overlap did **not** beat the deterministic floor yet — reported as-is. That open gap is the declared next target, not a hidden number.

---

# Every session has a receipt

::kicker EVIDENCE · BOB_SESSIONS/::

| Bob session (custom role mode) | Task ID | Context tokens | Cost |
|---|---|---|---|
| Commit Archaeologist | 13e68f09bab1b1b5 | 8,676 | $0.017 |
| Document Analyst | 2d8266ccd2f2bb4d | 5,854 | $0.012 |
| Code Reviewer | 900fb3e2e9a5ac1f | 7,893 | $0.016 |
| SRE Synthesizer | d32e706198b8c736 | 14,695 | $0.029 |
| Access smoke test | f404dad9621609031 | — | $0.022 |

- Screenshots of each task-session summary + exported task histories live in `bob_sessions/` in the repo — judges can audit every claim on this deck.
- The scored case is real: curl CVE-2023-38545 — introducer `4a4b63daaa` (2020-02-14) → fix `fb4415d8aee6` (2023-10-11): the bug's origin story, **1,335 days** before the fix.
- Evaluation is deterministic and AI-free — 175 offline tests, byte-reproducible scoring.

---

# Where it doesn't work (yet)

::kicker HONEST LIMITS::

- **One case scored end-to-end** (curl). Two further real cases exercise the edges of the approach:
- **log4j CVE-2021-44228** — introducer top-1 ✗: SZZ-lite honestly blames later JNDI refactors, not the 2013 component introduction. The floor's known blind spot, visible by design.
- **GitLab 2017 database outage** — an ops incident with no fix commit: degrades to an issues-only reconstruction and says so (resolution: 🔴 No evidence — no fix commit).
- **Attribution is candidates, not proof**: every attribution carries its score and badge; a wrong guess surfaces in yellow or red — never buried under confident prose.
- Agent-mode narrative scores still sit below the deterministic floor (see Metrics) — shown, not spun.

---

# Demo & repository

::kicker SEE IT RUN::

- **Demo video (4:27)**: the full pipeline over the real curl CVE — interactive timeline UI, click-through from any claim to its evidence, side-by-side vs the human postmortem.
- **Repo**: github.com/el-informatico/postmortem-generator (public, Apache-2.0)
- One command: `bob postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6`
- 3 real cases · 175 offline tests · CI workflow · deterministic, byte-reproducible evaluation
- IBM Bob 2.0 is the orchestration layer. Your repository is the evidence. The postmortem nobody had time to write — in seconds, with receipts.
