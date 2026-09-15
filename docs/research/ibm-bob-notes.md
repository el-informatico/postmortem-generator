# IBM Bob 2.0 — integration research notes

Research date: 2026-09-15. For: Incident Postmortem Generator (IBM Bob 2.0 hackathon, lablab.ai, 25–27 Sep 2026).
Method: read-only web research (DuckDuckGo MCP + fetch). Every syntax example below is marked with its source URL. Items NOT found are explicitly marked.

---

## 1. What IS IBM Bob (incl. "2.0", GA, doc URLs)

- **Definition (official docs):** "IBM Bob is an AI SDLC (Software Development Lifecycle) partner that augments your existing workflows and helps you work confidently with real codebases." — https://bob.ibm.com/docs/ide
- **Positioning:** "AI coding agent and AI-powered development partner that automates the full software development lifecycle." — https://www.ibm.com/products/ai-coding-agent (search snippet)
- **Architecture (V2):** three tiers — The Agent (agentic loop, identical in every client), The Harness (auth, logging, feature flags, telemetry), The Clients (IDE, shell). V1 had separate IDE/shell codebases; V2 unified them. — https://bob.ibm.com/blog/bob-v2-release-announcement/
- **Version timeline:**
  - Bob 1.0 GA: ~April 2026 ("IBM's AI coding 'partner' Bob hits general availability", The Register, 2026-04-28 — search snippet; IT Jungle "IBM Gets Bob 1.0 Off The Ground" 2026-03-02).
  - **Bob V2 GA: June 24, 2026** — "Bob V2 reaches general availability on June 24… it's built on a single agent that behaves identically across every client. That agent ships first in Bob IDE, with Bob Shell following soon." — https://bob.ibm.com/blog/bob-v2-release-announcement/
  - IT Jungle: "Big Blue Ships Bob 2.0 And Premium Package For IBM i" (2026-07-13) — https://www.itjungle.com/2026/07/13/big-blue-ships-bob-2-0-and-premium-package-for-ibm-i/ (search snippet)
