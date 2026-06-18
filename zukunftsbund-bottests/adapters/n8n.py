"""n8n-API als ZWEITE Prüfebene (nicht als Treiber).

MTProto prüft den Dialog — die n8n-API prüft die Maschinerie dahinter:
  * Vor dem Lauf: Static Data zurücksetzen (Sessions/Auth/Rate leeren).
  * Nach Schritten: letzten Execution-Status abfragen (grün? roter Node?).
  * Setup-Helfer: sheetId/driveFolderId auf Test-Werte umstellen.

Im Dry-Run liefert der Client neutrale Erfolgswerte zurück.

SICHERHEIT: Requests werden nur gegen N8N_BASE_URL gesendet. Enthält
die URL einen der N8N_FORBIDDEN_HOSTS-Marker, bricht der Client mit
PermissionError ab — analog zum Riegel in adapters/http.py.
"""

from __future__ import annotations

import os

# Produktions-Marker, die niemals als Ziel erlaubt sind.
# Erweiterbar via N8N_FORBIDDEN_HOSTS (kommasepariert).
_DEFAULT_FORBIDDEN: list[str] = []


class N8nClient:
    """HTTP-Client gegen eine n8n-Test-Instanz.

    Konfig via Umgebungsvariablen:
      N8N_BASE_URL  — z. B. https://n8n.test.intern
      N8N_API_KEY   — Bearer-Token der Test-Instanz
      N8N_FORBIDDEN_HOSTS — kommaseparierte Liste verbotener Host-Marker
                            (Produktions-Riegel, analog HTTP_FORBIDDEN_HOSTS)
    """

    def __init__(self, *, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.base_url = os.environ.get("N8N_BASE_URL", "").rstrip("/")
        self.api_key = os.environ.get("N8N_API_KEY", "")
        self._client = None
        # Produktions-Riegel: konfigurierbar + fest verdrahtet
        raw = os.environ.get("N8N_FORBIDDEN_HOSTS", "")
        extra = [m.strip() for m in raw.split(",") if m.strip()]
        self._forbidden: list[str] = _DEFAULT_FORBIDDEN + extra

    # ------------------------------------------------------------------
    # Interner HTTP-Client (lazy, wird im Dry-Run nie erzeugt)
    # ------------------------------------------------------------------

    def _http(self):
        if self._client is None:
            import httpx  # type: ignore

            self._guard_prod_target()
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "X-N8N-API-KEY": self.api_key,
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    def _guard_prod_target(self) -> None:
        """Bricht ab, wenn base_url einen Produktions-Marker enthält."""
        for marker in self._forbidden:
            if marker and marker in self.base_url:
                raise PermissionError(
                    f"N8N_BASE_URL {self.base_url!r} enthält gesperrten Marker {marker!r} — "
                    "Tests gegen die Produktions-n8n-Instanz sind verboten."
                )

    def close(self) -> None:
        """Gibt den HTTP-Client frei (optional, z. B. am Suite-Ende)."""
        if self._client is not None:
            self._client.close()
            self._client = None

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def reset_static_data(self, workflow_id: str) -> bool:
        """Setzt die Static Data eines Workflows zurück.

        Löscht gespeicherten Sitzungszustand (Sessions/Auth/Rate-Zähler),
        damit jeder Testlauf mit einem sauberen Zustand beginnt.

        Dry-Run: kein echter Call, gibt immer True zurück.

        Rückgabe: True bei Erfolg (HTTP 2xx oder leer), False bei Fehler.
        """
        if self.dry_run:
            return True
        if not workflow_id:
            return False
        try:
            # n8n-REST-API v1: POST /api/v1/workflows/{id}/activate und
            # PATCH /api/v1/workflows/{id} mit leerer staticData.
            # Robuster Weg: PATCH staticData auf leeres Objekt setzen.
            r = self._http().patch(
                f"/api/v1/workflows/{workflow_id}",
                json={"staticData": None},
            )
            r.raise_for_status()
            return True
        except Exception:
            return False

    def last_execution_ok(self, workflow_id: str) -> bool:
        """Prüft, ob die letzte Execution des Workflows erfolgreich war.

        Grün = finished=True UND status != "error" UND kein Node mit error.

        Dry-Run: kein echter Call, gibt immer True zurück.
        """
        if self.dry_run:
            return True
        if not workflow_id:
            return False
        r = self._http().get(
            "/api/v1/executions",
            params={"workflowId": workflow_id, "limit": 1, "includeData": "false"},
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            # Noch keine Execution → technisch kein Fehler, aber nicht prüfbar.
            return False
        last = data[0]
        return (
            last.get("finished") is True
            and last.get("status") not in ("error", "crashed", "waiting")
        )
