# The demo UI — `ui/index.html`

A single self-contained HTML file: the interactive centerpiece of the demo. Open it
directly in a browser (`file://` works — nothing is fetched from the network), or
[view it in GitHub](../ui/index.html).

## What it shows

Per case (the committed demo case is `curl-cve-2023-38545`):

- **Header** — case name, postmortem title, and provenance pills: generator
  (`deterministic-fallback` / `ibm-bob-agents`), wall-clock generation time next to
  the **human baseline ≈ 90 min**, and the claim-linkage rate when an eval report
  exists. A case switcher appears when more than one case is embedded.
- **Interactive timeline** — every `evidence.timeline` event (plus any generated
  timeline-section claim not covered by an event) as a card on a horizontal track
  (vertical on narrow screens). Click, hover or tab to an event: the detail panel
  below shows the full description, the resolved evidence ref, and — when the ref
  maps to a commit or issue — a **real link to GitHub** (commit URLs from the
  evidence, `…/issues/<n>` derived from the case repo). Event kinds are
  color-coded (commit / issue / comment / release); the **fix** is green and the
  **top introducer candidate** red, so the 3.5-year gap reads at a glance.
- **Side by side** — left: the generated postmortem rendered from its sections,
  each with its confidence badge (🟢 every claim linked · 🟡 grounded, some
  unreferenced · 🔴 no evidence, said explicitly) and per-claim **evidence chips**
  that resolve refs to human-readable names (fix sha, issue #, event date) and
  link to GitHub. Right: the **human baseline** markdown (blog / advisory tabs),
  rendered by a tiny safe markdown renderer — headers, lists, bold, code fences,
  links; all HTML is escaped first, images render as text references so nothing
  is ever fetched.
- **Evaluation metrics** — collapsed by default; the `▾ evaluation metrics`
  button reveals the deterministic harness table (metric / description / value,
  ✓–✗ for booleans, fixed-decimal floats, harness heuristics on hover). Rows are
  exactly the metrics in the case's `eval_report.json`.

The raw machine data for each case is also embedded in the page as
`<script type="application/json" id="case-<name>">` for inspection.

## Rebuild

```bash
/usr/bin/python3.12 scripts/build_ui.py                 # all cases -> ui/index.html
/usr/bin/python3.12 scripts/build_ui.py --cases curl-cve-2023-38545 --out ui/index.html
```

Inputs: every `eval-output/<case>/` directory that has a `postmortem.json`
(plus `evidence.json`, required for ref resolution; `eval_report.json` optional —
no metrics toggle without it). A case named explicitly via `--cases` that lacks
`postmortem.json` fails the build with a clear message. `ui/index.html` is
generated **and committed** — judges open it directly; rebuild after changing
pipeline output.

Ground truth discovery: `data/ground_truth/<case>/*.md` per-case directories
(`notes.md` excluded) when present, otherwise the legacy top-level
`blog.md` + `advisory.md` for curl cases. Both layouts work.

Tests: `/usr/bin/python3.12 -m pytest tests/test_build_ui.py -q` (offline;
includes a byte-identical rebuild check and a no-external-resources scan).

## Design constraints

- **Offline single file.** No CDNs, web fonts, images or frameworks — vanilla
  HTML/CSS/JS, everything inline. The only outbound URLs are GitHub links built
  from case data and links that appear inside the human ground-truth text.
- **Deterministic build.** Same inputs → byte-identical output: no timestamps,
  no randomness; rendered markup is produced by `scripts/build_ui.py` (stdlib
  only) at build time. The page is fully readable with JavaScript disabled —
  the inline script only adds interaction (case tabs, event selection, metric
  and document toggles).
- **Theme & responsive.** Light theme with automatic dark mode via
  `prefers-color-scheme`; two-column comparison collapses to one column and the
  timeline switches to vertical below ~900px. No color-only meaning: badges and
  kinds always carry a text/emoji label.
- **Size.** The page skeleton (CSS + JS + chrome) is ~50 KB before embedded
  case data; embedded JSON is slimmed (fix diff and markdown duplicates
  dropped — full files remain in `eval-output/`).

## Screenshot / video tips

- Open `ui/index.html` locally, full-window (~1440px wide) so the two columns
  and the full timeline track sit in one frame; dark mode makes a nice second
  beat (toggle the OS/browser theme).
- Story beat for the video: hover/click `4a4b63daaa` (red dot, *top introducer
  candidate*, 2020-02-14) → detail panel + commit link → then the fix card
  (green dot, 2023-10-11) — the whole "introduced to fixed" arc in two clicks.
- Scroll the left column to the 🔴 **Impact** / **Detection** sections and say
  "no evidence" out loud — that honesty rule is the differentiator; the right
  column (human blog) shows what a 90-minute human narrative looks like.
- End on the metrics table: repo-derivable metrics at ceiling, narrative
  metrics labeled as the Agent-mode target.
