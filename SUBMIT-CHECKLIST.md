# SUBMIT-CHECKLIST — IBM Bob 2.0 hackathon (CANÓNICO, mantener vivo)

> Generado 2026-09-26 ~23:55 (Lima) por Claude · Verificación contra disco real + /live fresca.
> **Deadline interno: dom 27-sep 13:00 UTC (08:00 Lima). Cliff real 15:00 UTC. Nunca después.**
> Fuente de campos: `docs/research/hackathon-status-2026-09-15.md` §4 + §6 (confirmados) y
> runbook `docs/SPRINT-RUNBOOK.md` §8 (el original manda si hay conflicto).

## 0. Snapshot /live (extraída OK 26-sep ~23:45 Lima — esta vez SÍ se dejó parsear)

- Estado: **"Live · Submissions open"**. Submissions: **196** (+164 hoy) · Drafts: 178 ·
  Participantes 15,727 · Equipos 3,370.
- **Prize pool mostrado: $12,000** (la research del 15-sep decía $10,000 y el video promocional
  dice $10k — la cifra de la página al momento del submit es la que vale; no afecta campos).
- **No existe campo "Main tracks" fijo**: el form pide **"Technology & Category Tags"** (tags
  libres). La /live muestra una nube de tecnologías en uso (IBM 223, ChatGPT 64, watsonx
  Assistant 53, Claude Code 52, Anthropic Claude 49, …) — ver §5 Technologies.
- **Criterios de jueces (publicados, research §4)**: Application of Technology · Presentation ·
  Business Value · Originality. → Los borradores de §3 están alineados a estos 4.
- Intel competitiva (top community vote): #1 "OpsPilot AI – Autonomous SRE Platform" (42 votos,
  espacio adyacente al nuestro), "Overlook: AI said done. See what actually changed.",
  "CodeOns: Automated Codebase Onboarding Agent". **Nuestro diferencial vs OpsPilot**: nosotros
  no automatizamos SRE — reconstruimos el *post-fix loop* con evidencia enlazada y honestidad
  *obligada por el harness*. Ese contraste es el ángulo de Originality.

## 1. Checklist por campo del form

