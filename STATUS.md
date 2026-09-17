# STATUS — pre-sprint build log

Sprint: IBM Bob 2.0 hackathon (lablab.ai), vie 25-sep 15:00 UTC → dom 27-sep 15:00 UTC.

> **[ ] HUMANO — deadline vie 25-sep 15:00 UTC (kickoff): confirmar registration en lablab**
> (<https://lablab.ai/ai-hackathons/ibm-bob-2-hackathon> debe mostrar "Registered";
> el evento cierra el registro al kickoff — hard gate, 17-sep aún ABIERTO, no verificable
> desde tooling — requiere login humano).
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

## B6 — 2026-09-15 · Refuerzo pre-sprint (corpus + UI + docs)
- [x] **Corpus 3 casos reales**: curl (flagship, introducer top-1 exacto) + **log4j
      CVE-2021-44228** (fix `c77b3cb393` = merge PR #608; introducer VERIFICADO
      `f1a0cac60f` "LOG4J2-313 Add JNDILookup" 2013-07-18 vía `git log --follow
      --diff-filter=A`; el piso SZZ-lite honestamente NO lo encuentra — culpa a refactors
      2017 de JndiManager, ciego documentado del método) + **GitLab 2017** (incidente de
      ops SIN commits de fix: camino issues-only; issue #1684 vive en gitlab.com
      gitlab-com/infrastructure — cache sembrada a mano desde GitLab API v4, documentado).
      Ground truth cita-fiel por caso (`data/ground_truth/<caso>/`), pipelines reales
      corridos offline (`eval-output/`), métricas por caso (honesty ✓ y linkage 1.0 en
      los tres).
- [x] **Soporte issues-only** en contracts/collector/bob/eval (fix_sha opcional, secciones
      resolution/root_cause degradan honestamente, invariant de linkage 1.0 se mantiene).
- [x] **UI delgada** (`scripts/build_ui.py` → `ui/index.html`, single-file offline 616 KB):
      timeline interactiva con deep-links a commits/issues reales, lado-a-lado generado
      vs humano con badges y chips de evidencia, tabla de métricas, switcher de 3 casos.
- [x] **Video script** (`docs/video-script.md`): 4:20, 7 beats, 1.335 días verificados
      commit→fix, checklist de session summaries de Bob, versión one-take de respaldo.
- [x] Suite completa: **155 tests, 0 fallos**. README con corpus + UI. Commits por bloque
      vía hooks. Sin push (publicación = gate aparte del usuario).

## B7 — 2026-09-15 · Métricas narrativas + dry-run video + verificación sprint

- [x] **Métricas narrativas del piso determinista (sin IA, sin tocar el scoring)**:
  `git diff --stat pmg/eval/` VACÍO — cada delta viene de mejor evidencia y mejor
  generación, nunca del cálculo de la métrica (documentado en
  `docs/B7-narrative-improvements.md` con la regresión incluida).
  - Collector: `committer_date` (fix y candidatos), `closed_at`/`merged_at`/
    `is_pull_request` de issues/PRs, y **releases** vía
    `git tag --contains --sort=version:refname` (tags `-rc/-beta/...`
    descartados: un RC no es una release). Fechas normalizadas a UTC
    (`utc_iso`/`utc_date` en contracts) — solo esto corrigió un día de drift
    en el push del introducer de curl (`2020-02-17T00:08+01:00` =
    `2020-02-16T23:08Z`).
  - Orchestrator: timeline narrativo = **hitos** (lifecycle de issue/PR,
    candidato top authored+pushed, releases, fix; push y cierre-de-PR del
    mismo día en UNA línea; comentarios post-resolución fuera del timeline
    — los 156 comentarios post-disclosure de log4j eran ruido); root cause
    cita **las palabras del propio fix** (mensajes del diff con joins de
    strings C, body del commit message con trailers fuera, sitio de copy
    `memcpy`); action items agregan upgrade-a-release-del-fix + aplicar el
    patch + **checklist del tracking issue** (los action items humanos de
    gitlab vivían ahí) — sin inventar los de opinión/bounty.
  - **Deltas medidos (mismo harness, antes→después)**:
    curl: recall 0.375→**0.75** · precision 0.60→**1.00** · actions
    0.111→**0.333** · root_cause 0.220→**0.295** · top1/top5/honesty/linkage
    intactos (21/21 claims). log4j: precision 0.012→**0.50** · actions
    0.00→**0.25** · root_cause 0.086→**0.172** · line_agreement 0.056→0.00
    (regresión documentada: el match viejo era un comentario
    post-disclosure citando la security page — ruido eliminado). gitlab:
    recall 0.091→**0.182** · actions 0.00→**0.786** (checklist del issue) ·
    precision 1.00. Techos restantes son honestos (eventos solo-advisory,
    ciego SZZ de log4j, line_agreement ≈ 0 = objetivo de las sesiones Bob).
  - Suite: **172 tests, 0 fallos** (155 heredados + 17 nuevos: UTC, tags,
    lifecycle, extracción de mensajes/checklist, curación de hitos).
  - `eval-output/` regenerado para los 3 casos + UI rebuild + tabla de
    métricas de README y cifras del video-script actualizadas a los valores
    nuevos (6/8, 0.29, 21/21).
