# CI — `bob postmortem` in GitHub Actions

The workflow in [`.github/workflows/postmortem.yml`](../.github/workflows/postmortem.yml)
runs the full postmortem pipeline on GitHub's runners. There is no official
IBM Bob Action (research in [`docs/research/ibm-bob-notes.md`](research/ibm-bob-notes.md) §3),
so the job installs *this repo* and drives our own CLI, `bob-postmortem`.
When `BOB_API_KEY` is configured, the Bob integration (`pmg.bob`) shells out
to `bob run` on the runner itself.

## How the Action works

One job, five steps (idempotent — safe to re-run):

1. **Checkout (fetch-depth: 0)** — full history of the workflow repo; git
   history is our evidence base when the subject repo *is* this repo.
2. **Clone subject repository** — `git clone <subject_repo_url> .repos/curl`
   (skipped when the directory already exists). Default subject:
   `https://github.com/curl/curl`. The clone is a full clone on purpose:
   SZZ-lite needs blame/log over the whole history.
3. **Setup Python 3.12** (pip cache keyed off `pyproject.toml`).
4. **`pip install -e .`** — puts the `bob-postmortem` console script on PATH.
5. **Run pipeline** —
   `bob-postmortem postmortem --case <case> --local-repo .repos/curl --mode <mode> --out eval-output/curl-cve-2023-38545`,
   then upload `eval-output/**` as the `postmortem` artifact (uploaded even
   on failure, for debugging).

Triggers:

- `workflow_dispatch` with inputs: `case` (case config path, default
  `data/cases/curl-cve-2023-38545.json`), `subject_repo_url`, `mode`
  (`auto|bob|deterministic`, default `auto`), `offline` (default `false`).
- `push` to `main` touching `data/cases/**`, `pmg/**` or the workflow file —
  a cheap smoke run: mode falls back to `deterministic` (no Bobcoin spend,
  even when `BOB_API_KEY` is configured); the collector's few GitHub API
  calls use the automatic `GITHUB_TOKEN`.

## Secrets

| Secret | Required | Notes |
|---|---|---|
| `GITHUB_TOKEN` | automatic | Provided by Actions; authenticates the collector's GitHub API calls (higher rate limits for private subject repos). |
| `BOB_API_KEY` | **optional** | IBM Bob API key (Inference type, `bob.ibm.com` portal). In `auto` mode an absent/invalid key degrades to the deterministic generator — the job still exits 0. Only an explicit `--mode bob` run exits 4 when Bob is unavailable. |

## Local usage

```bash
pip install -e .                       # installs the bob-postmortem console script

# From a case file (offline, over the local curl clone):
bob-postmortem postmortem --case data/cases/curl-cve-2023-38545.json \
    --local-repo .repos/curl --offline

# From the bare trio (synthesizes a case named <repo>-<fixsha7>):
bob-postmortem postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6 \
    --local-repo .repos/curl

# The direct flag form also works (subcommand is implied):
bob-postmortem --case data/cases/curl-cve-2023-38545.json
```

Outputs land in `eval-output/<case-name>/`: `evidence.json`,
`postmortem.json`, `postmortem.md`, `linkage.json`, and — when ground truth
is found — `eval_report.json` + `metrics.md`.

Exit codes: `0` ok · `2` usage · `3` offline cache miss · `4` Bob unavailable
(explicit `--mode bob`) · `5` unexpected error.

### The `bob postmortem` wrapper

IBM Bob's CLI has **no native subcommand mechanism** — custom commands are
`.bob/commands/*.md` slash commands inside `bob chat` (research notes §3).
The literal `bob postmortem ...` syntax is therefore delivered by
[`scripts/bob-postmortem.sh`](../scripts/bob-postmortem.sh):

```bash
scripts/bob-postmortem.sh postmortem --case data/cases/curl-cve-2023-38545.json
alias bob.pm="$(pwd)/scripts/bob-postmortem.sh"   # then: bob.pm --case ...
```

## Offline cache contract

- `data/cache/` (the collector's GitHub API disk cache) is **gitignored and
  NOT committed** — it is rebuildable, and CI fetches fresh responses with
  `GITHUB_TOKEN` instead.
- To run fully offline locally, warm the cache first:
  `python3 scripts/refresh_cache.py` (piece 1 owns it), then pass `--offline`.
- `--offline` with a cold cache raises `OfflineCacheMiss` → the CLI prints a
  hint (`run scripts/refresh_cache.py first`) and exits `3`.
