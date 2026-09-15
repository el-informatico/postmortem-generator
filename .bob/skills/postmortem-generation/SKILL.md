---
name: postmortem-generation
description: Generate an evidence-linked SRE incident postmortem from repository history (fix commit, issue thread, introducer candidates) with honesty badges for sections the repository cannot ground
---
# Postmortem generation

Use this skill when asked to write, draft or review an incident postmortem
for a bug that was fixed by a specific commit. It drives the
postmortem-generator pipeline, which is evidence-first: every claim links to
repository evidence, and sections without evidence say so.

## Pipeline steps

1. **collect** — deterministic evidence collection from repository data only
   (fix commit + diff, linked issue threads, SZZ-lite introducer candidates,
   timeline). No AI, no invention.
2. **roles** — three analyst roles analyze their evidence slice in parallel
   (`commit-archaeologist`, `document-analyst`, `code-reviewer`), then
   `sre-synthesizer` merges everything into the SRE template. Implemented as
   parallel `bob run --chat-mode=<slug> --format json` processes
   (see `.bob/custom_modes.yaml`).
3. **synthesize** — 8 sections (summary, impact, timeline, root_cause,
   detection, resolution, action_items, lessons), each with an honesty badge:
   🟢 green = every claim carries a valid evidence ref · 🟡 yellow = grounded,
   some claims unreferenced · 🔴 red = no evidence.
4. **validate linkage** — every claim's refs must be valid evidence ids;
   invalid claims are reported with their section.
5. **eval** (optional) — compare against the human ground-truth postmortem
   when one exists for the case.

## Honesty rule (binding)

Repository data contains no user impact and no detection story. The impact
and detection sections are 🔴 red with a "No evidence" body unless external
evidence was actually ingested. Never invent dates, numbers, impact or
detection stories.

## Example invocation

```bash
# full pipeline, auto mode (Bob agents when available, deterministic fallback)
bob-postmortem postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6

# offline / no-AI floor
bob-postmortem postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6 --mode deterministic
```

The interactive equivalent is the `/postmortem` slash command
(`.bob/commands/postmortem.md`).
