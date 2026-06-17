# telegram-prompter — Autonome Bau-Test-Pipeline (Nacht-Schleife)

> **Eine Zielstellung rein, ein grüner Pull Request raus.**
> ZUKUNFTSBUND Sprint 9. Drei Docker-Container schalten das bestehende
> Test-Framework (`zukunftsbund-bottests/`) zu einem headless-Dienst zusammen:
> Claude Code baut, der telegram-prompter testet, der Orchestrator korrigiert sich
> selbst und liefert einen reviewbaren PR. Produktion wird nie automatisch berührt.

## Architektur

| Service | Rolle | Port |
|---|---|---|
| **prompter-mcp** | Test-Framework als MCP-Server (FastMCP/HTTP). Tools: `list_suites`, `run_suite`, `run_case`, `get_report`, `compare_runs`. Fährt den Test-Bot über MTProto. | 8080 |
| **orchestrator** | Headless Bau-Test-Fix-PR-Loop als **cron-Tick** (eine Runde pro Aufruf, crash-sicher über `STATE.md`, ralph-Loop-Muster). Engine umschaltbar: `mock` (Dry-Run) ↔ `claude` (echte CLI). | — |
| **admin** | FastAPI-Web-Panel: MCPs verwalten, Ziele/Zeitplan/Budget, Secrets (maskiert), Live-Status. Staging-Marker. | 8000 |

Vollständiger Integrations-Vertrag: [`docs/BUILD-CONTRACT.md`](docs/BUILD-CONTRACT.md).
Konzept: `../KONZEPT-Nacht-Pipeline.md`. Hartes Grün: [`GATE-REPORT.md`](GATE-REPORT.md).

## Sicherheits-Leitplanken (nicht verhandelbar)
- **Nie gegen Produktion** — nur Test-Bot/Test-Sheet/Staging. Riegel
  `TELEGRAM_ALLOWED_TEST_BOTS` / `HTTP_FORBIDDEN_HOSTS` bleiben scharf.
- **Secrets nur via `.env`/Docker-Secrets** — nie ins Image, nie in Git.
- **Stop-Kriterien** aus `config/pipeline.yml` (max Iterationen, Budget, „stuck → melden").
- **Kein Selbst-Merge** — Ergebnis ist ein PR (ohne Token simuliert). Promote nach Prod = dein manueller Knopfdruck.

## Lokal prüfen (ohne Server, ohne Secrets)

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r prompter/requirements.txt -r orchestrator/requirements.txt -r admin/requirements.txt

# Framework grün?
( cd zukunftsbund-bottests && PYTHONPATH=. python -m pytest -q && PYTHONPATH=. python -m runner.run --all --dry-run )

# Service-Tests
PYTHONPATH=zukunftsbund-bottests:. python -m pytest -q prompter/tests
PYTHONPATH=. python -m pytest -q orchestrator/tests admin/tests

# Ein kompletter Mock-Zyklus (bauen→testen→Report→PR-Sim), ohne echten Claude:
PYTHONPATH=. python -m orchestrator.run tick --dry-run

# Compose-Validität
docker compose config
```

## Deployment auf dem Server (Netcup, im VPN)

1. **Repo klonen** auf den Server (eigene Infra, getrennt von Produktion).
2. **`.env` anlegen** aus `.env.example` und befüllen (Telegram-API, Test-Session,
   n8n-Key, Notify, optional `GITHUB_TOKEN`). `.env` bleibt lokal, nie committen.
   ```bash
   cp .env.example .env && nano .env
   ```
3. **Telethon-Session erzeugen** (einmalig, interaktiv) für den Test-Account und in
   `TELEGRAM_TEST_SESSION` hinterlegen:
   ```bash
   ( cd zukunftsbund-bottests && python scripts/make_session.py )   # Sprint 1
   ```
4. **Claude Code auf dem Host** ist bereits installiert und angemeldet (kein API-Key).
   Der Orchestrator-Container mountet `~/.claude` read-only und nutzt diese Session,
   wenn `ORCHESTRATOR_ENGINE=claude` gesetzt ist. Default ist `mock` (sicher).
5. **Hochfahren:**
   ```bash
   docker compose up -d --build
   ```
   - Admin-Panel: `http://<server>:8000` → MCP (n8n) eintragen, Ziel + Nacht-Fenster + Budget setzen.
   - prompter-mcp: `http://<server>:8080/mcp`.
6. **Nacht-Tick per Host-Crontab** (statt Dauer-Daemon — hält die Schleife „am Leben",
   jeder Tick ist eine begrenzte, crash-sichere Runde):
   ```cron
   # alle 2 Stunden im Nacht-Fenster eine Runde fahren
   0 1-6/2 * * *  cd /pfad/telegram-prompter && docker compose run --rm orchestrator tick >> logs/orchestrator.log 2>&1
   ```
7. **Morgens:** PR reviewen, grünen Stand manuell nach Produktion promoten.

## Echte Engine scharf schalten
`ORCHESTRATOR_ENGINE=claude` in `.env` → der Orchestrator ruft `claude -p` headless
(Auth über gemountetes `~/.claude`). Ohne `GITHUB_TOKEN` wird der PR-Schritt simuliert.
Budget in `config/pipeline.yml` hart deckeln, bevor du auf `claude` umstellst.
