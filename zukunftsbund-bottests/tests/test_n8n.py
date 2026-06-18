"""Sprint 2: Tests für adapters/n8n.py — gemocktes httpx.

Prüft:
  - Dry-Run gibt immer True zurück (kein echter Call).
  - last_execution_ok: grüne Execution → True.
  - last_execution_ok: rote Execution (status=error) → False.
  - last_execution_ok: keine Executions → False.
  - reset_static_data: erfolgreicher PATCH → True.
  - reset_static_data: fehlgeschlagener PATCH → False.
  - Produktions-Riegel schlägt an, wenn N8N_BASE_URL einen verbotenen Marker enthält.
  - reset_static_data im Dry-Run läuft, ohne echten Call zu machen.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from adapters.n8n import N8nClient


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_client(dry_run: bool = False, base_url: str = "https://n8n.test.intern") -> N8nClient:
    """Erstellt einen N8nClient mit Test-Env."""
    with patch.dict(os.environ, {"N8N_BASE_URL": base_url, "N8N_API_KEY": "test-key"}):
        return N8nClient(dry_run=dry_run)


def _mock_response(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# Dry-Run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_last_execution_ok_dry_run_true(self):
        """Im Dry-Run gibt last_execution_ok immer True zurück."""
        client = _make_client(dry_run=True)
        assert client.last_execution_ok("wf-123") is True

    def test_reset_static_data_dry_run_true(self):
        """Im Dry-Run gibt reset_static_data immer True zurück."""
        client = _make_client(dry_run=True)
        assert client.reset_static_data("wf-123") is True

    def test_dry_run_macht_keine_http_calls(self):
        """Im Dry-Run wird _http() nie aufgerufen."""
        client = _make_client(dry_run=True)
        with patch.object(client, "_http") as mock_http:
            client.last_execution_ok("wf-123")
            client.reset_static_data("wf-123")
            mock_http.assert_not_called()


# ---------------------------------------------------------------------------
# last_execution_ok
# ---------------------------------------------------------------------------


class TestLastExecutionOk:
    def test_gruene_execution_gibt_true(self):
        """Letzte Execution status=success → True."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.get.return_value = _mock_response(
            {"data": [{"finished": True, "status": "success"}]}
        )
        with patch.object(client, "_http", return_value=mock_http):
            assert client.last_execution_ok("wf-abc") is True

    def test_rote_execution_gibt_false(self):
        """Letzte Execution status=error → False (absichtlich roter Node)."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.get.return_value = _mock_response(
            {"data": [{"finished": True, "status": "error"}]}
        )
        with patch.object(client, "_http", return_value=mock_http):
            assert client.last_execution_ok("wf-abc") is False

    def test_crashed_execution_gibt_false(self):
        """status=crashed → False."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.get.return_value = _mock_response(
            {"data": [{"finished": True, "status": "crashed"}]}
        )
        with patch.object(client, "_http", return_value=mock_http):
            assert client.last_execution_ok("wf-abc") is False

    def test_keine_executions_gibt_false(self):
        """Leere Datenliste (noch kein Lauf) → False."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.get.return_value = _mock_response({"data": []})
        with patch.object(client, "_http", return_value=mock_http):
            assert client.last_execution_ok("wf-abc") is False

    def test_nicht_abgeschlossen_gibt_false(self):
        """finished=False (läuft noch) → False."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.get.return_value = _mock_response(
            {"data": [{"finished": False, "status": "running"}]}
        )
        with patch.object(client, "_http", return_value=mock_http):
            assert client.last_execution_ok("wf-abc") is False

    def test_leere_workflow_id_gibt_false(self):
        """Leere Workflow-ID ohne HTTP-Call → False."""
        client = _make_client()
        assert client.last_execution_ok("") is False


# ---------------------------------------------------------------------------
# reset_static_data
# ---------------------------------------------------------------------------


