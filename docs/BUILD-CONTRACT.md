# BUILD-CONTRACT — telegram-prompter (Sprint 9, Nacht-Pipeline)

Verbindlicher Integrations-Vertrag für **alle** Bau-Subagenten. Wer hier etwas
ändert, stimmt es vorher ab. Quelle der Wahrheit für Service-Namen, Ports, Pfade,
Env-Variablen und die Framework-API.

## Repo-Wurzel
`telegram-prompter/` (eigenes Git-Repo, Branch `main`). Enthält **alle drei Services**
plus das eingebettete Test-Framework `zukunftsbund-bottests/` (kopiert, ein Repo).

## Eiserne Leitplanken (aus KONZEPT-Nacht-Pipeline.md §5 — nicht aufweichen)
- **Nie gegen Produktion.** Nur Test-Bot/Test-Sheet/Staging. Riegel
  `TELEGRAM_ALLOWED_TEST_BOTS` und `HTTP_FORBIDDEN_HOSTS` bleiben scharf.
- **Secrets nur via .env/Docker-Secrets**, nie ins Image, nie in Git. `.gitignore` pflegen.
- **Stop-Kriterien** aus `config/pipeline.yml` hart respektieren (max Iterationen, Budget,
  „stuck → anhalten und melden").
- **Kein Selbst-Merge:** Ergebnis ist ein PR (im Dry-Run simuliert), nie ein Prod-Push.
- **Sprache** in Code/Kommentaren: Deutsch.

## Services, Ports, Service-Namen (docker-compose)
| Service (compose-Name) | Port (intern→host) | Rolle |
|---|---|---|
| `prompter-mcp` | 8080→8080 | Test-Framework als MCP-Server (HTTP/streamable-http) |
| `orchestrator` | — (cron-Tick, kein Port) | headless Bau-Test-Fix-PR-Loop |
| `admin`        | 8000→8000 | FastAPI-Web-Panel |

## Gemeinsame Pfade / Volumes (Container-intern)
- `/app/zukunftsbund-bottests/`  — das Framework. `prompter-mcp` (ro), `orchestrator` (rw).
- `/app/config/`  — `pipeline.yml`, `mcp.json`. `orchestrator` (rw), `admin` (rw).
- `/data/reports/`  — JSON-Reports (named volume `reports`). `prompter-mcp` schreibt,
  `admin` + `orchestrator` lesen.
- `/app/state/`  — `STATE.md`, `budget.json` (named volume `state`). `orchestrator` rw.
- `~/.claude` des Hosts → im `orchestrator` read-only gemountet (Auth für echte Engine).

## Env-Variablen (`.env`, Vorlage in `.env.example`)
Framework/Riegel: `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`, `TELEGRAM_TEST_SESSION`,
`TELEGRAM_ALLOWED_TEST_BOTS`, `HTTP_FORBIDDEN_HOSTS`, `N8N_BASE_URL`, `N8N_API_KEY`,
`NOTIFY_BOT_TOKEN`, `NOTIFY_CHAT_ID`.
Pipeline: `ORCHESTRATOR_ENGINE` (`mock`|`claude`, default `mock`), `GITHUB_TOKEN` (optional;
ohne → PR wird simuliert), `ADMIN_SECRET_KEY`, `PROMPTER_MCP_URL` (default
`http://prompter-mcp:8080/mcp`).

## Framework-API (so wird gewrappt — NICHT neu erfinden)
Aus `zukunftsbund-bottests/`:
```python
from runner.loader import discover_suites, load_suite   # discover_suites(SUITES_DIR)->{name:Path}
from runner.engine import run_suite                      # async run_suite(suite,*,dry_run,only,tags,context)->SuiteResult
from runner.reporter import write_json, telegram_summary # write_json(result, REPORTS_DIR)->Path
```
- `SuiteResult` Felder: `suite, run_id, cases[], started_at, finished_at`, Props
  `passed, skipped, executed, total, all_green`. JSON-Datei: `reports/<suite>-<run_id>.json`.
- `CaseResult`: `id, desc, status(pass|fail|error|skip), steps[], duration_ms, error`.
- `run_id` = `uuid4().hex[:12]`. Suiten liegen unter `zukunftsbund-bottests/suites/<name>/cases.yaml`.

## prompter-mcp — MCP-Tools (FastMCP, HTTP)
- `list_suites() -> [name]`
- `run_suite(name, env="staging", tags=None, only=None, dry_run=True) -> {run_id, suite, passed, executed, all_green, report_path}`
- `run_case(suite, case_id, dry_run=True) -> {…}` (intern `run_suite(only={case_id})`)
- `get_report(run_id) -> dict` (liest `/data/reports/*-<run_id>.json`)
- `compare_runs(a, b) -> {regressions:[…], fixed:[…]}`
Nur Test-Targets — Riegel des Frameworks gelten unverändert. Lange Telegram-Läufe:
asynchrone `run_id`-Rückgabe statt blockierend (im Dry-Run synchron ok).

## orchestrator — cron-Tick (ralph-Loop-Muster)
Ein Aufruf = **eine** begrenzte Runde, crash-sicher über `/app/state/STATE.md`:
1. Budget/Kill-Switch prüfen (Stop-Kriterien aus `pipeline.yml`). 2. Ziel aus
`pipeline.yml` lesen. 3. **bauen** (Engine). 4. **testen** über prompter-mcp
(`run_suite`/`run_case`). 5. Report lesen. 6. rot → fixen + gezielt re-testen
(`tags`/`only`), 1–2× Flaky-Retry. 7. grün → Branch-Commit + PR (simuliert ohne Token).
8. STATE schreiben, raus. Entscheidung `continue|stop|halt` deterministisch
(Drift-Pausegate, max-iter) — wie `ralph_decide`.
**Engine-Abstraktion:** Interface `AgentEngine.build(goal, context)->BuildResult`.
`MockEngine` (default, Dry-Run-Zyklus ohne echten Claude) und `ClaudeCodeEngine`
(`claude -p "<task>" --output-format json`, Auth über gemountetes `~/.claude`,
kein API-Key). Umschaltung via `ORCHESTRATOR_ENGINE`.
Cron: Container-internes cron ODER dokumentierte Host-Crontab-Zeile, die
`docker compose run --rm orchestrator tick` im Nacht-Fenster auslöst. CLI:
`python -m orchestrator.run tick` (eine Runde), `--dry-run` erzwingt MockEngine.

## admin — FastAPI + leichtes Frontend (Port 8000)
Vier Bereiche (Optik an `../Konzept-Nacht-Pipeline.html` anlehnen):
1. **MCP-Server** verwalten (hinzufügen/entfernen, URL+Key, „Verbindung testen") →
   schreibt `config/mcp.json`. 2. **Ziele & Zeitplan** (Zielstellung als Tests, Nacht-Fenster,
   Budget, Iterations-Limit) → schreibt `config/pipeline.yml`. 3. **Secrets** (maskiert,
   verschlüsselt; nie im Klartext rendern). 4. **Status** (letzte Läufe aus `/data/reports`,
   Pass/Fail, PR-Links, STATE) + **Staging-Marker** sichtbar. Ein Stack (FastAPI +
   Jinja/HTMX oder minimal JS), keine schwere SPA.

## config/-Formate
- `config/pipeline.yml`: `goals:[{id, suite, acceptance, tags}]`, `schedule:{window, cadence}`,
  `budget:{max_iterations, time_minutes, cost_cap}`, `flaky_retries:2`, `safety:{staging_only:true}`.
- `config/mcp.json`: `{ "mcpServers": { "<name>": {"type":"http","url":...,"headers":{...}} } }`.

## Definition of Done (Konzept §DoD)
`docker compose up` startet alle 3 Container; Admin erreichbar und trägt eine MCP (n8n)
nach `config/mcp.json` ein; Orchestrator fährt im Dry-Run einen kompletten Zyklus gegen
Mock-Targets und öffnet/simuliert bei grün einen PR; `pytest -q` grün; `python -m
runner.run --all --dry-run` grün; `docker compose config` valide; keine Secrets/kein
Prod-Target im Diff; README beschreibt das Server-Deployment vollständig.
