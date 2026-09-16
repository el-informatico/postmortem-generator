#!/usr/bin/env bash
# verify_sprint_ready.sh — fully OFFLINE pre-sprint readiness check.
#
# Run this before the IBM Bob 2.0 hackathon sprint (Fri 2026-09-25 15:00 UTC).
# It exercises everything that must work without a network: the test suite,
# the UI build, the GitHub Action YAML, the full pipeline over the 3 real
# cases (deterministic fallback + warm data/cache + local clones), the
# honesty/linkage invariants on the regenerated output, and repo hygiene.
#
# Severity policy (what blocks readiness vs. what only warns):
#   FAIL — offline capability is broken: tests red, UI build crash, YAML
#          invalid, a case's pipeline fails or misses artifacts, honesty
#          invariant violated (linkage < 1.0 or invented impact/detection),
#          LICENSE missing, or a tracked file that looks like .env/token/secret.
#   WARN — real but non-blocking: dirty git tree, stale ui/index.html, hooks
#          not executable/wired, a missing local repo clone (the affected
#          pipeline check will FAIL on its own if it is actually needed).
#
# Exit code: 0 = READY OFFLINE (warnings allowed), 1 = any FAIL.
# Everything network-shaped is defensively unset (proxies, GITHUB_TOKEN,
# BOB_API_KEY); the pipeline is driven with --offline --mode deterministic,
# so the run cannot spend Bobcoins or touch the network.
#
# Usage:   scripts/verify_sprint_ready.sh        (or: bash scripts/verify_sprint_ready.sh)
# Runtime: ~1 min (test suite ~35s + 3 pipeline runs ~20s + the rest <5s).

set -u

# --- hard offline: drop anything that could route traffic or auth a fetch ---
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY \
      all_proxy ALL_PROXY ftp_proxy FTP_PROXY \
      no_proxy NO_PROXY GITHUB_TOKEN GH_TOKEN BOB_API_KEY || true

PY=python3.12
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TMP="$(mktemp -d)" || { echo "verify: mktemp failed" >&2; exit 1; }
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

T_START=$SECONDS

# ---------------------------------------------------------------------------
# result collection — every check records one row; we never abort early
# ---------------------------------------------------------------------------
declare -a R_STAT=() R_NAME=() R_DETAIL=()
N_PASS=0; N_WARN=0; N_FAIL=0

record() { # record STATUS NAME DETAIL
  R_STAT+=("$1"); R_NAME+=("$2"); R_DETAIL+=("$3")
  case "$1" in
    PASS) N_PASS=$((N_PASS + 1)) ;;
    WARN) N_WARN=$((N_WARN + 1)) ;;
    FAIL) N_FAIL=$((N_FAIL + 1)) ;;
  esac
  printf '  [%s] %s\n        %s\n' "$1" "$2" "$3"
}

section() { printf '\n== %s\n' "$1"; }

# ---------------------------------------------------------------------------
# 1. full test suite
# ---------------------------------------------------------------------------
section "1/6 test suite (python3.12 -m pytest -q)"
if "$PY" -m pytest -q >"$TMP/pytest.log" 2>&1; then
  summary="$(tail -n 1 "$TMP/pytest.log" | tr -d '\r')"
  record PASS "test-suite" "${summary:-all tests green (log: $TMP/pytest.log)}"
else
  tail -n 15 "$TMP/pytest.log" >&2
  summary="$(tail -n 1 "$TMP/pytest.log" | tr -d '\r')"
  record FAIL "test-suite" "pytest FAILED: ${summary:-see stderr above}"
fi

