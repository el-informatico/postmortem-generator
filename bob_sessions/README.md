# bob_sessions/

**Required deliverable.** This folder holds the IBM Bob IDE task session summary screenshots —
the official evidence of Bob usage for this submission. Per the hackathon rules, every task
related to the submission must have its session consumption summary captured here, in PNG
format, added **as the work happens — not reconstructed at the end**.

## Layout

One folder per session, numbered by pipeline lifecycle
(`01-init-plan` through `14-final-export-audit`):

```
bob_sessions/
  01-init-plan/
    pmg_task01_init-plan_summary.png     <- task session consumption summary (screenshot)
    task-history-01.md                   <- exported task history (Export task history)
  02-environment-bootcheck/
    ...
```

## File naming

PNG: `<team>_task<NN>_<slug>_summary.png` — e.g. `pmg_task01_init-plan_summary.png`
(following the official example pattern `teamalpha_task01_login_flow_summary.png`).
Export: `task-history-<NN>.md`.

## Capture procedure (after every task, before starting the next one)

1. In Bob IDE's chat: `...` (Views and More Actions) → **History**
   (set the workspace selector to "All" if needed).
2. Click the task in the history list — it opens in the chat panel.
3. Click the **task header** → the **task session consumption summary** appears
   (Context Length, Task ID, Tokens, API Cost).
4. Screenshot the full summary panel including the header → save as the PNG above.
5. Same view: **Export task history** (download icon) → saves the `.md`.
6. Both files into this folder, then log cost + remaining balance in the sprint tracker.

## Notes

- Task history is local to the machine and expires after 14 days — exports are taken
  immediately after each session, never deferred.
- Folders exist only for sessions that actually ran; the count in the submission reflects
  the real number (no placeholder folders, no mock data).
- Screenshots must not contain credentials or API keys; trim if any is visible.
