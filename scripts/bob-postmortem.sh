#!/usr/bin/env bash
# bob-postmortem.sh — wrapper delivering the literal `bob postmortem ...` UX.
#
# IBM Bob's CLI (Bob Shell 2.0) has NO native subcommand mechanism: custom
# commands are `.bob/commands/*.md` slash commands usable inside `bob chat`,
# not `bob <subcommand>` (docs/research/ibm-bob-notes.md §3). The syntax
#
#     bob postmortem --repo OWNER/NAME --issue N --fix-sha ABC
#
# therefore ships as this thin wrapper around the `bob-postmortem` console
# script installed by this repo (pip install -e .).
#
# Usage (both forms are accepted; a leading "postmortem" is optional):
#     scripts/bob-postmortem.sh postmortem --case data/cases/curl-cve-2023-38545.json
#     scripts/bob-postmortem.sh --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6
#
# Making it feel like a real subcommand:
#     alias bob.pm="$(pwd)/scripts/bob-postmortem.sh"     # bob.pm --case ...
#     # or, with pip install -e ., the console script is already on PATH:
#     bob-postmortem postmortem --case data/cases/curl-cve-2023-38545.json
set -euo pipefail

if [ "${1:-}" = "postmortem" ]; then
  shift  # accept both `bob-postmortem postmortem ...` and direct flags
fi

if command -v bob-postmortem >/dev/null 2>&1; then
  exec bob-postmortem postmortem "$@"
fi

# Fallback when the console script is not on PATH (no `pip install -e .`).
# Prefer python3.12 (the interpreter pmg is installed for; the module form
# works from any cwd). Bare `python3` is the last resort: it only works when
# the cwd happens to be the repo root (sys.path[0] for -c is the cwd).
if command -v python3.12 >/dev/null 2>&1 \
   && python3.12 -c "import pmg" >/dev/null 2>&1; then
  exec python3.12 -m pmg.shell.cli postmortem "$@"
fi
exec python3 -c 'import sys; from pmg.shell.cli import main; sys.exit(main())' \
  postmortem "$@"
