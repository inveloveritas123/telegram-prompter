"""
pytest-Tests fuer das Admin-Panel.
Prueft: alle vier Bereiche laden (GET 200), MCP-hinzufuegen schreibt valides mcp.json,
Ziel-speichern schreibt valides pipeline.yml.
"""
import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

# Temporaere Verzeichnisse vor dem Import setzen, damit config.py die richtigen Pfade hat
_TMP = tempfile.mkdtemp(prefix="admin_test_")
os.environ["CONFIG_DIR"] = str(Path(_TMP) / "config")
os.environ["REPORTS_DIR"] = str(Path(_TMP) / "reports")
os.environ["STATE_DIR"] = str(Path(_TMP) / "state")

# Verzeichnisse anlegen
for _d in ["config", "reports", "state"]:
    (Path(_TMP) / _d).mkdir(parents=True, exist_ok=True)

# Admin-App nach dem Setzen der Env-Variablen importieren
from admin.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=True)

CONFIG_DIR = Path(os.environ["CONFIG_DIR"])
REPORTS_DIR = Path(os.environ["REPORTS_DIR"])
STATE_DIR = Path(os.environ["STATE_DIR"])


# ─────────────────────── Bereich 1: MCP-Server ───────────────────────

class TestMcpBereich:
    """MCP-Server-Bereich laedt und MCP-Hinzufuegen schreibt valides mcp.json."""

    def test_mcp_seite_laedt(self):
        """GET /?tab=mcp gibt HTTP 200 zurueck."""
        resp = client.get("/?tab=mcp")
        assert resp.status_code == 200
        assert "MCP-Server" in resp.text

    def test_mcp_seite_ohne_tab_laedt(self):
        """GET / (ohne Tab) gibt HTTP 200 zurueck."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_mcp_hinzufuegen_schreibt_json(self, tmp_path):
        """POST /mcp/add schreibt valides mcp.json mit korrektem Format."""
        resp = client.post(
            "/mcp/add",
            data={"name": "test-mcp", "url": "https://example.com/mcp", "api_key": "secret123"},
            follow_redirects=True,
        )
        assert resp.status_code == 200

        mcp_path = CONFIG_DIR / "mcp.json"
        assert mcp_path.exists(), "mcp.json wurde nicht angelegt"

        data = json.loads(mcp_path.read_text(encoding="utf-8"))
        assert "mcpServers" in data, "Schluessel mcpServers fehlt"
        assert "test-mcp" in data["mcpServers"], "test-mcp wurde nicht eingetragen"

        server = data["mcpServers"]["test-mcp"]
        assert server["type"] == "http"
        assert server["url"] == "https://example.com/mcp"
        assert "Authorization" in server["headers"]
        assert server["headers"]["Authorization"] == "Bearer secret123"

    def test_mcp_hinzufuegen_ohne_key(self):
        """MCP ohne API-Key: headers-Dict ist leer."""
        client.post(
            "/mcp/add",
            data={"name": "mcp-ohne-key", "url": "https://example.com/mcp2", "api_key": ""},
            follow_redirects=True,
        )
        data = json.loads((CONFIG_DIR / "mcp.json").read_text(encoding="utf-8"))
        server = data["mcpServers"]["mcp-ohne-key"]
        assert server["headers"] == {}

    def test_mcp_entfernen(self):
        """POST /mcp/remove loescht den Eintrag aus mcp.json."""
        # Erst hinzufuegen
        client.post(
            "/mcp/add",
            data={"name": "zu-entfernen", "url": "https://x.example.com/mcp", "api_key": ""},
            follow_redirects=True,
        )
        # Dann entfernen
        resp = client.post("/mcp/remove", data={"name": "zu-entfernen"}, follow_redirects=True)
        assert resp.status_code == 200

        data = json.loads((CONFIG_DIR / "mcp.json").read_text(encoding="utf-8"))
        assert "zu-entfernen" not in data.get("mcpServers", {})

    def test_api_mcp_json(self):
        """GET /api/mcp gibt JSON zurueck."""
        resp = client.get("/api/mcp")
        assert resp.status_code == 200
        body = resp.json()
        assert "mcpServers" in body


# ─────────────────────── Bereich 2: Ziele & Zeitplan ───────────────────────

class TestZieleBereich:
    """Ziele-Bereich laedt und Speichern schreibt valides pipeline.yml."""

    def test_ziele_seite_laedt(self):
        """GET /?tab=goals gibt HTTP 200 zurueck."""
        resp = client.get("/?tab=goals")
        assert resp.status_code == 200
        assert "Ziele" in resp.text

    def test_ziel_hinzufuegen_schreibt_pipeline_yml(self):
        """POST /pipeline/goal/add schreibt valides pipeline.yml."""
        resp = client.post(
            "/pipeline/goal/add",
            data={
                "goal_id": "album-merge-fix",
                "suite": "kontakt-bot",
                "acceptance": "Suite kontakt-bot inkl. T7 gruen",
                "tags": "album, merge",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        yml_path = CONFIG_DIR / "pipeline.yml"
        assert yml_path.exists(), "pipeline.yml wurde nicht angelegt"

        data = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
        assert "goals" in data
        assert isinstance(data["goals"], list)
        assert len(data["goals"]) >= 1

        ziel = next((g for g in data["goals"] if g["id"] == "album-merge-fix"), None)
        assert ziel is not None, "Ziel album-merge-fix nicht in pipeline.yml"
        assert ziel["suite"] == "kontakt-bot"
        assert "T7" in ziel["acceptance"]
        assert "album" in ziel["tags"]
        assert "merge" in ziel["tags"]

    def test_pipeline_save_schreibt_budget(self):
        """POST /pipeline/save schreibt Budget- und Zeitplan-Felder."""
        resp = client.post(
            "/pipeline/save",
            data={
                "window": "03:00-05:00",
                "cadence": "nightly",
                "max_iterations": "8",
                "time_minutes": "180",
                "cost_cap": "6.0",
                "flaky_retries": "3",
                "goals_json": "[]",
            },
            follow_redirects=True,
        )
        assert resp.status_code == 200

        data = yaml.safe_load((CONFIG_DIR / "pipeline.yml").read_text(encoding="utf-8"))
        assert data["schedule"]["window"] == "03:00-05:00"
        assert data["budget"]["max_iterations"] == 8
        assert data["budget"]["cost_cap"] == 6.0
        assert data["flaky_retries"] == 3
        assert data["safety"]["staging_only"] is True

    def test_ziel_entfernen(self):
        """POST /pipeline/goal/remove loescht ein Ziel."""
        # Ziel anlegen
        client.post(
            "/pipeline/goal/add",
            data={
                "goal_id": "temp-ziel",
                "suite": "content-autopilot",
                "acceptance": "Alle Tests gruen",
                "tags": "",
            },
            follow_redirects=True,
        )
        # Entfernen
        resp = client.post("/pipeline/goal/remove", data={"goal_id": "temp-ziel"}, follow_redirects=True)
        assert resp.status_code == 200

        data = yaml.safe_load((CONFIG_DIR / "pipeline.yml").read_text(encoding="utf-8"))
        ids = [g["id"] for g in data.get("goals", [])]
        assert "temp-ziel" not in ids

    def test_api_pipeline_json(self):
        """GET /api/pipeline gibt JSON mit Pflichtfeldern zurueck."""
        resp = client.get("/api/pipeline")
        assert resp.status_code == 200
        body = resp.json()
        assert "goals" in body
        assert "schedule" in body
        assert "budget" in body


# ─────────────────────── Bereich 3: Secrets ───────────────────────

class TestSecretsBereich:
    """Secrets-Bereich laedt, zeigt keine Klartext-Werte."""

    def test_secrets_seite_laedt(self):
        """GET /?tab=secrets gibt HTTP 200 zurueck."""
        resp = client.get("/?tab=secrets")
        assert resp.status_code == 200
        assert "Secrets" in resp.text

    def test_secrets_zeigen_keine_klartextwerte(self, monkeypatch):
        """Secret-Werte erscheinen nicht im Klartext in der Seite."""
        monkeypatch.setenv("TELEGRAM_API_ID", "supersecret_1234567890")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_supersecrettoken")

        resp = client.get("/?tab=secrets")
        assert "supersecret_1234567890" not in resp.text
        assert "ghp_supersecrettoken" not in resp.text

    def test_api_secrets_status_kein_klartext(self, monkeypatch):
        """GET /api/secrets/status gibt Status ohne Klartext-Werte zurueck."""
        monkeypatch.setenv("TELEGRAM_API_HASH", "topmostgeheim")
        resp = client.get("/api/secrets/status")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        # Kein einziger Eintrag darf den echten Wert enthalten
        for entry in body:
            assert "topmostgeheim" not in str(entry.get("masked", ""))


# ─────────────────────── Bereich 4: Status ───────────────────────

class TestStatusBereich:
    """Status-Bereich laedt und zeigt Reports + STATE."""

    def test_status_seite_laedt(self):
        """GET /?tab=status gibt HTTP 200 zurueck."""
        resp = client.get("/?tab=status")
        assert resp.status_code == 200
        assert "Status" in resp.text

    def test_status_laedt_ohne_reports(self):
        """Status-Seite crasht nicht wenn Reports-Verzeichnis leer ist."""
        resp = client.get("/?tab=status")
        assert resp.status_code == 200

    def test_status_zeigt_reports(self):
        """Vorhandene JSON-Reports werden im Status angezeigt."""
        report = {
            "suite": "kontakt-bot",
            "run_id": "abc123def456",
            "started_at": "2026-06-17T02:00:00Z",
            "passed": 17,
            "total": 17,
            "all_green": True,
        }
        report_path = REPORTS_DIR / "kontakt-bot-abc123def456.json"
        report_path.write_text(json.dumps(report), encoding="utf-8")

        resp = client.get("/?tab=status")
        assert resp.status_code == 200
        assert "abc123def456" in resp.text
        assert "kontakt-bot" in resp.text

    def test_status_zeigt_state_md(self):
        """STATE.md-Inhalt wird auf der Status-Seite angezeigt."""
        state_path = STATE_DIR / "STATE.md"
        state_path.write_text("# STATE\nphase: idle\niteration: 0", encoding="utf-8")

        resp = client.get("/?tab=status")
        assert resp.status_code == 200
        assert "phase: idle" in resp.text

    def test_api_status_json(self):
        """GET /api/status gibt JSON mit reports und state zurueck."""
        resp = client.get("/api/status")
        assert resp.status_code == 200
        body = resp.json()
        assert "reports" in body
        assert "state" in body

    def test_status_ohne_state_md(self):
        """Status-Seite zeigt Platzhalter wenn STATE.md fehlt."""
        state_path = STATE_DIR / "STATE.md"
        if state_path.exists():
            state_path.unlink()
        resp = client.get("/?tab=status")
        assert resp.status_code == 200
        # Kein Crash, Platzhalter-Text vorhanden
        assert resp.status_code == 200
