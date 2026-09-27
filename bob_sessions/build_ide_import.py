#!/usr/bin/env python3
"""Build an IDE-importable task export (version 1) from the WSL bob.db.

The Bob IDE Tasks panel has an import (arrow-down) action that accepts a
JSON export. The format is defined by bobshell 2.0.5 dist/bob.js
(exportProject / importProject / zod schema `kel`):

    {
      "version": 1,
      "exportedAt": <ms epoch>,
      "workspace": "<informational — import re-files tasks under the
                     workspace (cwd) the IDE passes, not this field>",
      "tasks": [
        {
          "task": {id, parentId, taskType, workspace, title, status,
                   firstMessage, version, gitSha, gitBranch, env, costs,
                   messageQueue, approvalConfig, lastError, isPinned,
                   createdAt, updatedAt},
          "messages": [{id, role, data: {role, content, ...}, createdAt}]
        }
      ]   # >= 1 task; import assigns NEW task ids and status "paused"
    }

This script reads the WSL-side database read-only (~/.bob/db/bob.db), maps
the requested tasks to that schema (mirroring exportProject/rowToTask/
rowToMessage, which drop lockedBy/lockLeaseUntil/timeArchived and
taskId), validates the result, and writes the JSON file.

Usage:
    python3 bob_sessions/build_ide_import.py \
        [--db ~/.bob/db/bob.db] \
        [--ids 2d8266cc,900fb3e2,13e68f09,d32e7061] \
        [--all] \
        [--out bob_sessions/ide-import-tasks.json]

    --ids   comma-separated task-id prefixes (default: the 4 role sessions
            of the curl-cve-2023-38545 Bob pipeline run of 2026-09-27)
    --all   include every task in the DB (overrides --ids)
    --short-titles
            replace the full role-prompt titles (the CLI stores the whole
            prompt as title) with short "<Role> — <id8>" labels; the
            original prompt survives in firstMessage/messages either way
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

# The 4 role sessions run by the pipeline (document-analyst, code-reviewer,
# commit-archaeologist, sre-synthesizer). The two "reply with ok" smokes
# (f404dad9, 6a72dcdd) are excluded by default; add them via --ids/--all.
DEFAULT_ROLE_IDS = "2d8266cc,900fb3e2,13e68f09,d32e7061"

VALID_TASK_STATUS = {
    "active", "running", "compacting", "paused", "completed", "error",
}
VALID_TASK_TYPE = {"normal", "subtask", "subagent"}
VALID_MSG_ROLE = {"user", "assistant", "system", "tool"}

# "You are SRE Synthesizer, a subagent role..." -> "SRE Synthesizer"
_ROLE_TITLE_RE = re.compile(r"^You are ([A-Za-z][A-Za-z ]+?),")

# keys exportProject drops from the rowToTask dict
_TASK_DROPS = ("lockedBy", "lockLeaseUntil", "timeArchived")


def row_to_task(row: sqlite3.Row) -> dict:
    """tasks-table row -> export `task` object (mirrors rowToTask +
    exportProject's field dropping)."""
    t = dict(row)
    out = {
        "id": t["id"],
        "parentId": t["parent_id"],
        "taskType": t["task_type"] or ("subagent" if t["parent_id"] else "normal"),
        "workspace": t["project_id"],
        "title": t["title"] or "",
        "status": t["status"] or "active",
        "firstMessage": t["first_message"],
        "version": t["version"],
        "gitSha": t["git_sha"],
        "gitBranch": t["git_branch"],
        "env": json.loads(t["env"]) if t["env"] else None,
        "costs": json.loads(t["costs"]) if t["costs"] else None,
        "messageQueue": json.loads(t["message_queue"]) if t["message_queue"] else None,
        "approvalConfig": json.loads(t["approval_config"]) if t["approval_config"] else None,
        "lastError": json.loads(t["last_error"]) if t["last_error"] else None,
        "isPinned": bool(t["is_pinned"] or 0),
        "createdAt": t["created_at"],
        "updatedAt": t["updated_at"],
    }
    return {k: v for k, v in out.items() if k not in _TASK_DROPS}


def row_to_message(row: sqlite3.Row) -> dict:
    """messages-table row -> export message (mirrors rowToMessage minus
    taskId; `_meta.spend` is already in reduced {cost, contextTokens}
    form in this DB, so no tae() stripping is needed)."""
    data = json.loads(row["data"])
    return {
        "id": row["id"],
        "role": row["role"],
        "data": data,
        "createdAt": row["created_at"],
    }


def validate(export: dict) -> list[str]:
    """Check the export against the import schema (`kel` in bob.js).
    Returns a list of violations (empty == valid)."""
    errs: list[str] = []

    def _int_ms(v, where):
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0

    if export.get("version") != 1:
        errs.append("version must be 1")
    if not _int_ms(export.get("exportedAt"), "exportedAt"):
        errs.append("exportedAt must be a non-negative int (ms)")
    if not isinstance(export.get("workspace"), str) or not export["workspace"]:
        errs.append("workspace must be a non-empty string")
    tasks = export.get("tasks")
    if not isinstance(tasks, list) or len(tasks) < 1:
        return errs + ["tasks must be an array with >= 1 task"]
    for i, entry in enumerate(tasks):
        w = f"tasks[{i}]"
        t = entry.get("task") or {}
        for req in ("id", "parentId", "taskType", "workspace", "title",
                    "status", "createdAt", "updatedAt"):
            if req not in t:
                errs.append(f"{w}.task missing {req}")
        if t.get("taskType") not in VALID_TASK_TYPE:
            errs.append(f"{w}.task.taskType {t.get('taskType')!r} invalid")
        if t.get("status") not in VALID_TASK_STATUS:
            errs.append(f"{w}.task.status {t.get('status')!r} invalid")
        if not isinstance(t.get("workspace"), str) or not t.get("workspace"):
            errs.append(f"{w}.task.workspace must be non-empty")
        for ts in ("createdAt", "updatedAt"):
            if not _int_ms(t.get(ts), ts):
                errs.append(f"{w}.task.{ts} must be non-negative int ms")
        env = t.get("env")
        if env is not None and not (
            isinstance(env.get("id"), str) and env.get("id")
            and isinstance(env.get("workspace"), str)
        ):
            errs.append(f"{w}.task.env needs id: str + workspace: str")
        costs = t.get("costs")
        if costs is not None and not (
            isinstance(costs.get("cost"), (int, float))
            and isinstance(costs.get("contextTokens"), (int, float))
        ):
            errs.append(f"{w}.task.costs needs cost + contextTokens numbers")
        msgs = entry.get("messages")
        if not isinstance(msgs, list):
            errs.append(f"{w}.messages must be an array")
            continue
        for j, m in enumerate(msgs):
            mw = f"{w}.messages[{j}]"
            if not isinstance(m.get("id"), str) or not m.get("id"):
                errs.append(f"{mw}.id must be non-empty string")
            if m.get("role") not in VALID_MSG_ROLE:
                errs.append(f"{mw}.role {m.get('role')!r} invalid")
            d = m.get("data")
            if not isinstance(d, dict):
                errs.append(f"{mw}.data must be an object")
            elif not isinstance(d.get("content"), str):
                errs.append(f"{mw}.data.content must be a string")
            if not _int_ms(m.get("createdAt"), "createdAt"):
                errs.append(f"{mw}.createdAt must be non-negative int ms")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=str(Path.home() / ".bob/db/bob.db"))
    ap.add_argument("--ids", default=DEFAULT_ROLE_IDS,
                    help="comma-separated task-id prefixes")
    ap.add_argument("--all", action="store_true",
                    help="export every task in the DB")
    ap.add_argument("--short-titles", action="store_true",
                    help="short panel-friendly titles instead of the full "
                         "role prompts")
    ap.add_argument("--out",
                    default="bob_sessions/ide-import-tasks.json")
    args = ap.parse_args()

    db = Path(args.db).expanduser()
    if not db.exists():
        print(f"error: database not found: {db}", file=sys.stderr)
        return 1
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        if args.all:
            rows = con.execute(
                "SELECT * FROM tasks ORDER BY created_at ASC"
            ).fetchall()
        else:
            prefixes = [p.strip() for p in args.ids.split(",") if p.strip()]
            rows = []
            for p in prefixes:
                like = f"{p}%"
                found = con.execute(
                    "SELECT * FROM tasks WHERE id LIKE ? ORDER BY created_at ASC",
                    (like,),
                ).fetchall()
                if not found:
                    print(f"error: no task with id prefix {p!r}", file=sys.stderr)
                    return 1
                rows.extend(found)
        tasks_out = []
        for row in rows:
            msgs = con.execute(
                "SELECT * FROM messages WHERE task_id = ? ORDER BY created_at ASC",
                (row["id"],),
            ).fetchall()
            task = row_to_task(row)
            if args.short_titles:
                m = _ROLE_TITLE_RE.match(task["title"])
                if m:
                    task["title"] = f"{m.group(1).strip()} — {task['id'][:8]}"
            tasks_out.append({
                "task": task,
                "messages": [row_to_message(m) for m in msgs],
            })
    finally:
        con.close()

    export = {
        "version": 1,
        "exportedAt": int(time.time() * 1000),
        # informational: the IDE files imported tasks under ITS current
        # workspace (its cwd), not under this field
        "workspace": rows[0]["project_id"] if rows else "",
        "tasks": tasks_out,
    }
    errs = validate(export)
    if errs:
        for e in errs:
            print(f"schema violation: {e}", file=sys.stderr)
        return 1

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(export, indent=2, ensure_ascii=False) + "\n")
    n_msgs = sum(len(t["messages"]) for t in tasks_out)
    print(f"OK: wrote {out} — {len(tasks_out)} task(s), {n_msgs} message(s); "
          f"workspace (informational) = {export['workspace']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