| # | Campo del form | Estado | Evidencia (ruta) | Qué falta | Quién |
|---|---|---|---|---|---|
| 1 | **Project Title** (≤50 chars) | 🔨 borrador listo (§3.1, 3 opciones) | este archivo §3.1 | decisión final (P7/fila 6) | Juan |
| 2 | **Short Description** (≤255 chars) | 🔨 borrador listo (§3.2) | este archivo §3.2 | pegar tal cual (o edit menor) | — |
| 3 | **Long Description** (≥100 words, EN) | 🔨 borrador listo, 335 words (§3.3) | este archivo §3.3 | insertar deltas Bob reales tras F3 (marcado con `<<DELTAS>>`) | Claude (agent runner) |
| 4 | **Technology & Category Tags** | 🔨 propuesta lista (§3.4) | este archivo §3.4 | elegir 5-8 tags en el form | Juan |
| 5 | **Cover Image** (16:9) | ❌ falta — propuesta en §4.3 (NO generar aún) | — | screenshot del viewer UI (recomendada) o metrics card | Juan+Claude (P7) |
| 6 | **Video Presentation** | ✅ listo — 4:27, 48.8 MB (≤300 MB y ≤5 min ✓✓) | `~/projects/postmortem-generator-deliverables/video-v1/postmortem-generator-demo-v1.mp4` + `VIDEO-AUDIT-v1.md` + `captions.srt` | NADA (ship v1 tal cual — decisión tomada, plan fila 6). Sin re-encode: 48.8 MB sobra | — |
| 7 | **Slide Presentation** | ✅ listo — 9 slides, 16:9, 64 KB | `deliverables/deck/postmortem-generator-deck-v1.pdf` (+ `.md` fuente + `scripts/build_deck.py`) | NADA — subir el PDF al form. Métricas reales del run Bob (baseline honesto 0.33 vs 0.22; ver `~/deck-estado-2026-09-27.md`) | hecho por Claude 27-sep |
| 8 | **Demo Application Platform** | 🔨 = GitHub | repo público (§2) | (opcional: GitHub Pages, ver #9) | Juan |
| 9 | **Application URL** | 🔨 = `https://github.com/el-informatico/postmortem-generator` | gh repo view (§2) | OPCIONAL mejorar: publicar `ui/index.html` en GitHub Pages (~10 min, riesgo bajo; hoy NO existe, API pages 404) — decide Juan en P7 | Juan |
| 10 | **"Include code/files where IBM Bob assisted"** | 🔨 apuntadores listos (§3.5): `pmg/bob/`, `.bob/`, `bob_sessions/` | carpetas en repo | que F2-F5 committeen sus capturas | agent runner |
| 11 | **"Screenshots of IBM Bob task session summaries"** | 🔨 parcial — `bob_sessions/` con 3 PNGs hour-0; resto llega tras F2-F5 | `bob_sessions/00-account-setup/*.png` (3) + `session-00-smoke-envelope.json` | ⚠ PNG del summary del SMOKE (dir `session-00-smoke/` está VACÍO — ver §4.2) + PNGs por sesión curl | agente runner (captura IDE) |
| 12 | Repo final: push + CI verde | 🔨 local ahead 2 + bob_sessions untracked | §2 (git status, CI runs) | P8: README métricas honestas (deltas F3) → commit final → **push con YES explícito de Juan** → CI verde | Juan (YES) + Claude |
| 13 | **SUBMIT** en lablab + screenshot confirmación | ❌ pendiente (P9, fila 8; empezar 12:00 UTC máx) | — | ejecutar checklist completo al submit | Juan |

## 2. Verificación REAL de artefactos (26-sep noche — comandos corridos)

### Video v1 — PASA holgado
```
$ ffprobe -v error -show_entries format=duration,size -of default=noprint_wrappers=1 \
    ~/projects/postmortem-generator-deliverables/video-v1/postmortem-generator-demo-v1.mp4
duration=267.200000        # 4:27 ✓ (≤5 min)
size=48835389              # 48.8 MB = 46.5 MiB ✓ (≤300 MB — sobra 6x, NO re-encode)
```
Extras en la misma carpeta: `VIDEO-AUDIT-v1.md` (auditoría completa), `captions.srt`,
2 previews previos (ignorar).

### Repo GitHub (el-informatico/postmortem-generator)
- `gh repo view`: **visibility PUBLIC** ✓ · **license Apache-2.0** ✓ · default branch `main`.
- `pushedAt 2026-09-24T02:36:25Z` (= commit e79d0d2, GAP-1+GAP-4).
- **Local está ahead 2**: `f02f378` (hour-0 evidence) y `4f2d275` (hour-0 gates) NO están en
  GitHub. Además `bob_sessions/*` untracked (sin add aún). → push final es P8, con YES de Juan.
- CI (gh run list): últimos 2 runs **success** sobre main (último 36 s, 24-sep). Sin CI sobre
  los 2 commits locales hasta el push.

### bob_sessions/ — qué hay AHORA
- `00-account-setup/`: 3 PNGs ✓ (bobcoins initial, org dropdown, account email expanded).
- `README.md` (procedimiento + naming `pmg_taskNN_<slug>_summary.png`) — existe, **untracked**.
- `session-00-smoke-envelope.json`: smoke OK — task `f404dad9…`, coste **$0.0217**, "ok" ✓.
- `list-tasks-p0.ndjson`, `session-00-smoke-stderr.log` (0 bytes).
- ⚠ `session-00-smoke/` existe pero **VACÍO** — el envelope JSON prueba que el smoke corrió,
  pero falta el PNG del consumption summary del smoke (la regla exige captura por sesión).
  → playbook 7 del runbook: capturar del IDE History (task f404dad9) o 1 sesión ask barata;
  si es irrecuperable, documentar el gap en el README de bob_sessions. **Nunca fabricar.**
- Resto (sesiones curl/log4j/gitlab) llega tras F2-F5 del agente runner — no tocar.

### README / deck / cover
- `README.md` existe (10,988 B, 22-sep) con arquitectura + tabla métricas baseline. Falta la
  pasada P8: añadir columna/fila de **deltas Bob reales** (llegan de F3) manteniendo honestidad.
- Slide deck: ✅ creado 27-sep — `deliverables/deck/postmortem-generator-deck-v1.pdf`
  (9 slides, 16:9, 960×540 pt, 65,673 bytes, verificado con pypdf; fuente `.md` + builder
  `scripts/build_deck.py`).
- Cover: no existe. Propuestas en §4.3 (NO generar aún, orden de la misión).

## 3. Borradores de campos (listos para pegar; EN inglés donde el form lo exige)

### 3.1 Title — 3 opciones (≤50 chars, verificado por script)
1. `Honest Postmortems from Repository Evidence` (43) — ángulo Originality/honesty.
2. `Repo-to-Postmortem: every claim linked to evidence` (50, al límite exacto) — ángulo Application of Tech.
3. `Postmortem Generator — built on IBM Bob 2.0` (43) — ángulo event-fit (nombre producto + Bob).

Recomendación: **#1** (diferenciador real y memorable; "Bob" ya saturado en títulos del evento
— ninguno de los 2 análogos ganadores puso Bob en el título). Decisión final en P7: Juan.

