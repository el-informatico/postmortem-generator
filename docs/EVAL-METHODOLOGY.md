# Evaluation methodology — how every number in this project is measured

Audience: hackathon judges and any reviewer asking *"how exactly did you measure
that?"*. Everything below is deterministic and AI-free: the harness
(`pmg/eval/compare.py`) is token/heuristic math over the generated postmortem
and a human-written ground truth — no model in the loop, no randomness, same
inputs → same report. Canonical definitions live in `pmg/eval/compare.py`
(module docstring, lines 10-66) with tunable thresholds in one place
(`compare.py:97-102`); this doc is the plain-language mirror with worked
examples from a real run. When in doubt, the code wins.

## The 10-second answer: where does "29%" come from?

1. **Who generated the floor postmortem?** A deterministic template generator
   (`pmg/generator`, the "no AI" fallback) that fills the postmortem sections
   from collected git/GitHub evidence alone. It is **not** a generic LLM and
   **not** a human: it is reproducible rules.
2. **Reproduce it yourself** (offline, ~11 s collection + <1 s generation,
   GitHub cache warm):
   `python3.12 -m pmg.shell.cli postmortem --case data/cases/curl-cve-2023-38545.json --mode deterministic --offline`
   → writes `eval-output/curl-cve-2023-38545/{postmortem.md,eval_report.json,metrics.md}`.
3. **What is it compared against?** The human ground truth
   (`data/ground_truth/ground_truth.json`): the root cause the curl authors
   themselves stated, with quotes and sources — not our paraphrase.
4. **Why is it a legitimate floor?** The same harness and the same ground truth
   will judge the IBM Bob agent runs. Identical yardstick, identical truth:
   the only variable that changes is the generator. And we deliberately did
   **not** use a "generic LLM without evidence" as the floor — that would be a
   straw man punished for hallucinations rather than for lack of rigor.

The 0.29 itself: `root_cause_match` = max(jaccard = 0.200, overlap_ratio =
0.295) over content tokens — i.e. 29.5% of the floor's root-cause tokens are
covered by the human statement+quote (full detail in
`eval-output/curl-cve-2023-38545/eval_report.json`, `detail.root_cause`).

## What counts as "same root cause"

Not exact text, not a human rubric: a **deterministic token-overlap
heuristic**. `root_cause_match = max(jaccard, overlap_ratio)` between
content-tokens of the generated root-cause section (body + claims) and
content-tokens of `gt.root_cause.statement + " " + gt.root_cause.quote`
(`compare.py:42-45`). The directed `overlap_ratio` answers *"what share of the
generated causal claim is backed by the human's own words"* — which is why it,
not jaccard, drives the score. Scaling is continuous (0-1), so "did Bob find
the same cause?" becomes a measurable delta over the floor rather than a yes/no
argued after the fact.

## What counts as "guilty line" — and what doesn't

The harness scores the **introducer at commit granularity**, not file/line:

- `introducer_top1` (bool): the sha the postmortem *commits to* (best-ranked
  evidence candidate whose sha10 appears in the root-cause tokens) equals
  `sha10(gt.introducer.full_sha)`. Exact match, no partial credit.
- `introducer_top5` (bool): the ground-truth sha10 is among the first five
  distinct sha tokens in the section (root-cause texts routinely quote the
  *fix* sha first — top-5 tolerates that quoting style).

Why commit-level: for these incidents the human record itself assigns blame
to a commit ("the main commit for this change", curl blog) — a file/range
answer could not be checked against the ground truth without inventing a
line-mapping nobody published. What we *do* measure against the human prose is
`line_agreement`: sentence-level recall over the human postmortem text (share
of human sentences with ≥6 content tokens that have a counterpart sentence in
the generated markdown with Jaccard ≥ 0.35). It captures *"does the generated
narrative say what the human said"*, a different (and harder) question than
guilt assignment.

## Every metric, its threshold, and its plain meaning

