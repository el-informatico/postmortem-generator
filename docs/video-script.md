# Video script — Incident Postmortem Generator (IBM Bob 2.0 hackathon)

Submission video for lablab.ai. Judging rubric: Application of Technology · Presentation ·
Business Value · Originality. This script is written to hit all four explicitly.

**Hard rules (enforced throughout):**
- Runtime: target 3:30–4:30, **hard ceiling 5:00**. Spoken total below: **4:20** (40 s contingency).
- **Zero AI attribution**: never imply or state that any AI tool wrote this codebase. IBM Bob
  appears only as the *orchestration layer inside the product* — never as author.
- **No internal paths on screen**: record from the repo root, neutral shell prompt, no
  terminal title bar (see equipment checklist).
- **No sibling projects** mentioned anywhere.
- Voiceover: English only, verbatim as written. Spanish appears **only** in EDIT NOTE /
  production annotations.

---

## Runtime budget

| # | Beat | Window | Budget | VO words (~150 wpm) |
|---|------|--------|--------|---------------------|
| 1 | Hook — the unwritten postmortem | 0:00–0:25 | 25 s | ~60 |
| 2 | Positioning — repo-first, not stack-first | 0:25–0:55 | 30 s | ~80 |
| 3 | Architecture — the 4 pieces | 0:55–1:40 | 45 s | ~115 |
| 4 | Demo — real curl CVE-2023-38545 | 1:40–3:10 | 90 s | ~185 |
| 5 | Metrics — scored vs the human postmortem | 3:10–3:40 | 30 s | ~80 |
| 6 | Honest limits | 3:40–4:05 | 25 s | ~65 |
| 7 | Close + CTA | 4:05–4:20 | 15 s | ~30 |
| | **Total** | | **4:20** | **~615** |

If a beat overruns, cut in this order: (a) demo sub-beat 4d click-through extras, never the
money moment; (b) the "unmerged PR" aside in beat 4; (c) one sentence from beat 6. Never cut
the differentiator line (beat 2), the anti-wrapper line (beat 3), or the 1,335-day reveal (beat 4).

## Equipment checklist

- [ ] Screen: 1080p (1920×1080), 30 fps capture, **dark terminal theme**, terminal font ≥ 18 px
      (SHAs and badges must be legible after YouTube compression).
- [ ] Neutral prompt: `export PS1='$ '`; hide terminal title bar or record fullscreen; hide
      clock/battery/notifications (do-not-disturb ON). Nothing on screen may reveal usernames,
      hostnames, or directories outside the repo root.
- [ ] Record from the repo root only — the on-screen command uses the relative path
      `.repos/curl` (that one is fine; it is part of the product's documented CLI).
- [ ] Mic: USB/condenser, quiet room, 10 s room tone + clap for sync; read at ~150 wpm,
      short sentences, no rush on the numbers.
- [ ] Pre-warm before recording: full pipeline already run once (disk cache hot) so the demo
      command completes in seconds on camera; `postmortem.md` pre-opened in an editor;
      browser tab with the UI preloaded; metrics table pre-rendered.
- [ ] OBS (or equivalent) 3 scenes pre-built: terminal · browser UI · overlay card, so cuts
      are keystrokes, not drags.
- [ ] Cursor highlight ON; test that 🟢🟡🔴 emoji render in the terminal/editor theme used.

## REQUIRED-EVIDENCE checklist (lablab: "Be sure to include the screenshots of IBM Bob task
session summaries for your project")

Mandatory submission evidence — plan them into the video, don't bolt them on:

- [ ] During the sprint, for **every** Bob Agent-mode role run (archaeologist, document
      analyst, code reviewer, synthesizer): open History → click the task → click the task
      header → **screenshot the task session consumption summary** (Context Length, Task ID,
      Tokens, API Cost) → also export the task history `.md`. Store under `bob_sessions/`.
- [ ] **Flash #1 — beat 3 (~1:12)**: Bob IDE parallel-subagents grouped panel (completed/total,
      tools, tokens, cost, elapsed). 1.5 s on screen while VO says "role subagents".
      Directly evidences rubric "Application of Technology" (Agent mode, subagents, parallel tasks).