- [x] **Dry-run del video** (`docs/video-dryrun.md` + 9 screenshots reales en
  `docs/assets/video-dryrun/`): la UI se driveó offline con el chromium de la
  cache de playwright vía CDP-pipe (sin instalar nada, sin red). 7 beats con
  timestamps exactos (4:20), selectores reales, cues de narración y checklist
  de grabación. Hallazgos útiles: el sha del introducer no es texto en el tab
  blog (usar Ctrl+F o el tab advisory); "log4j in progress" va como VO+overlay;
  el switcher conserva el scroll. Cifras del guion actualizadas a las nuevas.
- [x] **`scripts/verify_sprint_ready.sh`**: verificación offline completa
  (tests, build de UI byte-identical, YAML de la Action, pipeline+honesty en
  los 3 casos en dirs temporales, higiene de repo/hooks/licencia/secrets) —
  **READY OFFLINE** con 15 PASS/1 WARN esperado (árbol sucio durante el
  trabajo). Lista lo no verificable sin el evento (jueces/tracks, Bobcoins,
  smoke de Bob, no contactar organizadores).

## video-v1 — 2026-09-16 · Demo video 4:27 (entregable fuera del árbol)

- [x] **`postmortem-generator-demo-v1.mp4`** (1920×1080, 30 fps, H.264+AAC,
  4:27, 26 clips xfade 0.4 s, captions SRT quemadas) en
  `~/projects/postmortem-generator-deliverables/video-v1/` — fuera del working
  tree, sin push. Pipeline del skill `demo-video-automation` (probado):
  narration verbatim del guion (26 segmentos) → edge-tts
  `en-US-AndrewNeural` rate +0% (268.5 s; sin `CARTESIA_API_KEY` en env →
  fallback aprobado) → 15 escenas HTML estáticas generadas + 11 clips de la UI
  real (`ui/index.html` offline, chromium en cache vía playwright-core, cursor
  sintético + ripple porque el video de Playwright no renderiza el cursor del
  SO) → ffmpeg: trim 0.12 s de cabeza, xfade+acrossfade encadenados, SRT con
  aserción dura de conteo de palabras (cues == narración), loudnorm −16 LUFS.
- Números en pantalla: solo `eval-output/` y STATUS (1335 días, 6/8, 0.29,
  21/21, score 0.70, µs reales del pill). Cero atribución de IA: Bob solo
  como capa de orquestación; sin paths internos (única ruta visible:
  `.repos/curl` y `eval-output/...`).
- QA determinista (gate): **7/7 PASS** — duración 4:27 (dentro de 3:30–4:30),
  decode completo 0 errores, formato exacto 1920×1080 yuv420p 30 fps,
  blackdetect recalibrado para dark theme (`pixel_black_th=0.004`: solo negro
  puro; el falso positivo del terminal `#0a0d12` quedó documentado), lane
  whitedetect (YAVG>240 = página sin pintar) 0/534 frames, re-conteo de
  palabras del SRT 633==633, audio rms −16.1 dB peak −1.2 dB — reporte en
  `qa/qa-report.md`. QA de color (no-gate): revisión de frames sobre 12
  frames clave + 4 crops de la banda de captions, un criterio por frame,
  schema `{pass, reason}` — `qa/frame-results.json`.
- Decisiones documentadas: sin música (sintética daña más de lo que suma);
  los flashes REQUIRED-EVIDENCE #1/#2 (sesiones Bob) quedan para el sprint
  (`bob_sessions/` no existe pre-evento — no se fabrican screenshots); el
  path del terminal se redactó a `eval-output/curl-cve-2023-38545` (los
  números no se tocaron); take-2 solo en ui-b (el panel de métricas abre al
  final del documento → scroll post-toggle), take-1 conservado en el resto.
- **Fix colisión captions↔escena (post-QA)**: el lane de color detectó que
  los "pills" `.lower` de s04/s05/s09 y la 3ª fila de badges de s08 caían
  dentro de la banda de captions quemadas (y857–959; verificado por
  bounding-box en chromium + row-scan de píxeles). Fix: s04 pill eliminado
  (mensaje verbatim en el VO), s05 bottom 120→270, s08 badges top 640→500,
  s09 pill movido arriba (top:90). Re-grabado el grupo static completo
  (escenas deterministas) + re-ensamblado; en el proceso se encontró y
  parcheó un pie de guerra en `assemble.py` (cache de norm por id
  reutilizaba clips viejos aunque el raw fuera nuevo → ahora compara
  mtimes). Verificación final: row-scan (gap limpio en los 4 frames) y
  revisión de frames 4/4 PASS.