# ---------------------------------------------------------------------------
# 2. UI builds from source and matches the committed ui/index.html
# ---------------------------------------------------------------------------
section "2/6 UI build (scripts/build_ui.py -> byte-compare with ui/index.html)"
UI_TMP="$TMP/index.html"
if "$PY" scripts/build_ui.py --out "$UI_TMP" >"$TMP/build_ui.log" 2>&1; then
  if [ ! -f ui/index.html ]; then
    record WARN "ui-build" "build OK but no committed ui/index.html to compare against"
  elif cmp -s "$UI_TMP" ui/index.html; then
    size="$(wc -c < ui/index.html | tr -d ' ')"
    record PASS "ui-build" "rebuild byte-identical to ui/index.html ($size bytes)"
  else
    record WARN "ui-build" \
      "ui/index.html is STALE: rebuild differs (run: python3.12 scripts/build_ui.py && git add ui/index.html)"
  fi
else
  tail -n 15 "$TMP/build_ui.log" >&2
  record FAIL "ui-build" "build_ui.py crashed — see stderr above"
fi

# ---------------------------------------------------------------------------
# 3. GitHub Action YAML parses and is structurally sound
# ---------------------------------------------------------------------------
section "3/6 CI workflow (.github/workflows/postmortem.yml)"
WF=".github/workflows/postmortem.yml"
if [ ! -f "$WF" ]; then
  record FAIL "ci-yaml" "workflow file missing: $WF"
elif "$PY" -c "import yaml" >/dev/null 2>&1; then
  if "$PY" - "$WF" >"$TMP/yaml.log" 2>&1 <<'PYEOF'; then
import sys, yaml
doc = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
if not isinstance(doc, dict):
    raise SystemExit("top level is not a mapping")
triggers = doc.get("on", doc.get(True))  # PyYAML parses bare `on:` as boolean True
if not triggers:
    raise SystemExit("no `on:` triggers block")
jobs = doc.get("jobs")
if not isinstance(jobs, dict) or not jobs:
    raise SystemExit("no jobs")
steps = ((jobs.get("postmortem") or {}).get("steps"))
if not isinstance(steps, list) or not steps:
    raise SystemExit("job `postmortem` has no steps")
print(f"ok: {len(jobs)} job(s), {len(steps)} steps, triggers: "
      f"{', '.join(map(str, triggers))}")
PYEOF
    record PASS "ci-yaml" "PyYAML parse + structure OK ($(tail -n 1 "$TMP/yaml.log"))"
    else
      record FAIL "ci-yaml" "invalid workflow: $(tail -n 1 "$TMP/yaml.log")"
    fi
else
  # project is stdlib-only, so PyYAML may legitimately be absent — fall back
  if grep -q '^jobs:' "$WF" && grep -q 'runs-on:' "$WF" \
     && grep -q 'uses: actions/' "$WF" && ! grep -qP '\t' "$WF"; then
    record WARN "ci-yaml" "PyYAML not installed — structural grep only (pip install pyyaml for a real parse)"
  else
    record FAIL "ci-yaml" "PyYAML not installed AND structural grep found problems in $WF"
  fi
fi

# ---------------------------------------------------------------------------
# 4. offline pipeline end-to-end on all 3 real cases (temp out dir, never
#    touches eval-output/) + 5. honesty invariant on the regenerated output
# ---------------------------------------------------------------------------
section "4/6 offline pipeline — 3 cases (deterministic, --offline, temp out dir)"
section "5/6 honesty invariant (linkage 1.0 + red impact/detection, 0 claims)"

# case|local-repo|ground-truth  (empty local-repo = issues-only case)
CASES=(
  "curl-cve-2023-38545|.repos/curl|data/ground_truth/ground_truth.json"
  "log4j-cve-2021-44228|.repos/logging-log4j2|data/ground_truth/log4j-cve-2021-44228/ground_truth.json"
  "gitlab-2017-db-outage||data/ground_truth/gitlab-2017-db-outage/ground_truth.json"
)
ARTIFACTS="evidence.json postmortem.json postmortem.md linkage.json metrics.md eval_report.json"