### 3.2 Short Description (≤255 chars — 2 variantes validadas)
A (225 chars):
> From the fix commit to a full postmortem: which commit introduced the bug (SZZ-lite), timeline, root cause, prevention — every claim linked to repo evidence, ungroundable sections declared 'No evidence'. Built on IBM Bob 2.0.

B (253 chars):
> Reconstructs an incident postmortem from repository evidence: which commit introduced the bug (SZZ-lite), timeline, root cause, prevention. Every claim links to evidence; what the repo can't ground is honestly marked 'No evidence'. Built on IBM Bob 2.0.

### 3.3 Long Description (335 words ✓ ≥100 — pegar completo)
An incident ends. The fix is merged. And the postmortem — the document where the team actually learns — never gets written, because it costs a senior engineer roughly 90 minutes that nobody has.

The Incident Postmortem Generator closes that post-fix loop starting from the repository, not from the incident stack. Give it a repo, the issue behind a bug, and the SHA of the fix: it reconstructs which commit introduced the bug (SZZ-lite: blame, pickaxe and issue linkage), a milestone timeline, the root cause, and a prevention plan. Every claim links to its evidence (claim_linkage_rate 1.00); every section carries a confidence badge; and what repository data cannot ground — user impact, detection, telemetry — is declared "No evidence" instead of invented. The evaluation harness fails any run that invents it. Honesty is enforced, not promised.

Everything runs on real cases, never synthetic data: curl CVE-2023-38545, log4j CVE-2021-44228, and the GitLab 2017 database outage (an ops incident with no fix commit — the issues-only honesty path). The deterministic floor already finds curl's true introducer as top-1 candidate with timeline precision 1.00. `<<DELTAS: tras F3 insertar 1 frase con los deltas Bob medidos — ej. "Agent-mode sessions lifted action-item overlap from 0.33 to X and line agreement from 0.00 to Y while keeping claim linkage at 1.00".>>`

How IBM Bob 2.0 was used: the analysis layer is orchestrated through Bob Agent mode — parallel role subagents (commit archaeologist, document analyst, code reviewer, SRE synthesizer) with document understanding over real issue threads and advisories — with measured metric deltas over the deterministic baseline, plus a Bob-side slash command (.bob/commands/postmortem.md), custom role modes, and the complete bob_sessions/ evidence trail with per-task session summaries.