- [ ] **Flash #2 — beat 4 (~1:55)**: one task session consumption summary screenshot while the
      command "runs". 2 s, zoomed so Task ID / Tokens / Cost are readable at 1080p.
- [ ] All session screenshots + exported task histories also go into `bob_sessions/` in the
      repo and one slide of the slide deck (judges evaluate these, not just runtime behavior).
- [ ] Verify legibility of every screenshot at 1080p before export; re-shoot blurry ones.

---

## BEAT 1 · HOOK — the postmortem nobody has time to write · 0:00–0:25 (25 s)

**VOICEOVER (verbatim)**

> An incident ends. The fix is merged. And the postmortem — the document where the team
> actually learns — never gets written. Writing one takes about ninety minutes of a tired
> engineer's time, weeks after the pager went quiet. So most postmortems simply don't exist.
> Our question: after the merge, what does the repository already know?

**ON-SCREEN**
- Black frame → fade in on a terminal/editor showing an empty `postmortem.md`, cursor blinking.
- Overlay text at 0:10: **"≈ 90 minutes of human writing — per report"**.
- Final line overlays at 0:20: "the repository already knows".

**EDIT NOTE (producción)**
- Arrancar en negro 1,5 s; fundido al editor; dejar el cursor parpadeando solo 2 s máximo
  (mata el ritmo). Sin música hasta 0:03; entrada suave de sintetizador debajo.
- La frase "never gets written" debe caer con el zoom al archivo vacío.

---

## BEAT 2 · POSITIONING — repo-first, not stack-first · 0:25–0:55 (30 s)

**VOICEOVER (verbatim)**

> Rootly, PagerDuty, incident.io Nexus Code — they generate postmortems from the stack they
> manage: alerts, Slack threads, timelines. But most bug fixes leave none of that behind.
> This project takes the other entrance: **it starts from the repository, connecting the
> issue to the commit that introduced the bug — not from the managed incident stack.**
> You hand it a repo, an issue, and a fix SHA. It closes the post-fix loop that
> telemetry-centric IBM AIOps — Instana, Cloud Pak — never sees. A complement, never a competitor.

**ON-SCREEN**
- Split screen. Left (desaturated): "MANAGED INCIDENT STACK — alerts · Slack · timelines".
  Right (full color): a repository window with `issue #4907 → introducer commit → fix commit` arrows.
- Lower-third with the bolded differentiator line, held 4 s.
- End frame: small diagram "IBM AIOps → fix merged → [THIS] → postmortem".

**EDIT NOTE (producción)**
- Al decir "not from the managed incident stack", cortar/apagar el lado izquierdo y crecer
  el derecho: el contraste visual ES el argumento.
- "A complement, never a competitor" con subtítulo fijo — es la línea que protege frente a
  los patrocinadores IBM; no la acelerar.

---

## BEAT 3 · ARCHITECTURE — four pieces, not a prompt · 0:55–1:40 (45 s)

**VOICEOVER (verbatim)**

> Under the hood, four pieces. One: a deterministic evidence collector — GitHub API and git,
> zero AI — running SZZ, the classic algorithm that traces the lines a fix deleted back to
> the commit that introduced the bug. Two: IBM Bob, in Agent mode, orchestrating role
> subagents: a commit archaeologist, a document analyst, a code reviewer, an SRE
> synthesizer. Each one sees only its slice of the evidence. Three: an SRE template where
> every claim carries a link to its evidence, and every section carries a confidence badge —
> green, yellow, or red. Four: an evaluation harness that scores the result against a real
> human postmortem. **The prompt is the last 10% — the product is the pipeline.**

