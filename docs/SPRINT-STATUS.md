# Sprint-Status — ZUKUNFTSBUND Bot-Test-Framework

Stand der acht Sprints aus `../SPRINT-PLAN.md`. Gebaut wird in der deployten Kopie
`zukunftsbund-bottests/` (kanonisch); wo ein Sprint echte Credentials/Endpoints
braucht, ist Code+Tests **dry-run-grün** und der Live-Schritt unten vermerkt.

| Sprint | Inhalt | Status | Live-Schritt (durch dich) |
|---|---|---|---|
| 0 | Fundament | ✅ | — |
| 1 | Echte Telethon-Session | ✅ Code | `scripts/make_session.py` einmalig interaktiv ausführen → `TELEGRAM_TEST_SESSION` in `.env` |
| 2 | n8n als zweite Prüfebene | ✅ Code | `N8N_BASE_URL`/`N8N_API_KEY` setzen (Test-Instanz) |
| 3 | Kontakt-Bot-Suite T1–T17 + Fixtures | ✅ | — (Fixtures synthetisch) |
| 4 | `sheet_row` gegen Test-Sheet | ✅ Code | Google-Sheets-Creds + `SHEET_TEST_ID`; `pip install google-api-python-client` |
| 5 | Change-Detection (Diff→Tags) | ✅ | — (`scripts/select_tests.py`) |
| 6 | Test-Runner als MCP-Server | ✅ | **erfüllt durch `telegram-prompter/prompter/`** (FastMCP: list_suites/run_suite/run_case/get_report/compare_runs) |
| 7 | Content-Autopilot + Brand-Voice (LLM-judge) | ✅ Code | EU-Judge-Endpoint als `ctx["judge"]`-Provider; Budget-Cap in der Suite |
| 8 | Benchmark-Tiefe | ✅ | — (Metriken im JSON, `runner/compare.py`, `scripts/trend_dashboard.py`) |
| 9 | Autonome Nacht-Pipeline (Docker) | ✅ | siehe `../README.md` (Deploy) |

## Verifikation (Stand dieses Commits)
- **108 Framework-Tests grün**, `runner.run --all --dry-run` grün (content-autopilot 7/7, kontakt-bot 17/17).
- 58 Service-Tests (prompter/orchestrator/admin) grün.
- Riegel intakt (`TELEGRAM_ALLOWED_TEST_BOTS`, `HTTP_FORBIDDEN_HOSTS`, neu: `N8N_FORBIDDEN_HOSTS`, `SHEET_FORBIDDEN_IDS`).

## Neue Bausteine
- `scripts/make_session.py`, `scripts/select_tests.py` + `feature_map.yaml`, `scripts/trend_dashboard.py`
- `adapters/n8n.py` (voll), `adapters/sheets.py` (Mock + Google, lazy)
- `assertions/core.py`: `judge` (LLM-as-judge, Budget-Cap)
- `runner/compare.py` (compare_runs), Latenz-/Kosten-Metriken in `runner/reporter.py`/`models.py`

## Noch offen (bewusst, brauchen echte Außenwelt)
Echte Telethon-Session, echte n8n-Test-Instanz, echtes Google-Test-Sheet, echter
EU-Judge-Endpoint, CI-self-hosted-Runner (Sprint 4). Alles über `.env` einstöpselbar.