Pre-existing work: the deterministic core of this repo — git collector, SZZ-lite introducer search, eval harness, 3-case real corpus, offline UI — was built Sep 15–16 and pushed Sep 17, 2026, before the sprint kickoff (Sep 25; open, dated git history, never re-dated; the hour-0 pre-existence policy decision is documented in docs/SPRINT-RUNBOOK.md §3(e)). Built during the IBM Bob 2.0 window (Sep 25–27): the IBM Bob integration layer — multi-agent postmortem sessions (Agent mode, parallel tasks, subagents, document understanding), measured metric deltas over the deterministic floor, and the bob_sessions/ evidence trail.

### 3.4 Technology & Category Tags (elegir 5–8 en el form)
`IBM` · `IBM Bob` · `Python` · `git` · `GitHub API` · `LLM Agents` · `GitHub Actions` · `SZZ`
(Notas: "IBM" es el tag más usado del evento (223) — incluirlo. No usar "watsonx" — no lo
usamos; los análogos sí lo listan y ahí está bien. SZZ puede que no exista como tag — alta.)

### 3.5 "Include any code or files where IBM Bob 2.0 assisted"
Apuntar (texto corto para el campo):
> Bob-assisted code and evidence: `pmg/bob/` (role orchestrators, SRE template, linkage), `.bob/` (slash command, custom role modes, skill), and `bob_sessions/` (per-task session summaries with costs). Build log: `STATUS.md`.

### 3.6 Additional info (escala futura — EN, campo libre)
> Scale path: the collector and evaluator are deterministic and offline, so the floor runs at zero marginal cost — deployable as a post-merge CI step for any repository (.github/workflows/postmortem.yml ships today; it degrades to deterministic mode when no Bob key is configured). Next: org-wide rollout over an entire incident history, more case types (the GitLab outage already exercises the no-fix-commit path), and benchmark growth — the harness is AI-free and byte-reproducible, so any future model or orchestration change is scored against the same public baseline.

## 4. Cover image — propuesta (NO generada aún, según orden)

1. **Recomendada — shot del viewer UI**: `python3 scripts/build_ui.py` → abrir `ui/index.html`
   → caso curl cargado → screenshot 16:9 del side-by-side (postmortem con badges 🟢/🔴 + chips
   de evidencia vs el humano) o del timeline (fix verde / introducer rojo). Comunica el producto
   en 1 imagen y NADIE más del top-10 muestra algo parecido. Cropear 16:9, opcional tagline
   corta superpuesta ("Every claim linked to evidence").
2. **Alternativa — metrics/badge card**: tabla curl del README estilizada (introducer ✓, linkage
   1.00, honesty ✓) sobre fondo oscuro — más "estática", comunica rigor.
3. **Combinada**: shot UI + franja inferior con 3 métricas clave. Más trabajo, solo si sobra P7.

Fuente de shots existentes reutilizable: `docs/assets/video-dryrun/beat*.png` (beats del video).

## 5. Videos guía — análisis (Tarea B)

Descargados 26-sep ~23:45 a `/tmp/yt/` (mp4 360p + subs EN auto + info.json + 8-9 frames c/u;
`subs-clean.txt` por video). **Limitación anotada**: en este entorno los frames se suben a CDN
sin render visual y no hay CLI de visión/OCR local (sin tesseract/pytesseract/ollama) → el
análisis es de CONTENIDO (subs completos + metadata + descripciones), que es la prioridad del
brief. Frames quedan en disco para revisión humana si hace falta.