| Metric | Threshold / rule | Plain meaning |
|---|---|---|
| `introducer_top1` / `top5` | sha10 exact match (`compare.py:12-27`) | did we name the commit that introduced the bug? |
| `timeline_recall` | shared sha10 OR (\|Δdate\| ≤ 3 d AND Jaccard ≥ 0.3) | share of human timeline events we reconstructed |
| `timeline_precision` | same pairwise rule | share of our timeline entries that are real events |
| `action_item_overlap` | best `overlap_ratio ≥ 0.35` | share of human action items we also recommend |
| `root_cause_match` | max(jaccard, overlap_ratio), continuous | token agreement with the human's stated cause |
| `honesty_check` | impact+detection must be red+"No evidence" or green/yellow with an external ref | did we refuse to invent what git cannot know? |
| `claim_linkage_rate` | strict: non-empty refs AND refs ⊆ `Evidence.ref_ids()` | every claim cites evidence that actually exists |
| `line_agreement` | sentence Jaccard ≥ 0.35, ≥6 tokens | narrative agreement with the human text |
| `wall_clock_seconds` | verbatim from `pm.meta` | generation time (floor <1 s vs human ≈90 min) |

## Worked examples (real run: curl CVE-2023-38545, deterministic floor)

All from `eval-output/curl-cve-2023-38545/eval_report.json` — nothing below is
constructed for this doc.

**Timeline — MATCH by sha.** GT event 2020-02-14 "Introducer commit
4a4b63daaa… 'On February 14 2020 I landed the main commit for this change'" ↔
generated "2020-02-14 — Candidate introducer commit 4a4b63daaa: socks: make
the connect phase non-blocking". Rule fired: `sha match` (same commit = same
event, regardless of wording).

**Timeline — MATCH by date+content.** GT 2020-02-11 "PR #4907 … opened by
bagder" ↔ generated "2020-02-11 — PR #4907 opened by bagder: socks: make the
connect phase non-blocking" — `date ±0d + jaccard 0.77` (no sha involved; the
date window is ±3 d and the wording differs).

**Timeline — NO match.** GT 2023-09-30 "Issue reported to the curl project by
Jay Satiro" and GT 2023-10-03 "curl project contacted distros@openwall" —
`matched_generated: null`. Both events happened off-repo (private report,
coordinated disclosure list); the deterministic collector cannot see them. This
is the floor's honest blind spot, and it is *why* recall is 0.75 not 1.00.

**Action item — covered.** GT "A - Upgrade curl to version 8.4.0" ↔ generated
"Upgrade to curl 8.4.0 — the first release containing the fix…" — overlap
0.8333 ≥ 0.35 → covered. A subtler cover: GT "Regression test added for the
exact scenario (tests/data/test728…)" ↔ generated "Keep the regression test
added with the fix … passing in CI" — 0.4118 ≥ 0.35 → covered (same action,
different phrasing).

**Action item — NOT covered.** GT "C - Do not use `CURLPROXY_SOCKS5_HOSTNAME`
proxies" best-matches "Upgrade to curl 8.4.0…" at overlap 0.125 < 0.35 → not
covered: mitigation advice is a different action than upgrading. GT "Static
analysis alone was insufficient here" has no generated counterpart at all
(0.0). Six of nine human items are advisory/opinion the repo cannot ground —
that is the 0.33.

## Why per-role narrative confidence, not a numeric score per claim

Sonnet-style advice is "claim + citation + confidence number". We deliberately
keep the contract at `claim + refs` plus a per-role `confidence_notes` string
("what the evidence supports and what it does not",
`pmg/bob/roles.py:37-40`). Reasons: (1) a self-reported number is
unfalsifiable — theater, not rigor; (2) the *harness* already computes the
falsifiable confidence (claim_linkage_rate, honesty_check) from the refs
themselves; (3) forcing numeric per-claim scores invites models to calibrate
to look good, exactly the failure the honesty rule exists to prevent.

## Where to verify all of this

- Definitions + thresholds: `pmg/eval/compare.py` (docstring lines 10-66,
  constants lines 97-102) · canonical names in `docs/CONTRACTS.md`.
- Ground truth with quotes and sources: `data/ground_truth/ground_truth.json`
  (+ per-case dirs for log4j and GitLab).
- Real reports: `eval-output/<case>/eval_report.json` (every metric carries a
  `detail` with the exact pairs/rules shown above).
