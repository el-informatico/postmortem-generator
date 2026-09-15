# Incident Postmortem Generator

**From the fix commit to a full incident postmortem — starting from the repository, not
from the incident stack.** Built for the IBM Bob 2.0 hackathon (lablab.ai, Sep 2026).

Incident-management tools (Rootly, PagerDuty, incident.io Nexus Code, FireHydrant) generate
postmortems from *managed incident data*: alerts, Slack threads, timelines. This project
closes the **post-fix loop** the incident stack cannot see: give it a repository, the issue
behind a bug and the SHA of the commit that fixed it, and it reconstructs the incident from
**repository evidence** — **which commit introduced the bug** (SZZ-lite), a timeline, the
root cause, and a prevention plan. Every claim links to its evidence; every section carries
a **confidence badge**; sections repository data cannot ground (user impact, detection,
telemetry) are declared **"No evidence"** instead of invented.

Everything is demonstrated and evaluated against a **real, human-written postmortem**:
[curl CVE-2023-38545](https://curl.se/docs/CVE-2023-38545.html) — the SOCKS5 heap buffer
overflow introduced by `4a4b63daaa` (2020-02-14, shipped in 7.69.0) and fixed by
`fb4415d8aee6` (Jay Satiro, 2023-10-11, released in 8.4.0), as narrated by Daniel Stenberg
in ["How I made a heap overflow in curl"](https://daniel.haxx.se/blog/2023/10/11/how-i-made-a-heap-overflow-in-curl/).
No synthetic data anywhere in the demo or evaluation.

## Architecture (anti-prompt-wrapper)

The product is **not** "a prompt that reads git log". Four separable pieces:

```
┌──────────────────┐   ┌────────────────────────────┐   ┌────────────────────────┐
│ 1. COLLECTOR     │──▶│ 2. IBM BOB ORCHESTRATION   │──▶│ 4. EVALUATION HARNESS  │
│ deterministic,   │   │ Agent mode: 3-4 parallel   │   │ deterministic, AI-free │
│ AI-free:         │   │ role agents (see .bob/) +  │   │ vs. the real human     │
│ git CLI + GitHub │   │ SRE template + per-claim   │   │ postmortem (curl)      │
│ API + SZZ-lite   │   │ evidence linkage + badges  │   └────────────────────────┘
└──────────────────┘   └─────────────┬──────────────┘
                         │ determinist│c fallback (offline, no Bobcoins)
                         ▼           ▼
                       ┌────────────────────────────┐
                       │ 3. BOB SHELL / CI          │
                       │ bob postmortem --repo X    │
                       │   --issue N --fix-sha ABC  │
                       │ .github/workflows/…yml     │
                       └────────────────────────────┘
```

1. **Collector** (`pmg/collector`) — deterministic Python, zero AI: GitHub REST API (disk-cached,
   offline-replayable) + git CLI over a local clone. Produces the evidence JSON: issue
   threads, fix commit + diff, and introducer candidates via three methods — **SZZ blame**
   (trace the fix's removed lines at `fix~1`), **`git log -S` pickaxe** (oldest commit
   touching the vulnerable identifiers), and **issue linkage** (commit ↔ issue cross-refs) —
   after Śliwerski–Zimmermann–Zeller (MSR 2005).
2. **IBM Bob orchestration** (`pmg/bob`, `.bob/`) — Agent mode subagents with distinct
   roles: *commit archaeologist*, *document analyst* (issues/advisories), *code reviewer*
   (fix diff with repo context), *SRE synthesizer*. Role prompts embed only the evidence
   slice + the binding honesty rules; a normalizer discards any model-invented impact or
   detection text. A fully offline **deterministic fallback** fills the same template from
   evidence alone (used in CI and in every test).
3. **Bob Shell / CI** (`pmg/shell`, `.github/workflows/postmortem.yml`) —
   `bob postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6` as a post-merge CI
   step (`.bob/commands/postmortem.md` ships the Bob-side slash command; the GitHub Action
   degrades to deterministic mode when no `BOB_API_KEY` secret is configured).
4. **Evaluation harness** (`pmg/eval`) — deterministic, AI-free comparison against the
   human postmortem: exact introducer↔fix linkage, timeline recall/precision, action-item
   overlap, root-cause match, honesty check, claim-linkage rate, sentence-level agreement
   with the human text.

### The honesty rule

Git history contains no user impact, no telemetry, no detection story. The generator
**must** emit those sections as 🔴 *No evidence* — and the harness fails the run if it
invents them. Badges: 🟢 every claim linked to evidence · 🟡 grounded, some claims
unreferenced · 🔴 no evidence (said explicitly).

## Evaluation — real case, deterministic floor

The table below is the **actual output** of the full offline pipeline over the real curl
case (deterministic fallback, no AI, no Bobcoins — `eval-output/curl-cve-2023-38545/metrics.md`):

| Metric | Value | Notes |
|---|---|---|
| introducer_top1 | ✓ | Predicted `4a4b63daaa` = ground truth (SZZ-blame + issue-link; real top-1) |
| introducer_top5 | ✓ | |
| timeline_recall | 0.38 | 3/8 human events; the rest (releases, distros mail, disclosure) are not in git |
| timeline_precision | 0.60 | |
| action_item_overlap | 0.11 | 1/9 — the deterministic floor cites only repo-grounded items |
| root_cause_match | 0.22 | diff-facts without narrative |
| honesty_check | ✓ | impact & detection declared "No evidence" |
| claim_linkage_rate | 1.00 | 15/15 claims carry valid evidence refs |
| line_agreement | 0.00 | sentence-level recall vs. the human postmortem text |
| wall_clock_seconds | <1s | evidence collection 11s + generation; human baseline ≈ 90 min/postmortem |

Repo-derivable metrics (linkage, honesty, grounded timeline) are already at ceiling without
any AI. Narrative metrics (root cause, action items, line agreement) are the explicit target
of the Bob Agent-mode sessions during the sprint — this table is the baseline they must beat.

## Quick start

```bash
git clone https://github.com/el-informatico/postmortem-generator && cd postmortem-generator
git clone https://github.com/curl/curl .repos/curl      # offline evidence base (~155 MB)
pip install -e ".[dev]"
pytest                                                 # 130 tests, offline

# full offline pipeline over the real curl case (deterministic fallback)
bob-postmortem postmortem --case data/cases/curl-cve-2023-38545.json \
    --local-repo .repos/curl --offline --out eval-output/curl-cve-2023-38545

# or the trio form
bob-postmortem postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6 \
    --local-repo .repos/curl
```

Outputs: `evidence.json` (piece 1), `postmortem.md` (+ `.json`) with badges and per-claim
evidence refs, `linkage.json`, and — when ground truth exists — `metrics.md` +
`eval_report.json` (piece 4). With `BOB_API_KEY` set and the `bob` CLI installed,
`--mode auto` routes analysis through the real IBM Bob agents instead of the fallback.

## Repository layout

```
pmg/collector/     piece 1 — GitHub API (cached) · git CLI · SZZ-lite
pmg/bob/           piece 2 — roles · SRE template · linkage · orchestrators
pmg/shell/         piece 3 — `bob postmortem` CLI (console script bob-postmortem)
pmg/eval/          piece 4 — ground truth · comparison heuristics · report
.bob/              Bob-side integration: slash command · custom role modes · skill
.github/workflows/postmortem.yml     CI step (workflow_dispatch + push smoke)
data/cases/        case configs (curl-cve-2023-38545.json)
data/ground_truth/ human postmortem material (cached with attribution; see its NOTES)
docs/research/     verified research notes (IBM Bob integration, hackathon status, case)
docs/CONTRACTS.md  the cross-piece interface contract
eval-output/       committed pipeline output for the real curl case
STATUS.md          build log (pre-sprint → sprint)
```

## Credits & sources

- Ground truth: [curl CVE-2023-38545 advisory](https://curl.se/docs/CVE-2023-38545.html) and
  Daniel Stenberg's [postmortem](https://daniel.haxx.se/blog/2023/10/11/how-i-made-a-heap-overflow-in-curl/)
  (cached under `data/ground_truth/` for reproducible evaluation — copyright remains with
  the authors; the source URLs are authoritative).
- SZZ: Śliwerski, Zimmermann, Zeller, *"When Do Changes Induce Fixes?"* (MSR 2005).
- Template outline: Google SRE postmortem template (via dastergon/postmortem-templates, CC0-1.0).

## License

Apache-2.0 — see [LICENSE](LICENSE).
