"""Sheet-Provider — Schnittstelle zum Lesen von Google Sheets.

Liefert über `last_row(tab) -> dict` die letzte Zeile eines Tabellen-Tabs
als Spalten-Dict. Zwei Implementierungen:

  MockSheetProvider  — in-memory, für Unit-Tests ohne echte API.
  GoogleSheetProvider — echte Google Sheets API v4 (optional; Import lazy).

SICHERHEIT (eiserne Regel):
  GoogleSheetProvider prüft die Spreadsheet-ID gegen N8N_SHEET_ID_PROD
  und bricht mit PermissionError ab, wenn Produktion erkannt wird.
  Nur das konfigurierte TEST-Sheet (SHEET_TEST_ID) ist erlaubt.
  Nie Produktions-Daten lesen.

Konfig via Umgebungsvariablen:
  SHEET_TEST_ID          — Spreadsheet-ID des Test-Sheets (Pflicht für Google)
  SHEET_CREDENTIALS_FILE — Pfad zur service-account JSON-Datei
  SHEET_FORBIDDEN_IDS    — kommaseparierte Produktions-Spreadsheet-IDs (Riegel)
"""

from __future__ import annotations

import os
from typing import Any


# ---------------------------------------------------------------------------
# Basis-Protokoll (duck typing, kein ABC — Provider bleibt leichtgewichtig)
# ---------------------------------------------------------------------------


class SheetProvider:
    """Minimales Protokoll: last_row(tab) -> dict."""

    def last_row(self, tab: str) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# MockSheetProvider — für Tests
# ---------------------------------------------------------------------------


class MockSheetProvider(SheetProvider):
    """In-Memory-Provider für Tests.

    Initialisierung mit einem Dict von Tab-Name -> Liste von Zeilen-Dicts.
    last_row(tab) gibt die LETZTE Zeile zurück (wie Google Sheets).

    Beispiel:
        provider = MockSheetProvider({
            "Kontakte": [
                {"Name": "Max", "Telefon": "0123"},
                {"Name": "Erika", "Telefon": "0456"},
            ]
        })
        provider.last_row("Kontakte")  # -> {"Name": "Erika", "Telefon": "0456"}
    """

    def __init__(self, data: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._data: dict[str, list[dict[str, Any]]] = data or {}

    def set_rows(self, tab: str, rows: list[dict[str, Any]]) -> None:
        """Überschreibt die Zeilen eines Tabs (für Test-Setup)."""
        self._data[tab] = rows

    def last_row(self, tab: str) -> dict[str, Any]:
        rows = self._data.get(tab, [])
        return rows[-1] if rows else {}


# ---------------------------------------------------------------------------
# GoogleSheetProvider — optional, lazy Import (google-api-python-client)
# ---------------------------------------------------------------------------


class GoogleSheetProvider(SheetProvider):
    """Liest read-only aus dem konfigurierten Test-Google-Sheet.

    Setzt google-api-python-client + google-auth voraus (optional, nicht in
    requirements.txt — Pflicht-Dependencies werden nicht erzwungen).

    Installation bei Bedarf:
        pip install google-api-python-client google-auth

    Konfig via Env:
      SHEET_TEST_ID          — Spreadsheet-ID (nicht die URL, nur die ID)
      SHEET_CREDENTIALS_FILE — Pfad zur Service-Account-JSON
      SHEET_FORBIDDEN_IDS    — kommaseparierte verbotene IDs (Produktions-Riegel)
    """

    def __init__(self) -> None:
        self._spreadsheet_id = os.environ.get("SHEET_TEST_ID", "")
        self._credentials_file = os.environ.get("SHEET_CREDENTIALS_FILE", "")
        raw_forbidden = os.environ.get("SHEET_FORBIDDEN_IDS", "")
        self._forbidden_ids: list[str] = [
            s.strip() for s in raw_forbidden.split(",") if s.strip()
        ]
        self._service = None
        self._guard_prod_target()

    def _guard_prod_target(self) -> None:
        """Bricht ab, wenn die konfigurierte Sheet-ID in der Verboten-Liste steht."""
        for fid in self._forbidden_ids:
            if fid and fid == self._spreadsheet_id:
                raise PermissionError(
                    f"SHEET_TEST_ID {self._spreadsheet_id!r} ist als Produktions-Sheet "
                    f"gesperrt ({fid!r}) — Tests gegen Produktionsdaten sind verboten."
                )

    def _get_service(self):
        """Lazy-initialisiert den Google API Client."""
        if self._service is not None:
            return self._service
        try:
            # Lazy import — kein Fehler wenn Paket nicht installiert ist
            from google.oauth2 import service_account  # type: ignore
            from googleapiclient.discovery import build  # type: ignore
        except ImportError as exc:
            raise ImportError(
                "google-api-python-client und google-auth werden benötigt. "
                "Installation: pip install google-api-python-client google-auth"
            ) from exc

        if not self._credentials_file:
            raise EnvironmentError(
                "SHEET_CREDENTIALS_FILE ist nicht gesetzt. "
                "Bitte Service-Account-JSON-Pfad konfigurieren."
            )
        if not self._spreadsheet_id:
            raise EnvironmentError(
                "SHEET_TEST_ID ist nicht gesetzt. "
                "Bitte Test-Spreadsheet-ID konfigurieren."
            )

        creds = service_account.Credentials.from_service_account_file(
            self._credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def last_row(self, tab: str) -> dict[str, Any]:
        """Gibt die letzte Zeile des angegebenen Tabs als Spalten-Dict zurück.

        Liest die gesamte Seite (A:ZZ), nimmt Zeile 1 als Header und die
        letzte nicht-leere Zeile als Daten.
        """
        service = self._get_service()
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=self._spreadsheet_id,
                range=f"'{tab}'!A:ZZ",
            )
            .execute()
        )
        values = result.get("values", [])
        if len(values) < 2:
            return {}
        headers = values[0]
        # Letzte nicht-leere Zeile
        data_rows = [r for r in values[1:] if any(c.strip() for c in r if isinstance(c, str))]
        if not data_rows:
            return {}
        last = data_rows[-1]
        # Zeile auf Header-Länge normalisieren (fehlende Felder = leer)
        return {headers[i]: (last[i] if i < len(last) else "") for i in range(len(headers))}


# ---------------------------------------------------------------------------
# Factory-Funktion — baut den passenden Provider aus der Umgebung
# ---------------------------------------------------------------------------


def build_sheet_provider(*, dry_run: bool = False) -> SheetProvider | None:
    """Gibt einen Sheet-Provider zurück, wenn die Umgebung konfiguriert ist.

    Dry-Run oder fehlende SHEET_TEST_ID → None (Assertion überspringt sauber).
    Andernfalls: GoogleSheetProvider wenn google-Lib verfügbar, sonst Fehler.
    """
    if dry_run:
        return None
    sheet_id = os.environ.get("SHEET_TEST_ID", "")
    if not sheet_id:
        return None
    return GoogleSheetProvider()
