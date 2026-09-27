# Lista de capturas para Juan — evidencia Bob (26/27-sep 2026)

Fuente: `bob --list-tasks` (oficial, 27-sep 04:56 UTC). Workspace de todas:
`postmortem-generator (repo root)`.
En el IDE puede aparecer como "postmortem-generator" — si no ves NADA, abre el
filtro (embudo 🔽) y marca "All workspaces", o busca "curl" en Search tasks.

## Orden de aparición (por hora) — 6 tareas

| # | Tarea (primeras palabras del título) | task_id (para verificar) | PNG a guardar |
|---|---|---|---|
| 0 | "reply with ok" (smoke) | 6a72dcdd… | `ibm-hackathon-lablab_task00_smoke_summary.png` |
| 1 | "You are Document Analyst…" | 2d8266cc… | `ibm-hackathon-lablab_task01_document-analyst_summary.png` |
| 2 | "You are Code Reviewer…" | 900fb3e2… | `ibm-hackathon-lablab_task02_code-reviewer_summary.png` |
| 3 | "You are Commit Archaeologist…" | 13e68f09… | `ibm-hackathon-lablab_task03_commit-archaeologist_summary.png` |
| 4 | "You are SRE Synthesizer…" (POSTMORTEM FINAL) | d32e7061… | `ibm-hackathon-lablab_task04_sre-synthesizer_summary.png` |

*(falta el primer smoke f404dad9 del 23:37 y el de prueba del modo 6a72dcdd es
el segundo — ambos son "reply with ok"; captura solo UNO, el que veas con fecha
de hoy. El task00 es opcional pero recomendado.)*

## Pasos mecánicos (por cada fila)

1. Panel Bob → ícono **☰✓** (Tasks) → filtro embudo 🔽 → **All workspaces**
2. En la lista, localiza la tarea por su título (empieza "You are …")
3. Clic en la tarea → se abre en el chat
4. Clic en el **header de la tarea** (barra con el prompt y el coste ⏱)
5. Se expande el **consumption summary** (Context Length, Task ID, Tokens, API Cost)
6. Screenshot PNG → guárdala como el nombre de la tabla
7. Repite con la siguiente

**Verificación de identidad**: el Task ID del summary debe empezar con los
caracteres de la columna task_id (ej: d32e7061…). Si no coincide, no es esa.

## Dónde dejar los PNG
Arrástralos a la carpeta: `bob_sessions/` del proyecto (o dímelo por Telegram y los muevo yo a donde los sueltes).

## Estado de Bobcoins (después de F4)
Gastado hasta ahora: ~0.06 de 40 (smoke 0.022 + modo-test 0.010 + 4 sesiones F4).
Balance: ~39.9 — presupuesto holgado.
