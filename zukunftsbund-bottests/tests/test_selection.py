"""Tests für gezielte Test-Auswahl (Tags) — Kernmechanik für Re-Tests."""

import asyncio
from pathlib import Path

from runner.engine import run_suite
from runner.loader import load_suite
from runner.models import Status

ROOT = Path(__file__).resolve().parent.parent


def _load():
    return load_suite(ROOT / "suites" / "kontakt-bot" / "cases.yaml")


def test_tag_filter_runs_only_album():
    result = asyncio.run(run_suite(_load(), dry_run=True, tags={"album"}))
    by_id = {c.id: c.status for c in result.cases}
    assert by_id["T7-album-vorder-rueck"] is Status.PASS
    assert by_id["T1-neuer-kontakt-foto"] is Status.SKIP
    assert by_id["T12-passwort-riegel"] is Status.SKIP
    assert result.executed == 1
    assert result.all_green  # Skips zählen nicht als rot


def test_tags_parsed():
    suite = _load()
    t1 = next(c for c in suite.cases if c.id == "T1-neuer-kontakt-foto")
    assert "ocr" in t1.tags
