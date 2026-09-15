---
description: Generate an evidence-linked SRE postmortem for an incident fixed by a given commit
argument-hint: --repo <owner/repo> --issue <n> --fix-sha <sha> [--mode auto|bob|deterministic]
---
Generate a postmortem for the incident fixed by the commit given in
$ARGUMENTS by running the postmortem-generator pipeline (evidence first,
honesty always).

## Invocation

Shell out to the project CLI (entry point `bob-postmortem`, subcommand
`postmortem`):

```bash
bob-postmortem postmortem --repo <owner/repo> --issue <n> --fix-sha <sha> [--mode auto|bob|deterministic] [--out postmortem.md]
```

For example, for the reference case used in development:

```bash
bob-postmortem postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6
```

If the `bob-postmortem` entry point is not installed, run the module
directly: `/usr/bin/python3.12 -m pmg.shell.cli postmortem --repo ... --issue
... --fix-sha ...` from the repository root.

## Modes and fallbacks

- `--mode auto` (default): use the IBM Bob multi-agent pipeline when the
  `bob` binary is on PATH and `BOB_API_KEY` is set; otherwise fall back to
  the deterministic no-AI generator and record why in `meta.fallback_reason`.
- `--mode bob`: force the Bob pipeline (fails loudly if unavailable).
- `--mode deterministic`: force the offline, no-AI floor.

## How it behaves (evidence first)

1. A deterministic collector gathers evidence from repository data only:
   fix commit + diff, linked issue threads, SZZ-lite introducer candidates,
   timeline events. Nothing is inferred.
2. Four subagent roles (custom chat modes in `.bob/custom_modes.yaml`:
   commit-archaeologist, document-analyst, code-reviewer, sre-synthesizer)
   analyze their evidence slice and synthesize the SRE template.
3. Every claim in the output carries refs into the evidence; a linkage
   validator reports any claim that does not.

## Honesty rule (binding)

Repository data contains no user impact and no detection story. The
`impact` and `detection` sections are emitted with badge 🔴 red and a
"No evidence" body unless external evidence was actually ingested. Never
invent dates, numbers, impact or detection stories — sections without
evidence say so, and that is the point.

After running the command, show the generated markdown to the user and
point out which sections are green/yellow/red and why.