- **What 2.0 added** (all from the V2 blog post, https://bob.ibm.com/blog/bob-v2-release-announcement/):
  - Subagents with clean context ("only the summary comes back to the main agent").
  - Parallel native tool calling (several tools per turn; "a task that took around 30 seconds in V1 often finishes in under 10").
  - Context window 200k → **270k tokens**.
  - Modes folded 5 → 3: **Agent / Plan / Ask**.
  - Read ops pre-approved; state-changing ops (edit, execute, MCP, skills) still require approval; approval "can be tightened or loosened per tool class".
  - Background tasks (several tasks in parallel, each with own thread/context; task panel).
  - Rollback (per task / per turn / per tool call; no longer git-based).
  - **Document ingestion: "V2 reads `.docx`, `.pdf`, and `.xlsx` files natively"**; output side: "Bob can produce a single self-contained HTML summary of what it found".
  - Workflows (deterministic + AI + human steps); premium packages (Java Modernization, IBM i, IBM Z).
  - Reads "existing conventions, rules files, commands, and MCP servers" from other AI coding tools; supports "the plugin format that's become a de-facto standard across the ecosystem".
  - Roadmap tease: "running agents remotely and reaching them from any client, having multiple agents coordinate on a single task" — no dates.
- **IMPORTANT deadline:** "IDE v1.0.3 and v2.0.0 will stop working on September 30, 2026" — must be on v2.0.2+. — https://bob.ibm.com/docs/ide (applies to IDE; check Shell version at install).
- **Official doc URLs:**
  - Product: https://bob.ibm.com/ ; docs hub (IDE): https://bob.ibm.com/docs/ide ; Shell docs: https://bob.ibm.com/docs/shell
  - Download/releases: https://bob.ibm.com/download , https://bob.ibm.com/releases?bob=shell
  - Pricing: https://bob.ibm.com/pricing ; trial: 30 days / 50 Bobcoins
  - IBM Developer component: https://developer.ibm.com/components/ibm-bob/ (tutorials at /tutorials/)
  - GitHub (issues + releases mirror): https://github.com/IBM/ibm-bob ; demo repo: https://github.com/IBM/bob-demo
  - Community: IBM Community "IBM Project Bob" group (community.ibm.com)

## 2. Agent mode: modes, subagents, orchestration

### Modes (built-in) — https://bob.ibm.com/docs/ide/features/modes
Three modes. Exact role definitions quoted from docs:

| Mode | Role definition (verbatim, abbreviated) | Tools | Allowed subagents |
|---|---|---|---|
| Agent | "You are Bob, a highly skilled software engineer…" | `Read`, `Edit`, `Execute`, `MCP`, `Skill`, `Todo`, `Subtask`, `Subagent`, `Mode` | All |
| Plan | "…use the create-plan skill to gather information and get context to create a plan…" | `Read`, `Edit`, `MCP`, `Skill`, `Subagent`, `Mode` | `Explore` |
| Ask | "…knowledgeable technical assistant focused on answering questions…" | `Read`, `MCP`, `Skill`, `Subagent`, `Mode` | `Explore` |

Mode switching: dropdown, `Ctrl+.`/`⌘+.`, suggestions, or autonomous mid-task switch. In Shell: `--mode <agent|plan|ask>` flag or `/mode` command.

### Subagents — https://bob.ibm.com/docs/ide/features/subagents
- "A subagent is an independent agent that Bob can spawn to handle a focused, self-contained task. It runs in its own isolated context window… returns a summary of the results back to the main conversation."
- **Two subagent types only (built-in):** `explore` ("Read-only codebase exploration, runs on a lighter model") and `general` ("Full tool access, runs on the default model"). You CANNOT define custom subagent role personas with their own prompts — roles come from modes, not subagent definitions.
- Spawn flow: Bob passes a task description; user approves each spawn in interactive sessions ("You are prompted to approve the spawn before it starts"); subagent runs isolated ("does not share state, files, or tool results with Bob unless Bob explicitly passes them"); returns summary.
- `fork_context: true` option passes parent conversation history to the subagent (docs mention Bob "can set" it; not a user-facing config knob documented).
- Parallel subagents: "When multiple subagents run at the same time — for example, during a workflow that spawns several specialized agents in parallel — they are grouped into a single collapsible panel" with aggregate stats (completed/total, tools used, tokens, cost, elapsed, failed tool calls). Good screenshot material.
- Bob uses subagents sparingly by default (only for self-contained, context-heavy tasks). Workflows (premium packages) are the sanctioned way to force parallel fan-out (heidloff.net example: "Generate Unit Tests (AI-driven / Parallel Sub-Agents)" step spawning 3 parallel subagents — https://heidloff.net/article/workflows-sub-agents-ibm-bob/).
- **No public API/SDK to spawn subagents directly.** Orchestration is: (a) prompt-level (ask Agent mode to fan out), (b) custom modes that permit subagents, (c) Workflows (authoring "opens up once the API surface settles with early adopters" — i.e., NOT generally available at V2 GA; https://bob.ibm.com/blog/bob-v2-release-announcement/).
- Shell flags: `--disable-subagents` (bob run); `session.subagents: true|false` in settings.json — https://bob.ibm.com/docs/shell/getting-started/start-bobshell-non-interactive , https://bob.ibm.com/docs/shell/configuration/configuring
- Tool groups (Shell) — https://bob.ibm.com/docs/shell/core-concepts/tools : groups `read`, `edit`, `execute`, `mcp`, `skill`, `todo`, `subagent`, `mode`. `subagent` group is enabled in Agent mode only (defaults table).

### Custom modes (how we get "distinct roles") — https://bob.ibm.com/docs/shell/configuration/custom-modes-bobshell
YAML (preferred) or JSON; global `~/.bob/custom_modes.yaml` or project `.bob/custom_modes.yaml`. Verified example (from docs):

```yaml
customModes:
  - slug: shell-debug
    name: 🐛 Shell Debugger
    roleDefinition: >-
      You are a debugging specialist focused on command-line troubleshooting.
    whenToUse: Use for debugging shell scripts, command failures, and environment issues.
    customInstructions: |-
      When debugging:
      - Always check environment variables first
    groups:
      - read
      - command
```

Properties: `slug`, `name`, `description`, `roleDefinition`, `groups` (allowed toolsets; `edit` can carry `fileRegex` restriction), `whenToUse`, `customInstructions`. Tool groups in modes: `read`, `edit`, `browser`, `command`, `mcp`. Directory-scoped rules: `.bob/rules-{mode-slug}/01-*.md`. Launch in a mode: `bob --chat-mode=shell-debug` or `bob --chat-mode=test-runner -p "Run the test suite and report failures"` (both verbatim from docs). Per-command allowlist in settings JSON: `"tools": {"allowed": ["run_shell_command(git status)", ...]}`.

Caveat for our "3–4 parallel subagents with distinct roles": distinct roles are best implemented as custom modes invoked in parallel `bob run` processes (each with its own mode + clean context), or as parallel subagents spawned within one Agent-mode session (roles only explore/general). True per-subagent role definitions are NOT documented.

## 3. Bob Shell: CLI syntax, custom commands, CI

### Install / auth — https://bob.ibm.com/docs/shell/getting-started/install-and-setup
- OS: macOS, Linux, Windows, z/OS USS, Linux on Z. **Node.js >= 24 required** (docs) — note: community container guide used Node 22.15+ for Shell 1.x-era (https://community.ibm.com/community/user/blogs/krishna-shasank-devaguptapu/2026/04/20/containerizing-ibm-bob); trust official docs (24+) for 2.0.x.
- "Bob Shell 2.0.0 requires a fresh install. Currently there is no automated upgrade path from 1.0.x."
- Login entry point `bob.ibm.com/login`; SSO/IBMid via browser for interactive; **API key for non-interactive**: create key with Scope=Inference in the Bob web portal, then `export BOB_API_KEY=<key>` and run `bob run "..."` or `bob chat`. "If your API key is of type general (rather than Inference), you must also pass `--team-id <team-id>`." (verbatim).
- Install from release tgz (community-verified URL pattern): `https://s3.us-south.cloud-object-storage.appdomain.cloud/bob-shell/bobshell-<version>.tgz` via `npm install -g` — https://community.ibm.com/community/user/blogs/krishna-shasank-devaguptapu/2026/04/20/containerizing-ibm-bob

### Non-interactive invocation (VERIFIED SYNTAX) — https://bob.ibm.com/docs/shell/getting-started/start-bobshell-non-interactive
```
bob run [options] [prompt...]
echo "Explain this project" | bob run
cat buildError.txt | bob run "Explain this build error"
bob run "Review @bigFile.java" > review.md
bob run --max-cost 0.50 --max-turns 10 "Refactor @app.js"
bob run --resume <task-id> "Continue from where we left off"
bob run --resume latest "Keep going"
bob --list-tasks [n|all]        # NDJSON when stdout is not a TTY
```
Full option table (verbatim from docs): `--format <pretty|json|stream-json>`, `--mode <agent|plan|ask>`, `--max-cost <bobcoins>`, `--max-turns <n>`, `--disable-mcp`, `--disable-subagents`, `--disable-tool-groups <groups>` (e.g. `execute,mcp`), `--workspace <path>`, `--log-level <error|warn|info|debug|trace>`, `--resume <task-id>|latest`, `--team-id <id>` (required for general-type API keys), `--trust`, `--accept-license`. General utility: `bob --list-tasks`, `bob --limit <n>`, `bob --show-license`.

- **Machine-readable output:** `--format json` emits `{type:"result", timestamp, status, stats{task_id,total_tokens,input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,cache_ratio,duration_ms,session_costs,tool_calls}, last_message}`. `--format stream-json` emits NDJSON events: `message`, `tool_use` (tool_name/tool_id/parameters), `tool_result`, `error`, `result`. Pipeline example from docs: `bob run --format stream-json "Audit @src/" | grep '"type":"result"' | jq '.last_message'`.
- **All tools pre-approved in `bob run`:** "When running non-interactively with `bob run`, all tools are pre-approved. You are not prompted to approve tool calls during execution." (This is our CI story.)
- `@file` references pull project files into the prompt (e.g. `"Summarize the functionality in @src/main.js"`).
- Community container pattern (spawn Bob from a service): `spawn("bob", ["--accept-license", "-p", prompt, "--yolo"], {env: {...process.env, BOB_API_KEY}})`. `-p` is also shown in official custom-modes docs (`bob --chat-mode=test-runner -p "Run tests"`); `--yolo` appears ONLY in the community post — treat as unverified. — https://community.ibm.com/community/user/blogs/krishna-shasank-devaguptapu/2026/04/20/containerizing-ibm-bob

### Custom commands: slash commands (VERIFIED FORMAT) — https://bob.ibm.com/docs/shell/features/slash-commands
- Custom commands = **markdown files** in `.bob/commands/` (project) or `~/.bob/commands/` (global). "The filename becomes the command name": `.bob/commands/review.md → /review`.
- Frontmatter + positional args, verbatim from docs:

```markdown
---
description: Create a new API endpoint
argument-hint: <endpoint-name> <http-method>
---
Create a new API endpoint called $1 that handles $2 requests.
Include proper error handling and documentation.
```

- NOTE: slash commands are chat-UI constructs (typed in `bob chat` / IDE). They are NOT subcommands of the `bob` binary — there is **no documented way to make `bob postmortem` a native CLI subcommand**. Closest CI equivalent: `bob run` with a saved prompt/skill, or a thin wrapper script named `postmortem` in our repo that calls `bob run`.
- Built-in slash commands include `/compact`, `/mode`, `/permissions`, `/resume`, `/skills`, `/init`, `/status`, `/team`, `/manage-secrets set KEY VALUE` (secrets stored encrypted in `~/.bob/settings/`, referenced as `${KEY}` in MCP configs).

### Skills (VERIFIED FORMAT) — https://bob.ibm.com/docs/ide/features/skills
- Folder per skill in `.bob/skills/` or `~/.bob/skills/` with `SKILL.md`:

```markdown
---
name: code-review
description: Review code for bugs, security issues, and best practices
---
<instructions…>
```

- Supporting files (templates, checklists, scripts) live next to SKILL.md. "skills without descriptions are ignored". Skills load once per conversation; auto-activation is description-driven; approval per skill unless Settings → Auto-Approve → Skills is on. Skills tab exists in Bob Settings (V2).
- developer.ibm.com deep-dive article on building reusable Bob skills: https://developer.ibm.com/articles/build-reusable-agent-skills-with-bob/ (search snippet; article on skill design + Python tool integration + Granite evaluation).

### Settings & context files — https://bob.ibm.com/docs/shell/configuration/configuring
- `~/.bob/settings/settings.json` (user) / `<workspace>/.bob/` (project). Keys: `session.maxTurns` (default 50), `session.defaultMode` ("agent"), `session.mcp` (true), `session.subagents` (true), `logging.logLevel`, `tasks.retentionDays` (30), `telemetry.*`.
- Auth tokens: `~/.bob/settings/auth-secrets.json`. Logs: `~/.bob/logs/shell/`.
- Context files: **AGENTS.md** hierarchical (`~/.bob/AGENTS.md`, project root + parents, subdirs). `/init` in a workspace generates the project context file (AGENTS.md) — per hackathon team repo session logs (https://github.com/arcxteam/IBM-Bob-Code/blob/main/bob_sessions/README.md).
- Env var for logs: `BOB_LOG_LEVEL=debug`.

### GitHub Actions
- **No official `bob` GitHub Action found** (searches 2026-09-15 returned nothing on marketplaces or docs). CI integration is: container image or setup-node + npm install of the Shell tgz, then `bob run --format json` with `BOB_API_KEY` secret. Community-proven Dockerfile pattern (multi-stage, install as root, run as non-root, `bob --accept-license`): https://community.ibm.com/community/user/blogs/krishna-shasank-devaguptapu/2026/04/20/containerizing-ibm-bob

## 4. Programmatic access: API/SDK?

- **No public REST API, no Python/Node SDK for driving Bob is documented.** bob.ibm.com/docs exposes none; searching "IBM Bob REST API SDK" finds only unrelated products (HiBob HR at apidocs.hibob.com, developer.api.bob.io — NOT IBM; do not use).
- Supported programmatic surface = **the `bob` CLI as a subprocess**: `bob run --format json|stream-json` with NDJSON events (`message`, `tool_use`, `tool_result`, `error`, `result`) — effectively a machine-readable streaming protocol. — https://bob.ibm.com/docs/shell/getting-started/start-bobshell-non-interactive
- **API keys** (official): two types — **General** ("Scoped to your subscription instance and usable across multiple services. For inference requests, you must also include the team ID header") and **Inference** ("limited to inference requests only. No additional instance or team headers are required"). Created in the Bob web portal (API key management section); value shown once. Scoped to user + subscription instance; admins can list/revoke instance-wide. — https://bob.ibm.com/docs/shell/account/api-keys
  - "inference requests" language implies an HTTP inference endpoint exists behind the clients, but **no endpoint URL/base URL is published**. Unknown until we inspect traffic or ask at the hackathon.
- **MCP is the sanctioned extension surface** (VERIFIED config) — https://bob.ibm.com/docs/ide/configuration/mcp/mcp-in-bob : `.bob/mcp.json` (project) or `~/.bob/mcp.json` (global), `mcpServers` object; STDIO (`command`, `args`, `cwd`, `env`, `alwaysAllow`, `disabled`) and Streamable HTTP (`url`, `headers`, `alwaysAllow`), legacy SSE. Bob can even author MCP servers for you. Our orchestrator/tools can be exposed TO Bob this way (Bob calls our MCP tools via `use_mcp_tool`).
- Quota/rate: metered in Bobcoins (§7); `--max-cost` caps a run; no documented requests-per-second limit.

## 5. Document understanding & full-repo context

- **Formats ingested natively:** "V2 reads `.docx`, `.pdf`, and `.xlsx` files natively: drop one into the conversation and Bob works from it directly." — https://bob.ibm.com/blog/bob-v2-release-announcement/ ; echoed in IDE best practices: "Attach .docx, .pdf, and .xlsx files directly as context without manually extracting their content." plus "Use @problems to include Bob Findings panel diagnostics", "Use @terminal to include recent terminal output" — https://bob.ibm.com/docs/ide/getting-started/best-practices (search snippet).
- **File size limits for attachments: NOT FOUND in docs read so far.**
- **GitHub issues / advisories:** no built-in GitHub issue ingestion documented. Bob works on "full repository context" (lablab recap: "It operates with full repository context" — search snippet of the May hackathon recap PDF). Practical route for issue threads: `gh issue view N` piped into `bob run` (docs pattern `cat file | bob run "..."`), or an MCP server wrapping the GitHub API. Bob can run git/GitHub CLI via `execute_command` (Agent mode) — "Create a commit and pull request with Bob" tutorial: https://bob.ibm.com/docs/ide/tutorials/create-commit-and-pr (search snippet).
- **Private repos:** nothing documented about Bob-hosted repo connectors; workspace = local folder (`--workspace <path>`). Feed a private repo by cloning in CI (with `GITHUB_TOKEN`) and running `bob run` inside the clone. No docs found on IBM-side code storage beyond FAQ privacy language (https://bob.ibm.com/docs/ide/faq — snippet only).
- **Context window:** 270k tokens (V2), compaction (`/compact`) condenses older context (https://bob.ibm.com/blog/bob-v2-release-announcement/). Third-party cost guide claims condensing starts at ~140k (unverified — the-main-thread.com snippet).
- **AGENTS.md** is the repo-level instruction file (see §3 settings).

## 6. Session summaries / task session reports (hackathon evidence)

- Export procedure (VERIFIED, from hackathon team repo quoting the official guide flow) — https://github.com/arcxteam/IBM-Bob-Code/blob/main/bob_sessions/README.md :
  1. Bob IDE chat → "Views and More Actions" (`...`) → **History**.
  2. Select workspace (current or All), click a task.
  3. Click the task header → **task session consumption summary** appears (shows Context Length, Task ID, Tokens, API Cost) → **screenshot this**.
  4. Click the **Export task history** icon (download arrow) → saves `.md` file.
- Submission convention: `bob_sessions/` folder in repo root with `session-XXX/<screenshot.png + task-history.md>`. Confirmed as "mandatory submission deliverable… judges evaluate teams based on these exports — not on runtime behaviour" (vaatus/sentinel bob_sessions README, search snippet; arcxteam README above).
- In-product artifacts we can also screenshot: subagent aggregate panel (completed/total, tools, tokens, cost, elapsed — https://bob.ibm.com/docs/ide/features/subagents); background-task panel; the V2 "self-contained HTML summary" Bob can generate at the end of an analysis task (https://bob.ibm.com/blog/bob-v2-release-announcement/) — that HTML summary is itself a great postmortem deliverable.
- Shell-side equivalents: `bob --list-tasks` (NDJSON with id/title/status/workspace/updatedAt), `bob run --format json` result stats (task_id, tokens, session_costs, duration_ms, tool_calls) — https://bob.ibm.com/docs/shell/getting-started/start-bobshell-non-interactive.

## 7. Bobcoins

- Definition: "Bobcoins are the consumption-based billing metric used for Bob plans… Each action you complete with Bob… consumes a number of Bobcoins based on the computational resources required." — https://bob.ibm.com/docs/ide/account/bobcoins
- Plans (same page, verbatim table): Free trial **50**, Pro **50**, Pro+ **180**, Ultra **1000** per month; enterprise packs 1000 Bobcoins for $500 (expire 1 year). (Download page: "Try IBM Bob free for 30 days with 50 Bobcoins".) The Register pegged 1 Bobcoin ≈ $0.50 (snippet).
- Bobcoins vs tokens: tokens are raw model usage; "Bobcoins: IBM's billing metric that abstracts token usage into a predictable cost structure."
- Monitoring: gauge in top-right of Bob panel, Settings → General, **Bobalytics** (https://bob.ibm.com/docs/ide/features/bobalytics).
- **Cost of a typical multi-agent session: NOT DOCUMENTED anywhere I could verify.** Community discussion "Free trial = 20.00 Bobcoins?" suggests intensive trial days hit ~20 Bobcoins (community.ibm.com, snippet). One internal-usage blog advises "Cut Bobcoin spend per feature by routing exploration to subagents" (community.ibm.com blog by Narendra Murthy, snippet). Budget guardrails for us: `--max-cost` per `bob run`, `--max-turns`, `session.maxTurns` setting, `--disable-mcp` to trim system prompt.
- Hackathon allotment mechanics: the May 2026 hackathon guide PDF (https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/Lablab-IBM-Bob-hackathon-guide-May-2026.pdf) covers "how to access IBM Bob for the purposes of this hackathon" — PDF is binary to our fetcher; **content unread**. Sep-2026 (2.0) guide not found yet — expect it linked from the lablab event page at kickoff.

## 8. IBM-published hackathon material

- **This hackathon (Bob 2.0):** https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon — "The official IBM Bob 2.0 hackathon… Build: 48 hours… September 25–27, 2026… Prize pool: $10,000… Register before the Kick-Off Stream". IBM Developer event page: https://developer.ibm.com/events/ibm-bob-20-hackathon/ (dated 25 Sep 2026 11:00 GMT-4; page is JS-rendered, little static content). **No starter kit/repo for the Sep 2.0 edition found yet.**
- **Prior edition (May 2026)** — best current proxy for rules/format:
  - Official guide PDF (unreadable binary to us, but the canonical doc): https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/Lablab-IBM-Bob-hackathon-guide-May-2026.pdf (mirror in https://github.com/MISZURIE/devflow-ai/blob/main/Lablab-IBM-Bob-hackathon-guide-May-2026.pdf)
  - Recap page with rules + winners: https://lablab.ai/ai-hackathons/ibm-bob-hackathon
  - Dev Day + hackathon (Apr 30–May 3): https://developer.ibm.com/events/ibm-bob-dev-day-hackathon/
- **Ongoing IBM resources:** developer.ibm.com/components/ibm-bob (tutorials list incl. watsonx Orchestrate agent building, ACE integration, monolith modernization with "reusable AI skills"); skills article https://developer.ibm.com/articles/build-reusable-agent-skills-with-bob/; IBM/bob-demo (bite-sized demos) https://github.com/IBM/bob-demo; docs "Quickstart" https://bob.ibm.com/docs/ide/getting-started/quickstart; community blogs (containerizing Bob; Bob Shell on IBM Z, 2026-09-02, by Gregory Cernera).
- Prior-edition example submissions worth mining for judging format: arcxteam/IBM-Bob-Code, vaatus/sentinel, HEETMEHTA18/bob-ai-hackathon-bottleneck (all github.com, snippets).

---

## Integration plan for our repo

Mapping findings → Incident Postmortem Generator components.

### A. Subagent role definitions (custom modes)
Use `.bob/custom_modes.yaml` (project) defining 3–4 postmortem roles, each a first-class Bob mode with its own roleDefinition/tool groups:
- `postmortem-timeline` (groups: read, command — reconstructs events from issue thread, commits, logs)
- `postmortem-rootcause` (groups: read — code-level causal analysis around fix-sha diff)
- `postmortem-impact` (groups: read, command — blast radius: files touched, dependents, advisories)
- `postmortem-writer` (groups: read, edit — drafts the postmortem doc from the others' summaries)
Launch roles in parallel from the orchestrator as separate `bob run --chat-mode=<slug> --format json` processes (each gets clean context; avoids the explore/general-only limitation of native subagents). Native subagents (`explore`) remain a fallback within a single session. Source for format/flags: custom-modes + non-interactive docs (§2, §3).

### B. Orchestrator API client
There is no REST SDK — the client is a subprocess wrapper around `bob run`:
- `BobRunner` class: spawn `bob run --mode agent --format stream-json --max-cost <n> --max-turns <n> --accept-license --workspace <repo-path> "<role prompt>"`, env `BOB_API_KEY`; parse NDJSON `message|tool_use|tool_result|error|result` events; collect `stats.session_costs` and `stats.task_id` per role.
- Feed inputs: `gh issue view <N> --json ... | bob run "..."` or write thread to a temp .md/.pdf and attach; reference repo files with `@path`.
- Optional reverse integration: expose our report-store/query tools to Bob as an MCP server (`.bob/mcp.json`, streamable-http with `Authorization` header) so interactive Bob sessions can pull postmortem context.

### C. Custom shell command
Closest supported mechanism = custom slash command + repo wrapper:
- `.bob/commands/postmortem.md` with frontmatter `argument-hint: --repo <owner/repo> --issue <n> --fix-sha <sha>` and `$1 $2 $3` substitution → usable as `/postmortem` inside `bob chat` (interactive demo).
- A committed `bin/bob-postmortem` bash script implementing the exact UX `bob postmortem --repo X --issue N --fix-sha ABC` by parsing flags and invoking `bob run` — gives judges the requested syntax while using only documented CLI. (Native `bob <subcommand>` extension is NOT documented; do not promise it.)
- Pair with `.bob/skills/postmortem/SKILL.md` (+ supporting template files) so Bob auto-loads the workflow in Agent mode; enable auto-approve for Skills for demos.

### D. GitHub Action YAML (`.github/workflows/postmortem.yml`)
No official action exists; build on the containerized-Bob pattern:
1. Job: checkout (private repos fine), setup Node 24, `npm i -g <bobshell tgz from releases>` (or prebuilt docker image per community Dockerfile), `bob --accept-license`.
2. Run: `bob run --chat-mode postmortem-writer --format json --max-cost 5 --accept-license --workspace "$GITHUB_WORKSPACE" "Generate postmortem for issue ${ISSUE} fixed in ${SHA}" > result.json` with `env: BOB_API_KEY: ${{ secrets.BOB_API_KEY }}`.
3. Post: `jq -r .last_message result.json > postmortem-<sha>.md`; upload artifact / commit to `postmortems/` / comment on the issue.
4. Trigger: `workflow_dispatch` with `repo`, `issue`, `fix_sha` inputs (matches the required CLI surface), plus optional `issues: [closed]`.
5. Evidence: keep `bob run --format json` outputs in `bob_sessions/ci/` alongside IDE exports.

### E. Deliverables for judging
`bob_sessions/` per role-run: consumption-summary screenshots + exported task-history .md from every session (IDE export steps §6), plus the generated HTML summary Bob can emit — demonstrating Agent mode, parallel subagents panel, document understanding, and CI runs.

## Unknowns / not yet documented — smoke-test Friday 25-Sep

1. **Access & allotment**: how hackathon participants get Bob 2.0 accounts/Bobcoins (guide PDF unread; Sep guide not yet linked). Verify at kickoff stream; check lablab event "Tools/Resources" tab.
2. **API key availability on trial**: docs say keys are available "for trial and paid plan users" — confirm we can mint an Inference key day 1 for CI.
3. **`bob` CLI availability**: confirm Node 24 vs 22 requirement for Shell 2.0.x, exact install URL for the current tgz (releases page), and that `bob run` works in the hackathon's provided environment/container.
4. **Unverified flags**: `--yolo` (community only) and `-p` short form (appears in official custom-modes examples — confirm equivalence to `bob run` in `bob --help`).
5. **Subagent control**: can a prompt reliably force 3–4 parallel subagents in one Agent-mode session, and can each be given distinct instructions (only explore/general types exist)? Fallback = parallel `bob run` processes (planned).
6. **Attachment size limits** for .pdf/.docx/.xlsx; whether Shell can attach files or IDE only.
7. **Inference endpoint**: whether a documented HTTP inference API exists behind the API key (would simplify the orchestrator vs subprocess). Inspect `BOB_LOG_LEVEL=debug` traffic or ask IBM mentors.
8. **`--max-cost` semantics**: flag help says "Maximum spend in Bobcoins" but docs example shows `--max-cost 0.50` (dollars or Bobcoins?) — check `bob run --help`.
9. **Workflows authoring**: closed at GA ("broader authoring opens up once the API surface settles") — check if hackathon builds get early access; would beat our hand-rolled orchestration.
10. **Session export from Shell**: IDE export steps are known; confirm Shell tasks appear in the same exportable history (they share the task store per `--list-tasks`).

## Sources

Fetched and read in full (via MCP fetch tools):
- https://bob.ibm.com/docs/ide
- https://bob.ibm.com/blog/bob-v2-release-announcement/
- https://bob.ibm.com/docs/ide/features/modes
- https://bob.ibm.com/docs/shell
- https://bob.ibm.com/docs/ide/features/subagents
- https://bob.ibm.com/docs/shell/getting-started/start-bobshell-non-interactive
- https://bob.ibm.com/docs/ide/account/bobcoins
- https://bob.ibm.com/docs/shell/account/api-keys
- https://bob.ibm.com/docs/shell/getting-started/install-and-setup
- https://bob.ibm.com/docs/shell/features/slash-commands
- https://bob.ibm.com/docs/shell/configuration/custom-modes-bobshell
- https://bob.ibm.com/docs/ide/features/skills
- https://bob.ibm.com/docs/shell/configuration/configuring
- https://bob.ibm.com/docs/ide/configuration/mcp/mcp-in-bob
- https://bob.ibm.com/docs/shell/core-concepts/tools
- https://heidloff.net/article/workflows-sub-agents-ibm-bob/
- https://community.ibm.com/community/user/blogs/krishna-shasank-devaguptapu/2026/04/20/containerizing-ibm-bob
- https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon
- https://developer.ibm.com/events/ibm-bob-20-hackathon/
- https://developer.ibm.com/components/ibm-bob/
- https://github.com/IBM/ibm-bob
- https://github.com/arcxteam/IBM-Bob-Code/blob/main/bob_sessions/README.md
- https://watsonx-hackathons-2026.s3.us.cloud-object-storage.appdomain.cloud/Lablab-IBM-Bob-hackathon-guide-May-2026.pdf (binary PDF; not text-extractable with our tools)

Cited from search-result snippets only (verify before relying on):
- https://www.itjungle.com/2026/07/13/big-blue-ships-bob-2-0-and-premium-package-for-ibm-i/
- https://www.theregister.com/software/2026/04/28/ibms-ai-coding-partner-bob-hits-general-availability/5226774
- https://www.nicklitten.com/ibm-bob-pricing-explained-free-trial-bobcoins-and-pro-plans-on-ibm-i/
- https://community.ibm.com/community/user/discussion/free-trial-2000-bobcoins
- https://developer.ibm.com/articles/build-reusable-agent-skills-with-bob/
- https://developer.ibm.com/tutorials/accelerate-integration-development-app-connect-ibm-bob/
- https://bob.ibm.com/docs/ide/getting-started/best-practices
- https://bob.ibm.com/docs/ide/tutorials/create-commit-and-pr
- https://ibm.github.io/bob-l3/ , https://ibm.github.io/bob-l3/tailor/3-3/ , https://ibm.github.io/bob-l3/scale/4-2/
- https://github.com/IBM/bob-demo ; https://github.com/vaatus/sentinel/blob/main/bob_sessions/README.md ; https://github.com/HEETMEHTA18/bob-ai-hackathon-bottleneck/blob/main/docs/BOB_WORKFLOW.md ; https://github.com/MISZURIE/devflow-ai/blob/main/Lablab-IBM-Bob-hackathon-guide-May-2026.pdf
- https://lablab.ai/ai-hackathons/ibm-bob-hackathon (recap)
- https://community.ibm.com/community/user/blogs/gregory-cernera/2026/09/02/introducing-bob-shell-on-ibm-z
- https://www.the-main-thread.com/p/ibm-bob-cost-guide
