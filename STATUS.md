# STATUS — pre-sprint build log

Sprint: IBM Bob 2.0 hackathon (lablab.ai), vie 25-sep 15:00 UTC → dom 27-sep 15:00 UTC.
Today (pre-sprint, 2026-09-15): build pieces 1 & 4 complete + skeletons of 2 & 3, all
running offline over a local clone of curl. **Demo/eval siempre sobre el caso real
curl CVE-2023-38545.**

> Nota de riesgo: la política de código pre-existente de la edición de septiembre está
> NO VERIFICADA (referencia de mayo: submission original + tecnología pre-desarrollada
> permitida respetando licencias). Este trabajo pre-sprint se documenta abiertamente
> en este archivo y en el historial de git.

## Bloques de trabajo

### B0 — 2026-09-15 (mañana) · Setup + investigación — COMPLETO
- [x] Clone local de curl en `.repos/curl` (155 MB, offline evidence base).
- [x] Contratos de interfaces (`pmg/contracts.py`, `docs/CONTRACTS.md`) — las 4 piezas
      codifican contra estos tipos; fixtures de test en `tests/fixtures/`.
- [x] `docs/research/hackathon-status-2026-09-15.md` — sin cambios materiales: tracks TBA,
      jueces no publicados (solo 2 nombres NativelyAI), Bobcoins de sept SIN cifra (40 es de
      mayo), política de pre-existencia NO VERIFICADA, fechas confirmadas 25→27-sep 15:00 UTC,
      registrados ~10.700. Submission exige screenshots de task session summaries de Bob.
- [x] `docs/research/ibm-bob-notes.md` — Bob se conduce vía CLI `bob run --format json`
      (no hay REST/SDK público); comandos custom `.bob/commands/*.md`; modos/roles en
      `.bob/custom_modes.yaml`; auth `BOB_API_KEY`; subagentes nativos solo explore/general
      → orquestación por roles = procesos `bob run --chat-mode=<rol>` en paralelo;
      no existe mecanismo de subcomandos nativos → `bob postmortem` será wrapper.
- [x] `data/ground_truth/` (caso curl, cita-fiel, todo verificado contra fuentes):
      introducer `4a4b63daaa01ef59b131d91e8e6e6dfe275c0f08` (2020-02-14, cerró PR #4907 —
      un PR de bagder cerrado SIN merge, el commit entró por push directo), ships en 7.69.0
      (2020-03-04); fix `fb4415d8aee6c1045be932a34fe6107c2f5ed147` (autor **Jay Satiro**,
      committer Daniel Stenberg, 2023-10-11), fix en **8.4.0** (2023-10-11 — ¡no 8.3.0, que
      era la última afectada!); detección: Jay Satiro vía HackerOne #2187833 (2023-09-30,
      bounty $4.660, el mayor de curl hasta la fecha); timeline humano de 8 hitos; 9 action
      items; único null: `severity.cvss` (el advisory no publica CVSS, solo "High"/CWE-122).
      Trampas documentadas en `docs/research/curl-case-notes.md`: el fix NO tiene PR asociado
      (heurísticas basadas en PR fallarían); el commit introductor enlaza un PR no-mergeado.

### B1 — Collector determinista (pieza 1) — COMPLETO
- [x] `pmg/collector`: GitHub API con cache en disco (offline-replayable) + git CLI +
      SZZ-lite (blame @fix~1 + `git log -S` + issue-link; score 0.5/0.3/0.2 documentado).
- [x] Tests offline (16; repos git sintéticos en tmp_path + 1 test de integración real).
- [x] **Resultado real (caso curl): el collector encuentra el introducer `4a4b63daaa`
      como candidato TOP-1** (score 0.7 = szz-blame + issue-link "Closes #4907"; el blame
      quedó empatado 4-way a 1 línea y el issue-link + fecha más temprana desempatan).

### B2 — Harness de evaluación (pieza 4) — COMPLETO
- [x] `pmg/eval`: 10 métricas deterministas (sin IA), reporte byte-idéntico entre runs.
- [x] 48 tests. Fix de integración: `introducer_top1` ahora prefiere el sha que matchea
      un candidato del evidence (el fix-sha citado en el diff no es un claim de introducer).

### B3 — Esqueletos piezas 2-3 — COMPLETO
- [x] `pmg/bob`: 4 roles (arqueólogo/document-analyst/revisor/sintetizador), plantilla SRE
      (CC0) con badges 🟢🟡🔴, linkage validator, `DeterministicOrchestrator` (fallback
      offline) + `BobOrchestrator` (subprocesos `bob run --chat-mode=<rol> --format json`
      paralelos; normalizer descarta impact/detection inventados por el modelo). 44 tests.
- [x] `.bob/`: comando slash `postmortem.md`, `custom_modes.yaml` (4 roles), skill.
- [x] `pmg/shell` CLI (`bob-postmortem postmortem …`, exit codes 0/2/3/4/5),
      `scripts/bob-postmortem.sh` (wrapper `bob postmortem`), GitHub Action
      `.github/workflows/postmortem.yml` (degrada a determinista sin BOB_API_KEY;
      push nunca gasta Bobcoins). 19 tests.

### B4 — Integración + docs — COMPLETO
- [x] Suite completa: **130 tests, 0 fallos** (offline; usa `python3.12`).
- [x] Pipeline completo offline sobre el caso curl real → `eval-output/curl-cve-2023-38545/`
      (evidence.json, postmortem.md con badges, linkage.json, metrics.md, eval_report.json).
- [x] **Tabla de métricas (piso determinista, sin IA)**: introducer_top1 ✓ · introducer_top5 ✓
      · timeline_recall 0.38 · timeline_precision 0.60 · action_item_overlap 0.11 ·
      root_cause_match 0.22 · honesty_check ✓ · claim_linkage_rate 1.00 (15/15) ·
      line_agreement 0.00 · collect 11s + generate <1s (baseline humano ~90 min).
      Lectura: métricas derivables del repo ya al techo SIN IA; las narrativas
      (root cause, action items, line agreement) son el objetivo explícito de las
      sesiones Bob del sprint — esta tabla es el baseline a batir.
- [x] README final (arquitectura + métricas + posicionamiento), LICENSE Apache-2.0,
      `data/ground_truth/NOTES.md` (procedencia/copyright).

## Estado del repo
- [x] Repo público en GitHub (cuenta el-informatico), licencia Apache-2.0, CI en GitHub
      Actions (workflow `postmortem`: smoke determinista en push + run manual con inputs).
- [x] Triple validación pre-commit activa (`scripts/hooks/` — commit-msg + pre-commit +
      guard de contenido sensible; lista de tokens local bajo `.git/`, jamás trackeada).

## Checklist arranque del sprint (vie 25-sep, antes de comprometer horas)
- Re-verificar `docs/research/hackathon-status-2026-09-15.md` (jueces/tracks, 2º challenge,
  reglas, política de pre-existencia).
- Verificar cupo real de Bobcoins de la edición de septiembre (cifra ~40 es de mayo).
- Smoke test de acceso a IBM Bob 2.0 (Agent mode + Bob Shell) apenas abra la ventana.
- NUNCA contactar organizadores.