for row in "${CASES[@]}"; do
  IFS='|' read -r case lrepo gt <<<"$row"
  out="$TMP/run-$case"
  cmd=("$PY" -c 'import sys; from pmg.shell.cli import main; sys.exit(main(sys.argv[1:]))'
       postmortem --case "data/cases/$case.json" --mode deterministic --offline
       --ground-truth "$gt" --out "$out")
  [ -n "$lrepo" ] && cmd+=(--local-repo "$lrepo")
  t0=$SECONDS
  if "${cmd[@]}" >"$TMP/pipe-$case.log" 2>&1; then
    missing=""
    for a in $ARTIFACTS; do
      [ -f "$out/$a" ] || missing="$missing $a"
    done
    dur=$((SECONDS - t0))
    if [ -n "$missing" ]; then
      record FAIL "pipeline:$case" "exit 0 in ${dur}s but missing artifacts:$missing"
    else
      record PASS "pipeline:$case" "exit 0 in ${dur}s; all 6 artifacts in temp out dir"
    fi
  else
    rc=$?
    tail -n 6 "$TMP/pipe-$case.log" >&2
    record FAIL "pipeline:$case" "pipeline exited $rc — see stderr above (log: $TMP/pipe-$case.log)"
  fi

  # 5. honesty invariant on THIS run's output (only meaningful if it produced files)
  if [ -f "$out/postmortem.json" ] && [ -f "$out/linkage.json" ]; then
    if "$PY" - "$out" >"$TMP/honesty-$case.log" 2>&1 <<'PYEOF'; then
import json, sys
d = sys.argv[1]
pm = json.load(open(f"{d}/postmortem.json", encoding="utf-8"))
lk = json.load(open(f"{d}/linkage.json", encoding="utf-8"))
bad = []
if abs(float(lk.get("rate", 0)) - 1.0) > 1e-9:
    bad.append(f"claim_linkage_rate {lk.get('rate')} != 1.0")
secs = {s.get("id"): s for s in pm.get("sections", [])}
for sid in ("impact", "detection"):
    s = secs.get(sid) or next(
        (x for x in pm.get("sections", [])
         if sid in str(x.get("id", "")).lower()
         or sid in str(x.get("title", "")).lower()), None)
    if s is None:
        bad.append(f"section '{sid}' missing")
        continue
    if s.get("badge") != "red":
        bad.append(f"'{sid}' badge is {s.get('badge')!r}, expected 'red'")
    if s.get("claims"):
        bad.append(f"'{sid}' invents {len(s['claims'])} claim(s)")
if bad:
    print("; ".join(bad))
    raise SystemExit(1)
print(f"linkage {lk.get('valid_claims')}/{lk.get('total_claims')} = 1.0; "
      f"impact/detection red with 0 claims")
PYEOF
    record PASS "honesty:$case" "$(tail -n 1 "$TMP/honesty-$case.log")"
    else
      record FAIL "honesty:$case" "$(tail -n 1 "$TMP/honesty-$case.log")"
    fi
  fi
done

# ---------------------------------------------------------------------------
# 6. repo hygiene
# ---------------------------------------------------------------------------
section "6/6 repo hygiene"

dirty="$(git status --porcelain 2>/dev/null)"
if [ -z "$dirty" ]; then
  record PASS "git-clean" "working tree clean"
else
  nlines="$(printf '%s\n' "$dirty" | wc -l | tr -d ' ')"
  first="$(printf '%s\n' "$dirty" | head -n 3 | tr '\n' ' ')"
  extra=""
  if [ "$nlines" -eq 1 ] && printf '%s' "$dirty" | grep -q "scripts/verify_sprint_ready.sh"; then
    extra=" (only the verifier itself — commit it after the sprint or ignore)"
  fi
  record WARN "git-clean" "dirty tree, $nlines untracked/modified path(s): $first$extra"
fi

hook_files="scripts/hooks/commit-msg scripts/hooks/pre-commit scripts/guard-sensitive-content.sh"
nox=""
for f in $hook_files; do [ -x "$f" ] || nox="$nox $f"; done
if [ -z "$nox" ]; then
  record PASS "hooks-executable" "commit-msg, pre-commit, guard-sensitive-content.sh all executable"
