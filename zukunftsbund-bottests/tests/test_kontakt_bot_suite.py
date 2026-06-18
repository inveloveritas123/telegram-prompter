"""Sprint-3-Tests: vollständige T1–T17-Suite laden und strukturell prüfen.

Prüft, dass:
- alle 17 Fälle vorhanden sind,
- jeder Fall mindestens einen Tag hat,
- ausgewählte Tags (album, ocr, voice, auth, korrektur, ratelimit, dedupe) vorkommen,
- der Dry-Run aller 17 Fälle grün ist.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from runner.loader import load_suite
from runner.engine import run_suite
from runner.models import Status

ROOT = Path(__file__).resolve().parent.parent
SUITE_YAML = ROOT / "suites" / "kontakt-bot" / "cases.yaml"

EXPECTED_IDS = {
    "T1-neuer-kontakt-foto",
    "T2-ocr-rueckseite",
    "T3-ocr-kein-text",
    "T4-voice-transkript",
    "T5-korrektur-komma",
    "T6-korrektur-doppelpunkt",
    "T7-album-vorder-rueck",
    "T8-album-drei-seiten",
    "T9-dedupe-gleicher-kontakt",
    "T10-dedupe-update",
    "T11-update-feld",
    "T12-passwort-riegel",
    "T13-passwort-falsch-dreimal",
    "T14-rate-limit",
    "T15-korrektur-slash",
    "T16-korrektur-pipe",
    "T17-voice-kein-ton",
}


def test_alle_17_ids_vorhanden():
    """Suite enthält genau die 17 erwarteten Testfall-IDs."""
    suite = load_suite(SUITE_YAML)
    vorhandene_ids = {c.id for c in suite.cases}
    fehlende = EXPECTED_IDS - vorhandene_ids
    assert not fehlende, f"Fehlende Testfall-IDs: {fehlende}"
    assert len(suite.cases) == 17, f"Erwartet 17 Fälle, gefunden: {len(suite.cases)}"


def test_jeder_fall_hat_tags():
    """Jeder Testfall muss mindestens einen Tag haben."""
    suite = load_suite(SUITE_YAML)
    ohne_tags = [c.id for c in suite.cases if not c.tags]
    assert not ohne_tags, f"Fälle ohne Tags: {ohne_tags}"


def test_pflicht_tags_vorhanden():
    """Alle geforderten Feature-Tags sind mindestens einmal vergeben."""
    suite = load_suite(SUITE_YAML)
    alle_tags: set[str] = set()
    for c in suite.cases:
        alle_tags.update(c.tags)
    pflicht = {"album", "ocr", "voice", "auth", "korrektur", "ratelimit", "dedupe"}
    fehlende = pflicht - alle_tags
    assert not fehlende, f"Pflicht-Tags nicht vergeben: {fehlende}"


def test_album_faelle_vollstaendig():
    """T7 und T8 tragen den Tag 'album'."""
    suite = load_suite(SUITE_YAML)
    by_id = {c.id: c for c in suite.cases}
    assert "album" in by_id["T7-album-vorder-rueck"].tags
    assert "album" in by_id["T8-album-drei-seiten"].tags


def test_auth_faelle_vollstaendig():
    """T12 und T13 tragen den Tag 'auth'."""
    suite = load_suite(SUITE_YAML)
    by_id = {c.id: c for c in suite.cases}
    assert "auth" in by_id["T12-passwort-riegel"].tags
    assert "auth" in by_id["T13-passwort-falsch-dreimal"].tags


def test_dry_run_alle_17_gruen():
    """Dry-Run der gesamten T1–T17-Suite muss grün durchlaufen."""
    suite = load_suite(SUITE_YAML)
    result = asyncio.run(run_suite(suite, dry_run=True))
    assert result.total == 17
    assert result.passed == 17, [
        (c.id, c.status, [s.detail for s in c.steps if s.status is Status.FAIL])
        for c in result.cases
        if c.status is not Status.PASS
    ]


def test_dry_run_tag_album():
    """--tag album: nur Album-Fälle laufen, Rest wird übersprungen."""
    suite = load_suite(SUITE_YAML)
    result = asyncio.run(run_suite(suite, dry_run=True, tags={"album"}))
    by_id = {c.id: c.status for c in result.cases}
    assert by_id["T7-album-vorder-rueck"] is Status.PASS
    assert by_id["T8-album-drei-seiten"] is Status.PASS
    assert by_id["T1-neuer-kontakt-foto"] is Status.SKIP
    assert result.executed == 2
    assert result.all_green


def test_dry_run_tag_ratelimit():
    """--tag ratelimit: T13 und T14 laufen, Rest wird übersprungen."""
    suite = load_suite(SUITE_YAML)
    result = asyncio.run(run_suite(suite, dry_run=True, tags={"ratelimit"}))
    by_id = {c.id: c.status for c in result.cases}
    assert by_id["T13-passwort-falsch-dreimal"] is Status.PASS
    assert by_id["T14-rate-limit"] is Status.PASS
    assert by_id["T1-neuer-kontakt-foto"] is Status.SKIP
    assert result.all_green


def test_dry_run_tag_korrektur():
    """--tag korrektur: T5, T6, T15, T16 laufen."""
    suite = load_suite(SUITE_YAML)
    result = asyncio.run(run_suite(suite, dry_run=True, tags={"korrektur"}))
    by_id = {c.id: c.status for c in result.cases}
    for tid in ("T5-korrektur-komma", "T6-korrektur-doppelpunkt",
                "T15-korrektur-slash", "T16-korrektur-pipe"):
        assert by_id[tid] is Status.PASS, f"{tid} ist nicht PASS"
    assert result.executed == 4
    assert result.all_green
