# ZUKUNFTSBUND Bot-Test-Framework

> Ein Testfall ist Code. Ein grüner Lauf ist ein Versprechen.

Szenariogetriebenes, kanalunabhängiges Test- & Benchmark-Framework. Es simuliert
einen echten Telegram-Nutzer (MTProto/Telethon), prüft die Maschinerie dahinter
über die n8n-API und teilt Testfälle über GitHub als Regressionsnetz. Jedes neue
Feature bringt seinen Testfall mit.

Ausführliches Konzept: `../KONZEPT-Testbot-Benchmark.md`
Bau-Anleitung für Claude Code: `CLAUDE.md`

## Schnellstart (Dry-Run, ohne echte Telegram-Session)

```bash
pip install -r requirements.txt
python -m runner.run --suite kontakt-bot --dry-run      # spielt die Suite mit Mock-Antworten durch
python -m pytest -q                                     # Unit- + Engine-Tests
```

## Befehle

```bash
# Eine Suite fahren
python -m runner.run --suite kontakt-bot

# Alle entdeckten Suiten
python -m runner.run --all

# Gezielt nach einer Änderung re-testen:
python -m runner.run --suite kontakt-bot --only T7-album-vorder-rueck   # einzelner Fall
python -m runner.run --suite kontakt-bot --tag album                    # alle Fälle mit Tag "album"

# JSON-Report für CI/MCP + Feedback an dich per Telegram
python -m runner.run --suite kontakt-bot --json --notify
```

Exit-Code 0 = alles grün, 1 = mind. ein Fall rot. Übersprungene Fälle zählen nicht als rot.

## Architektur (vier Schichten)

| Schicht | Verzeichnis | Aufgabe |
|---|---|---|
| 1 — Szenarien (*Was*) | `suites/*/cases.yaml` | Testfälle als lesbares YAML, ohne Code |
| 2 — Treiber/Adapter (*Wie*) | `adapters/` | `telegram` (MTProto), `http`, `n8n` (zweite Prüfebene) |
| 3 — Assertions (*Wogegen*) | `assertions/core.py` | `contains`, `regex`, `not_contains`, `equals`, `latency_below`, `sheet_row`, `n8n_execution_ok` |
| 4 — Reporting (*Ergebnis*) | `runner/reporter.py`, `runner/notify.py` | Konsole, JSON, Telegram-Feedback |

Orchestrierung: `runner/engine.py` lädt Suite → fährt Adapter → prüft Assertions → sammelt `SuiteResult`.

## Drei Antworten auf „wie weiß das Setup, was zu testen ist, und wann es fertig ist?"

1. **Konversation:** Der `telegram`-Adapter unterhält sich als echter Nutzer mit dem Bot (sendet Foto/Text/Voice/Album, sammelt Antworten im Sammelfenster ein).
2. **Was re-testen nach einer Änderung:** Jeder Fall trägt `tags` (z. B. `album`, `auth`, `ocr`). Wurde das Album-Feature angefasst → `--tag album`. Wurde ein einzelner Fall gemeldet → `--only <id>`. Die volle Suite läuft als Regressionsnetz in CI / on-demand.
3. **Fertig-Feedback:** `--notify` schickt dir nach dem Lauf eine Telegram-Zusammenfassung; `--json` legt ein Artefakt für CI/MCP ab; ein MCP-Agent kann `get_report` lesen und zusammenfassen (Phase 3).

## Sicherheit (hart verdrahtet)

- Separater **Test-Account** (eigene API_ID/API_HASH), eigene Test-Nummer.
- `TELEGRAM_ALLOWED_TEST_BOTS` begrenzt, welche Bots überhaupt getestet werden dürfen.
- `HTTP_FORBIDDEN_HOSTS` sperrt Produktions-Hosts für den HTTP-Adapter.
- Secrets nur als Umgebungsvariablen (`{{ env.NAME }}` in YAML), nie im Klartext/Git.
- Fixtures sind synthetisch (keine echten Personendaten, DSGVO).

Setup der Umgebung: `.env.example` kopieren nach `.env` und ausfüllen.
```

## Echte Telegram-Session (Sprint 1)

Die Adapter-Verbindung läuft standardmäßig im Dry-Run-Modus (mit Mock-Antworten).
Um echte Telegram-Tests zu fahren, brauchst du eine StringSession des Test-Accounts.

### Einmalig: Session erzeugen

```bash
# Voraussetzungen: TELEGRAM_API_ID und TELEGRAM_API_HASH in .env gesetzt
python scripts/make_session.py
```

Das Skript fragt nach deiner Test-Account-Telefonnummer und generiert einen
verschlüsselten Session-String. Diesen kopierst du in `.env`:

```bash
# .env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_TEST_SESSION=<hier einfügen, was make_session.py ausgibt>
```

**Sicherheit:** Der StringSession ist vertraulich wie ein Passwort. Niemals in Git
oder öffentliche Repos committen. `.env` und `*.session` stehen in `.gitignore`.

### Tests mit echter Verbindung fahren

```bash
# Dry-Run (Mock, kein Telegram)
python -m runner.run --suite kontakt-bot --dry-run

# Echte Verbindung (benötigt gültige Session und Netzwerk)
python -m runner.run --suite kontakt-bot
```

Der Adapter prüft vor jedem Lauf, ob der Ziel-Bot in `TELEGRAM_ALLOWED_TEST_BOTS`
freigegeben ist (Sicherheits-Riegel). Nur dort freigegebene Bots werden getestet,
um Verwechslungen mit Produktions-Bots auszuschließen.

```bash
