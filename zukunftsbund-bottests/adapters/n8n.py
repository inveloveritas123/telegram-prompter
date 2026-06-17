"""n8n-API als ZWEITE Prüfebene (nicht als Treiber).

MTProto prüft den Dialog — die n8n-API prüft die Maschinerie dahinter:
  * Vor dem Lauf: Static Data zurücksetzen (Sessions/Auth/Rate leeren).
  * Nach Schritten: letzten Execution-Status abfragen (grün? roter Node?).
  * Setup-Helfer: sheetId/driveFolderId auf Test-Werte umstellen.

Im Dry-Run liefert der Client neutrale Erfolgswerte zurück.
"""

from __future__ import annotations

import os


class N8nClient:
    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.base_url = os.environ.get("N8N_BASE_URL", "")
        self.api_key = os.environ.get("N8N_API_KEY", "")
        self._client = None

    def _http(self):
        if self._client is None:
            import httpx  # type: ignore

            self._client = httpx.Client(
                base_url=self.base_url,
                headers={"X-N8N-API-KEY": self.api_key},
                timeout=30.0,
            )
        return self._client

    def reset_static_data(self, workflow_id: str) -> bool:
        """Setzt die Static Data eines Workflows zurück (Test-Vorbereitung)."""
        if self.dry_run:
            return True
        # Konkrete Umsetzung über n8n-API/eigenen Reset-Endpunkt — bewusst offen
        # gelassen, da projektspezifisch. Siehe CLAUDE.md / Sprint-Plan Phase 2.
        raise NotImplementedError("reset_static_data: projektspezifisch in Phase 2 umsetzen.")

    def last_execution_ok(self, workflow_id: str) -> bool:
        """True, wenn die letzte Execution des Workflows grün durchlief."""
        if self.dry_run:
            return True
        r = self._http().get(
            "/api/v1/executions",
            params={"workflowId": workflow_id, "limit": 1},
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return False
        last = data[0]
        return last.get("finished") is True and last.get("status") != "error"