**ON-SCREEN**
- The 4-block architecture diagram (README), animating in block by block as numbered.
- ~1:12 → cut to **Bob IDE parallel-subagents panel screenshot (REQUIRED EVIDENCE flash #1)**,
  1.5 s, slight zoom.
- ~1:30 → close-up of the three badges 🟢🟡🔴 with labels: "every claim linked · grounded ·
  no evidence (said out loud)".
- Lower-third at the end: "the prompt is the last 10% — the product is the pipeline".

**EDIT NOTE (producción)**
- 1 s por bloque del diagrama; que el bloque 2 (Bob) destaque en color IBM.
- El flash del panel de subagentes entra JUSTO al oír "role subagents" — es evidencia
  obligatoria de la hackathon, que se note sin detener la narración.
- Cerrar con zoom a los badges: son el sello visual del producto y reaparecen en el demo.

---

## BEAT 4 · DEMO — the real curl CVE-2023-38545 · 1:40–3:10 (90 s)

**VOICEOVER (verbatim)**

> Now the real thing. Not a toy example: curl, and CVE-2023-38545 — the SOCKS5 heap
> overflow. One command: repo, issue, fix SHA. The collector pulls the issue thread, the fix
> diff, and candidate introducer commits. Bob's role agents analyze each slice in parallel.
> Seconds later: a postmortem. Every claim links to evidence. Sections git cannot ground
> are red — it says so, out loud. In the UI, the timeline is interactive. Click the
> introducer event: February 14th, 2020 — commit 4a4b63daaa, a non-blocking SOCKS refactor.
> Click any claim, and it jumps to the exact evidence behind it. One trap, by the way:
> issue 4907 is a pull request that was closed unmerged — the code landed by direct push.
> A tool that assumes "closed means merged" gets this case wrong. And side by side: our
> generated postmortem, and the one Daniel Stenberg wrote by hand. Same introducer. Here is
> the moment: the fix landed October 11th, 2023. The bug was born February 14th, 2020.
> That is the bug's origin story — 1,335 days before the fix.

**ON-SCREEN** (sub-beats)
- **1:40** — Terminal, type for real (or paste with typing animation):
  `bob-postmortem postmortem --repo curl/curl --issue 4907 --fix-sha fb4415d8aee6 --local-repo .repos/curl`
  (terminal font big enough that the command reads on a phone).
- **1:55** — While it runs: **task session consumption summary screenshot (REQUIRED EVIDENCE
  flash #2)**, 2 s, zoomed on Task ID / Tokens / Cost.
- **2:00** — `postmortem.md` opens: scroll slowly; Summary 🟢, Impact 🔴 "No evidence",
  Timeline 🟢, Root Cause 🟡 with the score. Badge close-up 2 s.
- **2:20** — Browser: the UI (`ui/index.html`). Interactive timeline; **click the 2020-02-14
  introducer event** → it expands to its evidence links (commit, issue, diff refs).
- **2:40** — Side-by-side view: generated postmortem vs Daniel Stenberg's blog postmortem;
  highlight "4a4b63daaa" on both sides.
- **2:50** — THE MONEY MOMENT: full-screen overlay counter animating **0 → 1,335 days**,
  "2020-02-14 → 2023-10-11". Hold 3 s. Hold the silence half a second before it.

**EDIT NOTE (producción)**
- Cache caliente antes de grabar: el comando debe terminar en pantalla en segundos, sin
  spinners eternos. Si la sesión Bob en vivo arriesga (Bobcoins/red), grabar la pasada
  determinista y mantener igualmente el flash del pantallazo de sesión.
- **`ui/index.html` es entregable del sprint (aún no existe en pre-sprint): grabar este
  sub-beat SOLO cuando la UI exista. Fallback si no llega a tiempo:** sustituir 2:20–2:40
  por scroll de `postmortem.md` (clic en los refs de evidencia) + split editor/navegador
  con el blog de Stenberg. El resto del beat no cambia.
- Contador 0→1335 con easing 1,5 s; silencio de 0,5 s justo antes. No poner música nueva,
  solo bajar la que haya. Si solo se salva una línea del video, es esta.
- El aside del PR no-mergeado ("closed unmerged") puede cortarse si falta tiempo (orden de
  recortes definido arriba), pero suma mucho a Originality: es un caso-trampa real resuelto.

---

## BEAT 5 · METRICS — scored against the human postmortem · 3:10–3:40 (30 s)

**VOICEOVER (verbatim)**

> Does it hold up? The harness compares the output against the human postmortem — and the
> scoring itself has no AI in it. Introducer prediction: exact match. Honesty check: passed.
> Claim linkage: fifteen out of fifteen claims carry valid evidence references. And the red
> sections — impact, detection — are the point: **it refuses to invent what git doesn't
> know.** The floor is honest about its limits too: three of eight timeline events, weak
> narrative. That's the baseline the Bob sessions are pushing up.

**ON-SCREEN**
- The eval table (`metrics.md`) with rows lighting up one at a time:
  `introducer_top1 ✓` → `honesty_check ✓` → `claim_linkage_rate 1.00 (15/15)`.
- Then the two red section headers from `postmortem.md`: Impact 🔴 / Detection 🔴 with
  "No evidence" highlighted.
- Small footer line: "baseline (no-AI floor): timeline recall 3/8 · root-cause 0.22 —
  narrative is the sprint's target".

**EDIT NOTE (producción)**
- Una fila por golpe de sonido; sin leer toda la tabla en voz alta — la tabla completa
  vive en el repo, el video solo clava los cuatro resultados.
- Nota de defensa (no en VO): el blog de Stenberg cita "1315 días" con extremos no
  definidos; nuestro 1.335 es commit-a-fix, verificable. Si un juez pregunta, no es un error.
  En pantalla solo 1,335 — no citar el 1315 para no confundir.

---

## BEAT 6 · HONEST LIMITS · 3:40–4:05 (25 s)

**VOICEOVER (verbatim)**

> Where it doesn't work yet. Operational incidents with no code to blame — like the GitLab
> 2017 database outage — degrade to an issues-only reconstruction, and the report says so
> out loud. Log4j is in progress. And attribution can be wrong: SZZ produces candidates,
> not proof. So every attribution carries its score and its badge. A wrong guess shows up
> in yellow or red — visible by design, never buried under confident prose.

**ON-SCREEN**
- Three cards sliding in, one per sentence:
  1. "ops-incident, no code → issues-only reconstruction (declared)"
  2. "log4j — in progress"
  3. "candidate score 0.70 · 🟡 badge — uncertainty stays on the surface"

**EDIT NOTE (producción)**
- Ritmo sobrio, sin música nueva; esta beat gana puntos de credibilidad (rubric:
  Presentation/Business Value) precisamente por no vender humo.
- La palabra clave visual es "declared": en la tarjeta 1, resaltarla.

---

## BEAT 7 · CLOSE + CTA · 4:05–4:20 (15 s)

**VOICEOVER (verbatim)**

> IBM Bob 2.0 is the orchestration layer. Your repository is the evidence. The postmortem
> nobody had time to write — in seconds, with receipts. github.com/el-informatico/postmortem-generator.

**ON-SCREEN**
- End card: the three badges 🟢🟡🔴 small, repo URL large and centered,
  "Apache-2.0 · built for IBM Bob 2.0". Hold the card 4 s after VO ends.

**EDIT NOTE (producción)**
- URL en pantalla el tiempo suficiente para copiarla a mano (mínimo 5 s totales).
- Último golpe de música y corte a negro. Sin créditos, sin "powered by" de ningún tipo
  (regla de cero atribución — Bob aparece como capa del producto, ya dicho en beat 3).

---

## One-take fallback (if recording time collapses on Sunday)

Single continuous screen capture, VO read live over it, ~75–90 s, no cuts needed:

1. "Postmortems don't get written — about ninety minutes each, after the incident is over.
   This project starts where the incident tools can't: the repository — the issue, the fix
   commit, and the commit that introduced the bug."
2. "One command over the real curl CVE-2023-38545 finds the introducer: commit 4a4b63daaa,
   February 14th, 2020 — the bug's origin story, 1,335 days before the fix."
3. "Every claim links to evidence, and sections git cannot ground — impact, detection — are
   declared 'No evidence' in red. It refuses to invent."
4. "Scored against Daniel Stenberg's own hand-written postmortem: exact introducer, honesty
   check passed, fifteen of fifteen claims linked."
5. "IBM Bob 2.0 orchestrates the role agents; the repository is the evidence.
   github.com/el-informatico/postmortem-generator."

On-screen for the fallback: type the demo command → open `postmortem.md` → scroll to the two
red sections → metrics table → end card with the URL. Even in this mode, keep one Bob task
session summary screenshot visible for at least 2 s (submission requirement).
