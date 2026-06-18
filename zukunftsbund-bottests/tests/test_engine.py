"""End-to-End-Test der Engine im Dry-Run (Mock-Adapter)."""

import asyncio
from pathlib import Path

from runner.engine import run_suite
from runner.loader import load_suite
from runner.models import Status

ROOT = Path(__file__).resolve().parent.parent


def test_dry_run_kontakt_bot_all_green():
    suite = load_suite(ROOT / "suites" / "kontakt-bot" / "cases.yaml")
    result = asyncio.run(run_suite(suite, dry_run=True))
    # Im Dry-Run liefern die Mock-Antworten genau die erwarteten Strings.
    assert result.total == 17
    assert result.passed == 17, [
        (c.id, c.status, [s.detail for s in c.steps if s.status is Status.FAIL])
        for c in result.cases
    ]


def test_only_filter_skips_others():
    suite = load_suite(ROOT / "suites" / "kontakt-bot" / "cases.yaml")
    result = asyncio.run(run_suite(suite, dry_run=True, only={"T12-passwort-riegel"}))
    statuses = {c.id: c.status for c in result.cases}
    assert statuses["T1-neuer-kontakt-foto"] is Status.SKIP
    assert statuses["T12-passwort-riegel"] is Status.PASS
