"""Sprint 4: Tests für adapters/sheets.py — gemockter Provider.

Prüft:
  - MockSheetProvider: last_row gibt die letzte Zeile zurück.
  - MockSheetProvider: leerer Tab → leeres Dict.
  - MockSheetProvider: erwartete Spalten gegen Mock-Daten.
  - sheet_row-Assertion: erwartete Zeile stimmt → PASS.
  - sheet_row-Assertion: Abweichung → FAIL mit Diff.
  - sheet_row-Assertion: kein Provider → überspringen (PASS).
  - GoogleSheetProvider-Riegel: verbotene Sheet-ID → PermissionError.
  - build_sheet_provider: Dry-Run → None.
  - build_sheet_provider: keine SHEET_TEST_ID → None.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from adapters.base import Response
from adapters.sheets import (
    GoogleSheetProvider,
    MockSheetProvider,
    build_sheet_provider,
)
from assertions.core import evaluate


# ---------------------------------------------------------------------------
# MockSheetProvider
# ---------------------------------------------------------------------------


class TestMockSheetProvider:
    def test_last_row_gibt_letzte_zeile(self):
        """last_row gibt die letzte Zeile des Tabs zurück."""
        provider = MockSheetProvider(
            {
                "Kontakte": [
                    {"Name": "Max", "Telefon": "0123"},
                    {"Name": "Erika", "Telefon": "0456"},
                ]
            }
        )
        row = provider.last_row("Kontakte")
        assert row == {"Name": "Erika", "Telefon": "0456"}

    def test_last_row_leerer_tab_gibt_leeres_dict(self):
        """Unbekannter / leerer Tab → leeres Dict."""
        provider = MockSheetProvider({})
        assert provider.last_row("NichtVorhanden") == {}

    def test_last_row_ein_eintrag(self):
        """Einzige Zeile wird als letzte zurückgegeben."""
        provider = MockSheetProvider({"Test": [{"A": "1"}]})
        assert provider.last_row("Test") == {"A": "1"}

    def test_set_rows_ueberschreibt_daten(self):
        """set_rows ersetzt den Tab-Inhalt."""
        provider = MockSheetProvider({"T": [{"X": "alt"}]})
        provider.set_rows("T", [{"X": "neu1"}, {"X": "neu2"}])
        assert provider.last_row("T") == {"X": "neu2"}

    def test_mehrere_tabs(self):
        """Mehrere Tabs unabhängig voneinander."""
        provider = MockSheetProvider(
            {
                "Tab1": [{"K": "A"}],
                "Tab2": [{"K": "B"}],
            }
        )
        assert provider.last_row("Tab1")["K"] == "A"
        assert provider.last_row("Tab2")["K"] == "B"


# ---------------------------------------------------------------------------
# sheet_row Assertion mit MockSheetProvider
# ---------------------------------------------------------------------------


class TestSheetRowAssertion:
    def _resp(self, text: str = "OK") -> Response:
        return Response(text=text, latency_ms=0.0)

    def test_erwartete_zeile_stimmt_pass(self):
        """Alle erwarteten Spalten stimmen → PASS."""
        provider = MockSheetProvider(
            {"Kontakte": [{"Name": "Hans", "Status": "gespeichert"}]}
        )
        spec = {"sheet_row": {"tab": "Kontakte", "last_row": {"Name": "Hans", "Status": "gespeichert"}}}
        ok, detail = evaluate(spec, self._resp(), {"sheet": provider})
        assert ok is True

    def test_erwartete_zeile_abweichung_fail(self):
        """Spalte weicht ab → FAIL mit Diff."""
        provider = MockSheetProvider(
            {"Kontakte": [{"Name": "Hans", "Status": "fehler"}]}
        )
        spec = {"sheet_row": {"tab": "Kontakte", "last_row": {"Status": "gespeichert"}}}
        ok, detail = evaluate(spec, self._resp(), {"sheet": provider})
        assert ok is False
        assert "Status" in detail
        assert "gespeichert" in detail
        assert "fehler" in detail

    def test_kein_provider_ueberspringt_sauber(self):
        """Kein Sheet-Provider im Context → überspringen (True).

        Direktaufruf der Assertion-Funktion, da evaluate() das Detail
        nur bei Fehlern weitergibt.
        """
        from assertions.core import _REGISTRY

        fn = _REGISTRY["sheet_row"]
        ok, detail = fn({"tab": "T", "last_row": {"Name": "X"}}, self._resp(), {})
        assert ok is True
        assert "übersprungen" in detail

    def test_mehrere_spalten_teilweise_falsch(self):
        """Zwei Spalten erwartet, eine stimmt, eine nicht → FAIL."""
        provider = MockSheetProvider(
            {"T": [{"A": "richtig", "B": "falsch"}]}
        )
        spec = {"sheet_row": {"tab": "T", "last_row": {"A": "richtig", "B": "erwartet"}}}
        ok, detail = evaluate(spec, self._resp(), {"sheet": provider})
        assert ok is False
        assert "B" in detail

    def test_leerer_tab_alle_spalten_fehlen(self):
        """Leerer Tab → alle erwarteten Werte fehlen → FAIL."""
        provider = MockSheetProvider({})
        spec = {"sheet_row": {"tab": "Leer", "last_row": {"Name": "X"}}}
        ok, detail = evaluate(spec, self._resp(), {"sheet": provider})
        assert ok is False


# ---------------------------------------------------------------------------
# GoogleSheetProvider — Produktions-Riegel
# ---------------------------------------------------------------------------


class TestGoogleSheetProviderRiegel:
    def test_verbotene_sheet_id_wirft_permission_error(self):
        """SHEET_TEST_ID in SHEET_FORBIDDEN_IDS → PermissionError."""
        env = {
            "SHEET_TEST_ID": "prod-sheet-id-123",
            "SHEET_FORBIDDEN_IDS": "prod-sheet-id-123",
            "SHEET_CREDENTIALS_FILE": "/tmp/creds.json",
        }
        with patch.dict(os.environ, env):
            with pytest.raises(PermissionError, match="verboten"):
                GoogleSheetProvider()

    def test_erlaubte_sheet_id_kein_fehler(self):
        """Test-Sheet-ID nicht in Verboten-Liste → kein Fehler beim Init."""
        env = {
            "SHEET_TEST_ID": "test-sheet-id-456",
            "SHEET_FORBIDDEN_IDS": "prod-sheet-id-123",
            "SHEET_CREDENTIALS_FILE": "/tmp/creds.json",
        }
        with patch.dict(os.environ, env):
            provider = GoogleSheetProvider()
            assert provider._spreadsheet_id == "test-sheet-id-456"

    def test_leere_forbidden_list_kein_fehler(self):
        """Keine Verboten-Liste → kein Fehler."""
        env = {
            "SHEET_TEST_ID": "beliebige-id",
            "SHEET_FORBIDDEN_IDS": "",
            "SHEET_CREDENTIALS_FILE": "/tmp/creds.json",
        }
        with patch.dict(os.environ, env):
            provider = GoogleSheetProvider()
            assert provider._spreadsheet_id == "beliebige-id"


# ---------------------------------------------------------------------------
# build_sheet_provider Factory
# ---------------------------------------------------------------------------


class TestBuildSheetProvider:
    def test_dry_run_gibt_none(self):
        """Dry-Run → None (kein Provider nötig)."""
        result = build_sheet_provider(dry_run=True)
        assert result is None

    def test_keine_sheet_id_gibt_none(self):
        """Keine SHEET_TEST_ID → None."""
        env = {"SHEET_TEST_ID": ""}
        with patch.dict(os.environ, env, clear=False):
            # Sicherstellen, dass SHEET_TEST_ID leer ist
            os.environ.pop("SHEET_TEST_ID", None)
            result = build_sheet_provider(dry_run=False)
            assert result is None

    def test_sheet_id_gesetzt_gibt_provider(self):
        """SHEET_TEST_ID gesetzt → GoogleSheetProvider (oder PermissionError wenn verboten)."""
        env = {
            "SHEET_TEST_ID": "test-sheet-xyz",
            "SHEET_FORBIDDEN_IDS": "",
            "SHEET_CREDENTIALS_FILE": "/tmp/fake.json",
        }
        with patch.dict(os.environ, env):
            provider = build_sheet_provider(dry_run=False)
            assert provider is not None
            assert isinstance(provider, GoogleSheetProvider)


# ---------------------------------------------------------------------------
# Integration: Engine mit Mock-Provider im Context
# ---------------------------------------------------------------------------


def test_engine_integriert_sheet_provider():
    """run_suite übergibt context['sheet'] an Assertions — grüner Durchlauf."""
    import asyncio
    from pathlib import Path

    from runner.engine import run_suite
    from runner.loader import load_suite
    from runner.models import Status

    ROOT = Path(__file__).resolve().parent.parent
    suite = load_suite(ROOT / "suites" / "kontakt-bot" / "cases.yaml")

    # Mock-Provider: kein Tab vorhanden → sheet_row überspringt/passt (da kein
    # assert_sheet in der kontakt-bot Suite)
    provider = MockSheetProvider({})
    ctx = {"sheet": provider}
    result = asyncio.run(run_suite(suite, dry_run=True, context=ctx))
    # Dry-Run muss grün bleiben — sheet-Provider ändert nichts an bestehenden Tests
    assert result.all_green
