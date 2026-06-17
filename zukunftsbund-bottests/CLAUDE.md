# CLAUDE.md — Bau-Anleitung & Projektregeln für Claude Code

Diese Datei wird von Claude Code automatisch geladen. Sie beschreibt, **wie**
dieses Test-Framework gebaut und erweitert wird, und enthält fertige
**Copy-Paste-Prompts** für jede Sprint-Phase.

---

## Was dieses Projekt ist

Ein szenariogetriebenes Test-Framework, das echte Telegram-Nutzer simuliert
(MTProto/Telethon), die Maschinerie dahinter über die n8n-API prüft und über
GitHub als Regressionsnetz geteilt wird. Vier Schichten: Szenarien (YAML) →
Adapter → Assertions → Reporting. Details: `README.md`, `../KONZEPT-Testbot-Benchmark.md`.

## Eiserne Regeln (immer einhalten)

1. **Niemals gegen Produktion testen.** Nur Test-Bot, Test-Sheet, Staging-Webhooks.
   Die Riegel in `adapters/telegram.py` (`TELEGRAM_ALLOWED_TEST_BOTS`) und
   `adapters/http.py` (`HTTP_FORBIDDEN_HOSTS`) dürfen nie aufgeweicht werden.
2. **Secrets nie in YAML oder Git.** Immer `{{ env.NAME }}` + `.env` / Secret-Store.
   `.env`, `*.session` stehen in `.gitignore` — dort halten.
3. **Jedes Feature bringt seinen Testfall mit.** Wer ein Feature ändert, ergänzt
   oder aktualisiert im selben PR den passenden Fall samt `tags`.
4. **Dry-Run muss immer grün bleiben.** `python -m runner.run --all --dry-run`
   und `pytest -q` sind das Sicherheitsnetz vor jedem Commit.
5. **Adapter-Vertrag respektieren.** Neue Kanäle = neuer Adapter, der `adapters/base.py`
   erfüllt. Szenarien und Engine bleiben unverändert.
6. **Fixtures sind synthetisch.** Keine echten Personendaten (DSGVO).

## Konventionen

- Python ≥ 3.10, Standard-Lib + `PyYAML`, `telethon`, `httpx`. Keine schweren Frameworks.
- Async durchgängig in Engine/Adaptern. Tests laufen über `pytest` (asyncio_mode=auto).
- Sprache im Code/Kommentar: Deutsch (wie das restliche Projekt).
- Neue Assertion = Funktion mit `@assertion("name")` in `assertions/core.py` + Test.
- Vor jedem Commit: `pytest -q && python -m runner.run --all --dry-run`.

## Befehle (Cheatsheet)

```bash
pip install -r requirements.txt
python -m runner.run --suite kontakt-bot --dry-run     # Suite mit Mocks durchspielen
python -m runner.run --suite kontakt-bot --tag album   # gezielt re-testen
python -m runner.run --all --json --notify             # CI-Artefakt + Telegram-Feedback
pytest -q                                              # Unit-/Engine-Tests
```

---

## Sprint-Prompts für Claude Code

Diese Blöcke nacheinander in Claude Code einkippen. Jeder ist so geschnitten,
dass Claude Code ihn weitgehend autonom umsetzen kann. Der vollständige Plan
mit Zeitachse steht in `../SPRINT-PLAN.md`.

### Sprint 1 — Echte Telegram-Session anbinden (Phase 1 fertig machen)

```
Lies CLAUDE.md und README.md. Das Framework läuft im Dry-Run grün. Jetzt soll
der telegram-Adapter eine ECHTE Verbindung können.
1. Schreibe scripts/make_session.py: erzeugt interaktiv eine Telethon StringSession
   für den Test-Account und gibt sie aus (für TELEGRAM_TEST_SESSION).
2. Verifiziere adapters/telegram.py: _connect(), Event-Handler, Sammelfenster.
   Stelle sicher, dass der allowed-bots-Riegel greift.
3. Lege .env aus .env.example an (Platzhalter), dokumentiere die Schritte in README.
4. Halte den Dry-Run grün: pytest -q und python -m runner.run --all --dry-run.
Keine echten Secrets committen.
```

### Sprint 2 — n8n als zweite Prüfebene

```
Implementiere adapters/n8n.py vollständig gegen unsere n8n-Instanz:
- reset_static_data(workflow_id): leert Sessions/Auth/Rate vor dem Lauf.
- last_execution_ok(workflow_id): prüft die letzte Execution (grün / roter Node).
Verdrahte beides in der Engine: setup.reset_static_data fährt vor der Suite,
assert_n8n nach kritischen Schritten. Schreibe Tests mit gemocktem httpx.
Nutze, falls vorhanden, das n8n-MCP (Plugin n8n-io/skills) zum Verstehen der
Workflow-Struktur — siehe Abschnitt "n8n-Skills" unten.
```

