# GATE-REPORT — telegram-prompter (Wächter-Lauf)

> Hartes Grün nach WERKBANK-Prinzip: **GRÜN ⟺ jedes Pflicht-Gate des Profils ist
> aktiv PASS.** Ein SKIP/FAIL eines Pflicht-Gates ⇒ ROT. Optionale Gates sind
> beratend und färben nicht rot, werden aber ehrlich als „nicht geprüft" ausgewiesen.

- **Profil:** `nacht-pipeline` (Pflichtmenge = Konzept-DoD, `KONZEPT-Nacht-Pipeline.md`)
- **Stand:** 2026-06-17 · **Branch:** `main` (lokal, Erst-Build) · **Engine geprüft:** `mock` (Dry-Run)

## Pflicht-Gates (Profil `nacht-pipeline`)

| Gate | Prüfung | Status | Beleg |
|---|---|---|---|
| A2 | Akzeptanzkriterien testbar formuliert | **PASS** | `config/pipeline.yml` → `goals[].acceptance` als Tests |
| B3 | Build/Imports kompilieren | **PASS** | alle Service-Module importierbar (`fastmcp`, `fastapi`, Framework) |
| C1 | Unit-/Service-Tests grün | **PASS** | **64 Tests** grün: Framework 10 · prompter 4 · orchestrator 30 · admin 20 |
| C-dry | Framework-Dry-Run grün | **PASS** | `runner.run --all --dry-run` → content-autopilot 2/2, kontakt-bot 3/3 |
| D3 | Secret-Scan: kein Secret im Diff | **PASS** | Regex-Scan über py/yml/json/env — leer; `.env` git-ignoriert |
| DoD-1 | `docker compose config` valide | **PASS** | drei Services, named volumes `reports`/`state` |
| DoD-2 | Voller Mock-Zyklus läuft durch | **PASS** | Tick: Build→Test (3/3)→Report→**stop**→PR-Sim→STATE geschrieben |
| DoD-3 | Admin trägt MCP nach `config/mcp.json` | **PASS** | admin-Test schreibt valides `mcpServers`-JSON |
| SAFE | Kein Prod-Target, Riegel scharf | **PASS** | `safety.staging_only: true`; Framework-Riegel unverändert; PR ohne Token simuliert |

**Pflicht-Gates ohne PASS: 0**

## VERDIKT: 🟢 GRÜN
Alle Pflicht-Gates des Profils `nacht-pipeline` sind aktiv PASS. Definition of Done
aus `KONZEPT-Nacht-Pipeline.md` erfüllt.

## Optionale Gates (beratend — nicht geprüft, Follow-up)
Ehrlich als SKIP ausgewiesen, färben dieses Profil **nicht** rot:
- B1 Lint (ruff), B2 Typecheck (mypy) — Dev-Toolchain noch nicht verdrahtet.
- C2 Coverage-Schwelle — nicht gemessen.
- D1 SAST (bandit/semgrep), D2 SCA (CVE-Scan der Deps) — nicht gelaufen.
- F1 Dependency-Pinning — requirements nutzen `>=`-Ranges, noch nicht gepinnt.
- **Echte Engine** (`ORCHESTRATOR_ENGINE=claude`) ungetestet (bewusst — kein API-Key/Kosten im Build).

## Nicht im Scope dieses Builds
Echte Telethon-Session (Sprint 1), n8n-MCP-Live-Anbindung (Sprint 2), Image-Build mit
`docker compose build` (lokal nicht ausgeführt — nur `config` validiert).
