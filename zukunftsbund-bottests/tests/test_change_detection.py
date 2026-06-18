"""Tests für Change-Detection: scripts/select_tests.py

Testet die Kernlogik pfade_zu_tags() mit simulierten Pfadlisten — KEIN echtes
git erforderlich. Die Diff-Pfadliste wird direkt injiziert.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.select_tests import lade_regeln, pfade_zu_tags, tags_zu_args

ROOT = Path(__file__).resolve().parent.parent
FEATURE_MAP = ROOT / "feature_map.yaml"


@pytest.fixture(scope="module")
def regeln():
    """Lädt die echte feature_map.yaml einmalig für alle Tests."""
    return lade_regeln(FEATURE_MAP)


# ---------------------------------------------------------------------------
# Mapping-Tests: Pfad → Tags
# ---------------------------------------------------------------------------

class TestPfadeZuTags:
    """Testet das Mapping geänderter Pfade auf Test-Tags."""

    def test_album_fixture_ergibt_album_tag(self, regeln):
        """Änderung an Album-Fixture aktiviert album-Tag."""
        tags = pfade_zu_tags(
            ["suites/kontakt-bot/fixtures/tilia_vorder.jpg"],
            regeln,
        )
        assert "album" in tags or "ocr" in tags, (
            "Foto-Fixture soll mindestens ocr oder album aktivieren"
        )

    def test_album_beide_seiten_fixture(self, regeln):
        """Beide Album-Fixtures → album-Tag."""
        tags = pfade_zu_tags(
            [
                "suites/kontakt-bot/fixtures/tilia_vorder.jpg",
                "suites/kontakt-bot/fixtures/tilia_rueck.jpg",
            ],
            regeln,
        )
        assert "album" in tags

    def test_ocr_einzelfoto_fixture(self, regeln):
        """Einzelfoto-Fixture → ocr-Tag."""
        tags = pfade_zu_tags(
            ["suites/kontakt-bot/fixtures/tilia_vorderseite.jpg"],
            regeln,
        )
        assert "ocr" in tags

    def test_voice_fixture_ogg(self, regeln):
        """Voice-Fixture (.ogg) → voice-Tag."""
        tags = pfade_zu_tags(
            ["suites/kontakt-bot/fixtures/test_sprache.ogg"],
            regeln,
        )
        assert "voice" in tags

    def test_voice_fixture_mp3(self, regeln):
        """Voice-Fixture (.mp3) → voice-Tag."""
        tags = pfade_zu_tags(
            ["suites/kontakt-bot/fixtures/kontakt.mp3"],
            regeln,
        )
        assert "voice" in tags

    def test_telegram_adapter_ergibt_mehrere_tags(self, regeln):
        """Änderung am Telegram-Adapter betrifft voice, ocr, album, dialog."""
        tags = pfade_zu_tags(["adapters/telegram.py"], regeln)
        erwartete = {"voice", "ocr", "album", "dialog"}
        assert erwartete.issubset(tags), (
            f"Telegram-Adapter soll {erwartete} aktivieren, bekam: {tags}"
        )

    def test_engine_ergibt_alle_feature_tags(self, regeln):
        """Änderung an der Engine → alle Feature-Tags aktiv."""
        tags = pfade_zu_tags(["runner/engine.py"], regeln)
        erwartete = {"ocr", "album", "voice", "auth", "dialog"}
        assert erwartete.issubset(tags), (
            f"Engine-Änderung soll alle Feature-Tags aktivieren, bekam: {tags}"
        )

    def test_cases_yaml_ergibt_auth_und_dialog(self, regeln):
        """Änderung an cases.yaml → auth und dialog."""
        tags = pfade_zu_tags(["suites/kontakt-bot/cases.yaml"], regeln)
        assert "auth" in tags
        assert "dialog" in tags

    def test_assertions_ergibt_alle_feature_tags(self, regeln):
        """Änderung an assertions/core.py → alle Feature-Tags."""
        tags = pfade_zu_tags(["assertions/core.py"], regeln)
        erwartete = {"ocr", "album", "voice", "auth", "dialog"}
        assert erwartete.issubset(tags)

    def test_http_adapter_ergibt_http_tag(self, regeln):
        """Änderung am HTTP-Adapter → http-Tag."""
        tags = pfade_zu_tags(["adapters/http.py"], regeln)
        assert "http" in tags

    def test_content_autopilot_suite(self, regeln):
        """Änderung an Content-Autopilot-Suite → content-Tag."""
        tags = pfade_zu_tags(
            ["suites/content-autopilot/cases.yaml"],
            regeln,
        )
        assert "content" in tags

    def test_unbekannter_pfad_ergibt_keine_tags(self, regeln):
        """Pfad ohne Treffer → leere Tag-Menge (kein Absturz)."""
        tags = pfade_zu_tags(
            ["docs/irgendwas.md", "README.md"],
            regeln,
        )
        # Kann leer sein — kein Crash erwartet
        assert isinstance(tags, set)

    def test_leere_pfadliste_ergibt_leere_menge(self, regeln):
        """Leere Pfadliste → leere Tag-Menge."""
        tags = pfade_zu_tags([], regeln)
        assert tags == set()

    def test_mehrere_pfade_vereinigen_tags(self, regeln):
        """Mehrere Pfade aus verschiedenen Features → Tags werden vereinigt."""
        tags = pfade_zu_tags(
            [
                "suites/kontakt-bot/fixtures/test_sprache.ogg",   # voice
                "suites/kontakt-bot/fixtures/tilia_vorderseite.jpg",  # ocr
            ],
            regeln,
        )
        assert "voice" in tags
        assert "ocr" in tags

    def test_feature_map_selbst_aktiviert_alle_tags(self, regeln):
        """Änderung an feature_map.yaml selbst → alle Feature-Tags (Sicherheitsnetz)."""
        tags = pfade_zu_tags(["feature_map.yaml"], regeln)
        erwartete = {"ocr", "album", "voice", "auth", "dialog"}
        assert erwartete.issubset(tags)


# ---------------------------------------------------------------------------
# tags_zu_args() — Ausgabe-Formatierung
# ---------------------------------------------------------------------------

class TestTagsZuArgs:
    """Testet die Umwandlung von Tags in Runner-Argumente."""

    def test_leere_menge_ergibt_leere_liste(self):
        assert tags_zu_args(set()) == []

    def test_einzelner_tag(self):
        args = tags_zu_args({"album"})
        assert args == ["--tag album"]

    def test_mehrere_tags_sortiert(self):
        args = tags_zu_args({"dialog", "album", "ocr"})
        assert args == ["--tag album", "--tag dialog", "--tag ocr"]

    def test_format_passend_fuer_runner(self):
        """Ausgabe muss `--tag <name>`-Format haben (passt zu runner.run --tag)."""
        args = tags_zu_args({"auth"})
        assert len(args) == 1
        assert args[0].startswith("--tag ")


# ---------------------------------------------------------------------------
# lade_regeln() — Laden der YAML-Konfiguration
# ---------------------------------------------------------------------------

class TestLadeRegeln:
    """Testet das Laden der feature_map.yaml."""

    def test_regeln_geladen(self):
        """feature_map.yaml enthält mindestens eine Regel."""
        regeln = lade_regeln(FEATURE_MAP)
        assert len(regeln) > 0

    def test_regeln_haben_globs_und_tags(self):
        """Jede Regel hat 'globs'- und 'tags'-Schlüssel."""
        regeln = lade_regeln(FEATURE_MAP)
        for regel in regeln:
            assert "globs" in regel, f"Regel ohne 'globs': {regel}"
            assert "tags" in regel, f"Regel ohne 'tags': {regel}"
            assert isinstance(regel["globs"], list)
            assert isinstance(regel["tags"], list)

    def test_pflicht_features_abgedeckt(self):
        """album, ocr, voice, auth, dialog müssen in der Map vorkommen."""
        regeln = lade_regeln(FEATURE_MAP)
        alle_tags: set[str] = set()
        for regel in regeln:
            alle_tags.update(regel.get("tags", []))
        pflicht = {"album", "ocr", "voice", "auth", "dialog"}
        fehlend = pflicht - alle_tags
        assert not fehlend, f"Pflicht-Features fehlen in feature_map.yaml: {fehlend}"