## B8 — 2026-09-16 · Hardening pre-sprint: runbook + presupuesto + re-verificación
- [x] **Re-verificación del status del hackathon** (sección fechada 2026-09-16 en
      `docs/research/hackathon-status-2026-09-15.md`): tracks / jueces / 2º-challenge /
      reglas-pre-existencia / Bobcoins-sep / plazos / premios / equipo **UNCHANGED**
      vs 15-sep (a 9 días del kickoff). Único movimiento: registered builders
      **10.420** / 1.698 equipos (vs ~10.700 / 1.742 — retroceso neto pese a +202/24h
      ⇒ purge/dedup; no afecta el plan). Hallazgos nuevos: la oferta "40 Bobcoins/30
      días" es del programa universitario BeMyApp (**no** del evento); hora del
      workshop 24-sep discrepa entre fuentes (developer.ibm 12:00 ET vs BeMyApp
      11:00–12:30 ET); bucket S3 sin PDF de reglas por 5º día consecutivo (nuevo
      objeto más reciente sigue siendo del 29-ago).
- [x] **`docs/SPRINT-RUNBOOK.md`**: checklist de prerequisitos con slots "verify at",
      gates de hora-0 (a–e, incl. gate de decisión sobre política de pre-existencia
      con pivot documentado — nunca esconder ni redatear trabajo pre-sprint), fases
      P0–P9 con ventanas UTC (deadline interno de sumisión dom 13:00), ledger de
      Bobcoins con disciplina de captura post-sesión (`bob_sessions/session-<NN>-<rol>/`
      = requisito duro de sumisión), 8 kill criteria con hora-límite, 8 playbooks de
      falla (acceso denegado / cuota menor / API changed / output inparseable /
      rate-limit / export faltante / WSL), checklist de sumisión y tabla
      baseline-a-batir. Hechos verificados contra el repo: timeout 900 s, exit codes,
      paths de casos, métricas por caso, `bob --list-tasks`.
- [x] **`docs/BOBCOIN-BUDGET.md`**: prompts de rol **medidos** con `build_role_prompt`
      sobre la evidencia real (curl ~7.4K tok · log4j ~90K · gitlab ~5K; pico ~43K
      tok << contexto 270K de Bob), envelope de 5 clases de sesión, tabla de 22
      sesiones → worst-case **32 + 8 de margen = 40** (mediana esperada ≈ 22), y
      **cut ladder re-derivada** — los umbrales 25/15/8/4 sugeridos por el brief NO
      verifican contra la aritmética; bandas correctas: ≥38 completo / 33–37 sin
      gitlab / 24–32 sin log4j / 19–23 sin demo CI / ≤18 curl a 2 roles, con regla
      comprometido ≤ Q − max(2, 0.15·Q). Calibración hora-1 leyendo
      `stats.session_costs` del envelope JSON.
- [x] **Guardarrailes de gasto en código**: `--bob-max-cost N` en el CLI (se forwarda
      a cada `bob run` como `--max-cost`; el piso determinista no lo consume), input
      `bob_max_cost` (default 1) en `postmortem.yml` para dispatch — el trigger push
      sigue determinista = 0 Bobcoins por construcción — y `PMG_ANALYST_ROLES` (env
      override de `ANALYST_ROLE_IDS`) para ejecutar el rung-4 sin tocar código el
      día del sprint.
- [x] **Dry-run offline completo**: `scripts/verify_sprint_ready.sh` → **READY
      OFFLINE** (16 checks, 15 PASS / 1 WARN esperado por STATUS sucio); suite
      **175 tests, 0 fallos** (172 + 3 nuevos: parse y forward de `--bob-max-cost`,
      override de roles con validación); UI rebuild byte-idéntica; 3 pipelines
      offline exit 0 con 6 artefactos c/u; honestidad curl/log4j/gitlab linkage 1.0
      con impact/detection rojos y 0 claims. Fix de rot: `scripts/bob-postmortem.sh`
      ahora prefiere `python3.12` (el `python3` del PATH es 3.11 de otro venv y
      rompía el fallback fuera del repo root).
- [x] Commits lógicos por bloque (runbook · presupuesto · re-verificación ·
      guardarrailes). Sin push (publicación = gate aparte del usuario).

## Checklist arranque del sprint (vie 25-sep, antes de comprometer horas)
- [x] Re-verificar el status del hackathon — HECHO 2026-09-16 (sección
      "Re-verification 2026-09-16" en `docs/research/hackathon-status-2026-09-15.md`:
      todo UNCHANGED salvo el conteo registrado).
- [ ] Verificar cupo real de Bobcoins de la edición de septiembre en la apertura
      (cifra ~40 es de mayo; decidir por banda según `docs/BOBCOIN-BUDGET.md` §5).
- [ ] Smoke test de acceso a IBM Bob 2.0 (Agent mode + Bob Shell) apenas abra la
      ventana (gates hora-0 y playbooks: `docs/SPRINT-RUNBOOK.md` §3/§7).
- [ ] NUNCA contactar organizadores.