else
  record WARN "hooks-executable" \
    "not executable:$nox — fix: chmod +x$nox"
fi

hp="$(git config core.hooksPath 2>/dev/null || true)"
if [ "$hp" = "scripts/hooks" ]; then
  record PASS "hooks-wired" "git config core.hooksPath = scripts/hooks (triple validation active)"
else
  record WARN "hooks-wired" \
    "core.hooksPath is '${hp:-unset}' — fix: git config core.hooksPath scripts/hooks"
fi

if [ -f LICENSE ]; then
  record PASS "license" "LICENSE present (Apache-2.0)"
else
  record FAIL "license" "LICENSE missing"
fi

leaks="$(git ls-files | grep -Ei '\.env|token|secret' || true)"
if [ -z "$leaks" ]; then
  record PASS "no-tracked-secrets" "git ls-files has no .env/token/secret-looking paths"
else
  record FAIL "no-tracked-secrets" "tracked suspicious paths: $(printf '%s' "$leaks" | tr '\n' ' ')"
fi

for pair in "repos-curl:.repos/curl" "repos-log4j:.repos/logging-log4j2"; do
  name="${pair%%:*}"; path="${pair#*:}"
  if [ -d "$path/.git" ]; then
    record PASS "$name" "$path present (offline evidence base)"
  else
    record WARN "$name" \
      "$path missing — the pipeline for its case will FAIL offline (fix: git clone <upstream> $path)"
  fi
done

# ---------------------------------------------------------------------------
# 7. summary
# ---------------------------------------------------------------------------
TOTAL=$((N_PASS + N_WARN + N_FAIL))
printf '\n'
printf '=====================================================================\n'
printf 'SUMMARY (%d checks: %d PASS / %d WARN / %d FAIL)\n' \
  "$TOTAL" "$N_PASS" "$N_WARN" "$N_FAIL"
printf -- '---------------------------------------------------------------------\n'
printf '%-4s  %-22s %s\n' "STAT" "CHECK" "DETAIL"
printf -- '---------------------------------------------------------------------\n'
for i in "${!R_NAME[@]}"; do
  printf '%-4s  %-22s %s\n' "${R_STAT[$i]}" "${R_NAME[$i]}" "${R_DETAIL[$i]}"
done
printf '=====================================================================\n'
printf 'offline runtime: ~%ds (tests + 3 pipeline runs, no network)\n\n' "$((SECONDS - T_START))"

if [ "$N_FAIL" -eq 0 ]; then
  printf '>>> READY OFFLINE: 0 FAIL (%d PASS, %d WARN of %d checks — warnings do not block)\n' \
    "$N_PASS" "$N_WARN" "$TOTAL"
else
  printf '>>> NOT READY — %d FAIL:\n' "$N_FAIL"
  for i in "${!R_NAME[@]}"; do
    [ "${R_STAT[$i]}" = "FAIL" ] && printf '    - %s: %s\n' "${R_NAME[$i]}" "${R_DETAIL[$i]}"
  done
fi

cat <<'EOF'

FALTA PARA EL VIERNES (no verificable offline) — manual checklist, sprint
opens Fri 2026-09-25 15:00 UTC (ends Sun 27 15:00 UTC):

  [ ] Re-verificar docs/research/hackathon-status-2026-09-15.md
      (jueces/tracks, 2º challenge, reglas, política de pre-existencia).
  [ ] Verificar cupo real de Bobcoins de la edición de septiembre
      (la cifra ~40 es de la edición de mayo).
  [ ] Smoke test de acceso a IBM Bob 2.0 (Agent mode + Bob Shell)
      apenas abra la ventana del sprint.
  [ ] NUNCA contactar organizadores.

EOF

[ "$N_FAIL" -eq 0 ] && exit 0
exit 1
