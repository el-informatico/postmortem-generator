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
No synthetic data anywhere in the demo or evaluation. Two further **real cases** extend the
corpus: **log4j CVE-2021-44228** (fix = merge of [PR #608](https://github.com/apache/logging-log4j2/pull/608),
introducer verified as `f1a0cac60f` "LOG4J2-313 - Add JNDILookup", 2013-07-18) and the
**GitLab 2017 database outage** (an operational incident with *no fix commit* — the
issues-only honesty path).

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
| timeline_recall | 0.75 | 6/8 human events; the missing two (private report, distros mail) are not in git |
| timeline_precision | 1.00 | milestone curation: every generated timeline entry matches a human event |
| action_item_overlap | 0.33 | 3/9 — upgrade-to-fix-release, apply-the-patch, regression test; the other six are advice/opinion the repo cannot ground |
| root_cause_match | 0.29 | causal chain quoting the fix's own message and diff strings |
| honesty_check | ✓ | impact & detection declared "No evidence" |
| claim_linkage_rate | 1.00 | 21/21 claims carry valid evidence refs |
| line_agreement | 0.00 | sentence-level recall vs. the human postmortem text |
| wall_clock_seconds | <1s | evidence collection 11s + generation; human baseline ≈ 90 min/postmortem |

Repo-derivable metrics (linkage, honesty, grounded timeline) are already at ceiling without
any AI. Narrative metrics (root cause, action items, line agreement) are the explicit target
of the Bob Agent-mode sessions during the sprint — this table is the baseline they must beat.

Methodology (what each metric means, its threshold, worked match/no-match examples from the
real run, and where the 29% comes from): **[docs/EVAL-METHODOLOGY.md](docs/EVAL-METHODOLOGY.md)**.

### Secondary cases (real, quote-faithful ground truth)

| Case | Kind | Pipeline result (deterministic floor) |
|---|---|---|
| [log4j CVE-2021-44228](data/ground_truth/log4j-cve-2021-44228/) | code (JVM) | honesty ✓ · linkage 1.0 · introducer top-1 ✗ — SZZ-lite honestly blames later JNDI refactors, not the 2013 component introduction: the floor's known blind spot, visible by design |
| [GitLab 2017 DB outage](data/ground_truth/gitlab-2017-db-outage/) | ops, no code | honesty ✓ · linkage 1.0 · timeline precision 1.0 · resolution section red "No evidence — no fix commit" — reconstructs from the issue thread instead of inventing code |

## Viewer UI

`ui/index.html` is a **single-file, offline** viewer (no CDNs, no build tools — rebuild with
`python3 scripts/build_ui.py`): interactive **timeline** with deep links to the real commits
and issues (fix in green, top introducer candidate in red), **side-by-side** generated
postmortem (per-section badges + evidence chips) vs the human original, and the metrics
table per case, with a case switcher for the whole corpus. Open it directly in a browser.

## Quick start

```bash
git clone https://github.com/el-informatico/postmortem-generator && cd postmortem-generator
git clone https://github.com/curl/curl .repos/curl      # offline evidence base (~155 MB)
pip install -e ".[dev]"
pytest                                                 # 175 tests, offline

# full offline pipeline over the real curl case (deterministic fallback)
bob-postmortem postmortem --case data/cases/curl-cve-2023-38545.json \
    --local-repo .repos/curl --offline --out eval-output/curl-cve-2023-38545

# or the trio form
bob-postmortem postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6 \
    --local-repo .repos/curl

# the viewer (single-file, opens offline in any browser)
python3 scripts/build_ui.py && xdg-open ui/index.html
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
scripts/build_ui.py + ui/index.html   the offline single-file viewer
.bob/              Bob-side integration: slash command · custom role modes · skill
.github/workflows/postmortem.yml     CI step (workflow_dispatch + push smoke)
data/cases/        case configs (curl CVE-2023-38545 · log4j CVE-2021-44228 · GitLab 2017)
data/ground_truth/ human postmortem material per case (cached with attribution; see NOTES)
docs/research/     verified research notes (IBM Bob integration, hackathon status, case)
docs/CONTRACTS.md  the cross-piece interface contract · docs/UI.md · docs/video-script.md
eval-output/       committed pipeline output for the real cases
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