class TestResetStaticData:
    def test_erfolgreicher_patch_gibt_true(self):
        """HTTP 200 auf PATCH → True."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.patch.return_value = _mock_response({})
        with patch.object(client, "_http", return_value=mock_http):
            result = client.reset_static_data("wf-xyz")
        assert result is True
        mock_http.patch.assert_called_once_with(
            "/api/v1/workflows/wf-xyz",
            json={"staticData": None},
        )

    def test_fehlgeschlagener_patch_gibt_false(self):
        """HTTP-Fehler (z.B. 404) → False (kein Exception-Bubble)."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.patch.side_effect = Exception("HTTP 404 Not Found")
        with patch.object(client, "_http", return_value=mock_http):
            result = client.reset_static_data("wf-xyz")
        assert result is False

    def test_leere_workflow_id_gibt_false(self):
        """Leere Workflow-ID ohne HTTP-Call → False."""
        client = _make_client()
        assert client.reset_static_data("") is False

    def test_reset_reproduzierbar(self):
        """Mehrfacher Aufruf liefert konsistent True bei Erfolg."""
        client = _make_client()
        mock_http = MagicMock()
        mock_http.patch.return_value = _mock_response({})
        with patch.object(client, "_http", return_value=mock_http):
            assert client.reset_static_data("wf-r1") is True
            assert client.reset_static_data("wf-r1") is True
        assert mock_http.patch.call_count == 2


# ---------------------------------------------------------------------------
# Produktions-Riegel
# ---------------------------------------------------------------------------


class TestProduktionsRiegel:
    def test_verbotener_host_wirft_permission_error(self):
        """Wenn N8N_BASE_URL einen Verboten-Marker enthält, PermissionError."""
        env = {
            "N8N_BASE_URL": "https://n8n.produktion.example.com",
            "N8N_API_KEY": "key",
            "N8N_FORBIDDEN_HOSTS": "produktion.example.com",
        }
        with patch.dict(os.environ, env):
            client = N8nClient(dry_run=False)
            with pytest.raises(PermissionError, match="verboten"):
                client._guard_prod_target()

    def test_erlaubter_host_kein_fehler(self):
        """Test-URL ohne Prod-Marker → kein Fehler."""
        env = {
            "N8N_BASE_URL": "https://n8n.test.intern",
            "N8N_API_KEY": "key",
            "N8N_FORBIDDEN_HOSTS": "produktion.example.com",
        }
        with patch.dict(os.environ, env):
            client = N8nClient(dry_run=False)
            client._guard_prod_target()  # darf nicht werfen

    def test_dry_run_ignoriert_riegel(self):
        """Im Dry-Run kommt es gar nicht bis zum Guard."""
        env = {
            "N8N_BASE_URL": "https://n8n.produktion.example.com",
            "N8N_API_KEY": "key",
            "N8N_FORBIDDEN_HOSTS": "produktion.example.com",
        }
        with patch.dict(os.environ, env):
            client = N8nClient(dry_run=True)
            # last_execution_ok im Dry-Run ruft _guard nie auf
            assert client.last_execution_ok("wf-1") is True


# ---------------------------------------------------------------------------
# Integration: Assertion überspringt sauber ohne n8n-Client
# ---------------------------------------------------------------------------


def test_assertion_ueberspringt_ohne_client():
    """n8n_execution_ok überspringt (True) wenn ctx['n8n'] fehlt.

    Direktaufruf der Assertion-Funktion, um den 'übersprungen'-Hinweis zu sehen.
    evaluate() liefert das Detail nur bei Fehlern; grüne Assertions geben '' zurück.
    """
    from adapters.base import Response
    from assertions.core import _REGISTRY

    resp = Response(text="OK", latency_ms=0.0)
    fn = _REGISTRY["n8n_execution_ok"]
    ok, detail = fn("wf-123", resp, {})
    assert ok is True
    assert "übersprungen" in detail
