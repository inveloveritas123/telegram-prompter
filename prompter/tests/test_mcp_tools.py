"""Tests für den prompter-mcp Tool-Layer.

Prüft list_suites und run_suite(dry_run=True) gegen die echten Suiten
aus zukunftsbund-bottests (kein echter MCP-Server nötig — direkter Import).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Framework aus dem eingebetteten Verzeichnis einbinden.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FRAMEWORK_DIR = _REPO_ROOT / "zukunftsbund-bottests"
if str(_FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_DIR))

# REPORTS_DIR auf ein temporäres Verzeichnis zeigen lassen (kein /data/reports nötig).
_TMP_REPORTS = _REPO_ROOT / "prompter" / "tests" / "_tmp_reports"

# Env-Variable setzen, bevor server importiert wird.
os.environ.setdefault("SUITES_DIR", str(_FRAMEWORK_DIR / "suites"))
os.environ["REPORTS_DIR"] = str(_TMP_REPORTS)

# Importiert das Tool-Modul (kein Server nötig).
from prompter.server import list_suites, run_suite  # noqa: E402

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_suites_gibt_bekannte_suiten_zurück() -> None:
    """list_suites muss mindestens 'kontakt-bot' und 'content-autopilot' enthalten."""
    suiten = list_suites()
    assert isinstance(suiten, list), "list_suites muss eine Liste zurückgeben"
    assert len(suiten) >= 1, "Es muss mindestens eine Suite vorhanden sein"
    # Bekannte Suiten aus dem Framework prüfen
    for erwartete in ("kontakt-bot", "content-autopilot"):
        assert erwartete in suiten, f"Suite {erwartete!r} fehlt in {suiten}"


def test_run_suite_dry_run_gibt_richtiges_schema_zurück() -> None:
    """run_suite im Dry-Run muss das definierte Schema zurückgeben."""
    suiten = list_suites()
    assert suiten, "Keine Suiten gefunden"

    ergebnis = run_suite(suiten[0], dry_run=True)

    pflichtfelder = {"run_id", "suite", "passed", "executed", "all_green", "report_path"}
    fehlende = pflichtfelder - ergebnis.keys()
    assert not fehlende, f"Fehlende Felder im Ergebnis: {fehlende}"

    assert isinstance(ergebnis["run_id"], str) and ergebnis["run_id"], (
        "run_id muss ein nicht-leerer String sein"
    )
    assert ergebnis["suite"] == suiten[0], "suite-Feld muss den Namen der Suite enthalten"
    assert isinstance(ergebnis["passed"], int), "passed muss ein int sein"
    assert isinstance(ergebnis["executed"], int), "executed muss ein int sein"
    assert isinstance(ergebnis["all_green"], bool), "all_green muss ein bool sein"
    assert Path(ergebnis["report_path"]).exists(), (
        "report_path muss auf eine existierende Datei zeigen"
    )


def test_run_suite_dry_run_ist_grün() -> None:
    """Alle Suiten müssen im Dry-Run grün laufen (all_green=True)."""
    suiten = list_suites()
    for name in suiten:
        ergebnis = run_suite(name, dry_run=True)
        assert ergebnis["all_green"], (
            f"Suite {name!r} ist im Dry-Run nicht grün: "
            f"passed={ergebnis['passed']}, executed={ergebnis['executed']}"
        )


def test_run_suite_unbekannte_suite_wirft_fehler() -> None:
    """Unbekannte Suite-Namen müssen ValueError werfen."""
    with pytest.raises(ValueError, match="nicht gefunden"):
        run_suite("diese-suite-existiert-nicht", dry_run=True)
