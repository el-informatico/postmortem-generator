# Git hooks — triple validation at commit time

This repository enforces three mechanical guards on every `git commit`.
They are tripwires, not containment: `git commit --no-verify` bypasses
them, so the matching behavior rule (below) matters as much as the
hooks themselves.

## The three validations

1. **No AI attribution in commit messages** (`hooks/commit-msg`):
   rejects `Co-Authored-By:` trailers naming an AI vendor
   (an alternation of well-known AI vendor/product names),
   "(generated|written|authored|assisted) with/by <vendor>" phrasing,
   and the robot emoji. These patterns are shape-based: a subject
   *mentioning* a vendor and human `Co-Authored-By:` trailers pass the
   pattern check. (If your local token list also carries vendor names —
   a strict zero-mention policy — the message token check below blocks
   any mention; the list decides.)
2. **No host-internal paths in staged added lines**
   (`guard-sensitive-content.sh`): absolute paths from the author's
   machine (`<home-dir>/<user>`, `<unix-windows-mount>/...`,
   `<drive>:\Users\...` and similar).
3. **No sibling/local-infra project names in staged added lines**
   (same guard): identifiers of other projects that live on the
   author's machine, plus AI-attribution strings in content.

Validations 2 and 3 read a list of literal tokens from
`$(git rev-parse --absolute-git-dir)/sensitive-tokens` — one string per
line, matched case-insensitively as substrings, only in ADDED lines of
the staged diff. That file lives inside `.git/`, so it is per-clone and
**never tracked or pushed**; the tokens themselves are the sensitive
strings and must not appear in the repository. The same list is also
checked against the commit *message* by `hooks/commit-msg`.

## Files

| File | Role |
|---|---|
| `hooks/commit-msg` | validation 1 + sensitive tokens in the message |
| `hooks/pre-commit` | runs the guard below |
| `../guard-sensitive-content.sh` | validations 2 + 3 over staged added lines |

## Install (per clone)

```sh
git config core.hooksPath scripts/hooks
chmod +x scripts/hooks/commit-msg scripts/hooks/pre-commit \
         scripts/guard-sensitive-content.sh
```

Then create the local token list (adjust to your machine — every line
is a literal substring to block):

```sh
cat > "$(git rev-parse --absolute-git-dir)/sensitive-tokens" <<'EOF'
<home-dir>/your-user
your-user
<unix-windows-mount>
<drive>:\users
<sibling-project-name>
<ai-vendor-1>
<ai-vendor-2>
<attribution-footer-phrase>
<robot-emoji>
EOF
```

Seed files with real token lists stay OUTSIDE the repository (or inside
`.git/`); never commit one.

## Bootstrap note (the one `--no-verify` exception)

The commit that introduced these guard scripts themselves was made with
`git commit --no-verify` exactly once: detection patterns necessarily
contain the literal strings they are meant to detect, so the guard
would refuse its own installation. Every later commit must go through
the hooks.

## Exit codes and failure mode

- `0` — clean, or check disabled (token list absent or empty:
  fail-open bootstrap, so a fresh clone without a list still commits).
- `1` — violation: rewrite the flagged content and re-stage.
- `2` — guard-internal failure (no git dir, `mktemp` failure, or a
  token list that exists but is not a readable regular file): the
  commit is REFUSED — fail-closed.

## Behavior rules (the hooks only tripwire these)

- Never use `git commit --no-verify` in this repository (sole
  exception: the hooks' own bootstrap commit, above).
- Never write AI-attribution trailers or attribution footers into
  commits or content in the first place.
- Deliverables that must quote sensitive strings for audit/planning
  belong outside the working tree; in-repo text uses category
  references ("the author's home directory", "a sibling project"), not
  the raw strings.

## Honest limits

`--no-verify` bypasses everything. Binary staged content is not
scanned. Only ADDED lines are checked — a file that already carries a
token under its tracked form is not re-flagged until a staged change
adds a new token-bearing line. The guard never prints matched content,
only file names and counts. The staged-file list is newline-delimited,
so a staged path containing an embedded newline is not scanned.