### Sprint 3 — Vollständige Kontakt-Bot-Suite (T1–T17) + Fixtures

```
Erweitere suites/kontakt-bot/cases.yaml zur vollständigen T1–T17-Suite:
OCR-Erfassung, Voice, Korrektur-Parser (alle Trenner-Varianten), Dedupe, Update,
Album, Passwort-Riegel, Rate-Limit. Jeder Fall bekommt sinnvolle tags.
Lege synthetische Fixtures in suites/kontakt-bot/fixtures/ an (Platzhalter-Bilder,
keine echten Daten). Ergänze pro Fall mock_replies, damit der Dry-Run grün bleibt.
Aktualisiere die Tests.
```

### Sprint 4 — sheet_row gegen echtes Test-Sheet

```
Implementiere einen Sheet-Provider (Google Sheets API, read-only auf das TEST-Tab)
mit Methode last_row(tab) -> dict. Reiche ihn über context["sheet"] in run_suite.
Erzwinge: nur das TEST-Sheet, nie Produktion. Tests mit gemocktem Provider.
```

### Sprint 5 — Change-Detection (welche Tests nach einer Änderung?)

```
Baue scripts/select_tests.py: liest `git diff --name-only <base>..HEAD`, mappt
geänderte Pfade/Features auf Tags (Mapping in einer feature_map.yaml gepflegt)
und gibt die passenden --tag/--only-Argumente aus. Beispiel: Änderung am
Album-Code -> --tag album. Dokumentiere das Mapping. Wenn das n8n-MCP verfügbar
ist, ziehe auch die Workflow-Definition heran, um geänderte Nodes Tags zuzuordnen.
Ziel: "Ich hab das Album umgebaut" -> Framework weiß, T7 (+ verwandte) müssen laufen.
```

### Sprint 6 — MCP-Server (agentenfähig)

```
Baue den Runner als MCP-Server (Python, FastMCP) mit Tools:
list_suites, run_suite(name, env, tags?), get_report(run_id),
run_case(suite, case_id), compare_runs(a, b).
Der Server fährt NUR gegen Test-Targets (Riegel wiederverwenden). Ergebnisse als
strukturiertes JSON. So wird "fahr die Kontakt-Bot-Suite nach dem Deploy und sag
mir, was rot ist" zum Agenten-Auftrag. Nutze die mcp-builder-Anleitung.
```

### Sprint 7 — HTTP-Suite Content Autopilot + Brand-Voice (LLM-as-judge)

```
Baue die content-autopilot-Suite aus: Pipeline-Endpunkte, Brand-Voice-Regeln
(keine Bann-Wörter), Fallback-Kette (Bedrock -> Gemini -> Mistral), Kosten-Cap.
Ergänze eine Assertion `judge` (LLM-as-judge gegen einen EU-Endpoint), die fragt:
"Erfüllt dieser Post Brand-Voice v3?" -> pass/fail + Begründung. Budget pro Lauf cappen.
```

### Sprint 8 — Benchmark-Tiefe

```
Ergänze Latenz-/Kosten-Metriken pro Lauf im JSON-Report, implementiere
compare_runs (Regression sichtbar machen) und ein einfaches Trend-Dashboard
(statische HTML aus den reports/*.json). Keine externen Services.
```

---

## n8n-Skills (n8n-io/skills) — Rolle in diesem Projekt

Das offizielle Repo `n8n-io/skills` ist ein Claude-Code-Plugin mit ~15 Skills,
die einem Agenten helfen, **n8n-Workflows korrekt zu bauen/ändern** (über den
n8n-MCP-Server der Instanz). Es ist KEIN Test-Tool, aber komplementär:

- **Bau-Seite:** Wenn Claude Code den Bot-Workflow in n8n anfasst, sorgen die
  Skills + MCP dafür, dass Node-Configs, Expressions, Error-Handling beim ersten
  Mal stimmen — weniger Fehler, die dieser Testbot später fangen müsste.
- **Change-Detection:** Über den n8n-MCP kann der Agent die Workflow-Definition
  lesen und geänderte Nodes auf Test-Tags abbilden (siehe Sprint 5).

Installation (separat, optional, nur falls Workflows mit Claude Code gebaut werden):
```
/plugin marketplace add n8n-io/skills
/plugin install n8n-skills@n8n-io
```
Voraussetzung: n8n-Instanz mit aktiviertem instance-level MCP-Server.

## Definition of Done (jeder Sprint)

- `pytest -q` grün, `python -m runner.run --all --dry-run` grün.
- Neue/​geänderte Features haben Testfälle **mit tags**.
- Keine Secrets im Diff, keine Produktions-Targets.
- README/CLAUDE.md aktualisiert, wenn sich Befehle/Konventionen ändern.
```