| Video | Qué muestra | Aplica a nosotros | Acción sugerida |
|---|---|---|---|
| **Win Big** (IdeaMela, 1:54, promo) | Pitch del evento: Bob 2.0 = "real systems, not just code snippets", full repository context; premios 5k/3k/2k; fechas; solo ok | ✅ directo: el pitch del evento ES nuestra tesis (repo-evidence, no snippets) | Ya cubierto: long desc dice "starting from the repository, not the incident stack". Opcional: eco de la frase "full repository context" en el deck P7 |
| **Setup Ep-02** (Tech Sharmit, 10:19, tutorial 3º) | Instalación IDE/Shell, IBMid, trial 30 días | ⚪ nulo para submission (tutorial de instalación, canal no oficial) | Ninguna. Ya hicimos todo esto en hour-0 con evidencia propia |
| **TriageGate** (TechXchange 2026, 5:25, análogo ganador-style) | Estructura: problema→filosofía ("selective autonomy, restraint is the feature")→demo 4 casos escalando→quién lo usa→por qué diferente→**"How IBM Bob 2 was used" explícito** (builder 24 casos / custom Bug Investigator mode / live headless runtime + Granite tiebreaker)→cierre. Web console con pipeline visible, diff before/after, tests 30→33, humano aprueba fix de payments | ✅✅ casi 1:1 con nuestro diseño (determinista primero, agente solo donde aporta, honestidad estructural) | 1) El long desc YA tiene sección "How IBM Bob 2.0 was used" (imita su patrón: roles + dónde + evidencia). 2) NUESTRO deck debe incluir slide "How Bob was used" (nos falta deck). 3) Nuestro equivalente de "24 documented cases" = bob_sessions/ con costes reales — citarlo con número de sesiones real tras F2-F5 |
| **CodeNova** (TechXchange 2026, 2:17, análogo, solo) | Demo por artefactos (checklist→architecture.md Mermaid→consistency audit "fact-checker, 20 real problems"→onboarding por rol con subagentes paralelos→custom mode global reutilizable)→**"a real constraint, not a scripted demo"** (subagentes chocaron permission limits)→**métricas: 5 sesiones, <4 runs, minutos vs 2-3 h manuales**→cierre "built entirely with IBM Bob 2.0" | ✅✅ valida: solo está OK; nombrar features Bob explícitamente; cuantificar; admitir fricción real | 1) Cuantificar en long desc/desk: nuestro "~90 min humano vs <12 s pipeline" ya está; añadir "N Bob sessions, $X.XX total cost" real tras F5. 2) La fricción honesta nuestra = el smoke $0.0217 + límites reales que registre el runner — un renglón "constraints hit" en el deck suma (patrón ganador). 3) "Reusable custom mode" — nuestro `.bob/` slash command + custom_modes.yaml ES eso; decirlo explícito en deck |

### Veredicto conjunto de videos
**El plan de submission cubre lo que los análogos enfatizan**, con 3 huecos accionables:
1. **Falta el slide deck** (campo requerido) — y los videos muestran que la estructura ganadora
   es: problema → demo/arte factos → "How IBM Bob was used" → métricas cuantificadas → fricción
   honesta → cierre. El deck P7 debe seguir ese esqueleto, no un deck corporativo genérico.
2. **Cuantificar el uso de Bob con números reales** (nº de sesiones, coste $ total, deltas de
   métricas) — ambos análogos cierran con números; nuestro long desc tiene el placeholder
   `<<DELTAS>>` y falta el renglón de coste. Llega tras F3/F5.
3. **Team story corta** — CodeNova abre con "I used IBM Bob 2.2 to fix that"; TriageGate abre
   con el dolor ("developer time quietly leaks"). Nuestro video v1 ya abre con el dolor
   ("the postmortem never gets written") ✓ — mantener ese hook también como primer slide.

Nada de lo visto obliga re-record del video ni cambia el ship-v1-tal-cual.

## 6. Top faltantes + riesgos (al cierre de esta misión)

1. **Slide deck (P7)** — único campo REQUERIDO sin ningún artefacto. Crítico-path mañana.
2. **Cover image** — falta; propuesta lista (§4), ejecutar en P7.
3. **PNG del summary del smoke** — `bob_sessions/session-00-smoke/` vacío (envelope sí).
   Capturar del IDE History (task `f404dad9…`) o playbook 7. — runner/Juan.
4. **Push final** — 2 commits + bob_sessions sin subir; requiere YES explícito de Juan (P8).
5. **README métricas honestas** — pasada P8 con deltas reales de F3.
6. **Deltas + coste Bob** — placeholder `<<DELTAS>>` en long desc; datos tras F3/F5.
7. Riesgo menor: prize pool dice $12k en /live vs $10k en research/videos — sin impacto en
   campos; solo no citar cifras de premio en nada nuestro.
