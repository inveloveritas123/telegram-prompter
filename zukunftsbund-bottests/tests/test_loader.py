"""Unit-Tests für Loader und Assertions — laufen ohne Netzwerk/Telegram."""

from pathlib import Path

import pytest

from adapters.base import Response
from assertions import core as a
from runner.loader import discover_suites, load_suite
from runner.models import StepKind

ROOT = Path(__file__).resolve().parent.parent
SUITES = ROOT / "suites"


def test_discover_finds_suites():
    suites = discover_suites(SUITES)
    assert "kontakt-bot" in suites
    assert "content-autopilot" in suites


def test_load_kontakt_bot():
    suite = load_suite(SUITES / "kontakt-bot" / "cases.yaml")
    assert suite.name == "kontakt-bot"
    assert suite.target.adapter == "telegram"
    ids = [c.id for c in suite.cases]
    assert "T1-neuer-kontakt-foto" in ids
    first = suite.cases[0]
    assert first.steps[0].kind is StepKind.SEND_PHOTO


def test_env_substitution(monkeypatch, tmp_path):
    monkeypatch.setenv("TEST_PASSWORT", "s3cret")
    yaml_text = (
        "suite: x\n"
        "target: { adapter: http, base_url: http://localhost }\n"
        "cases:\n"
        "  - id: c1\n"
        "    steps:\n"
        "      - send: '{{ env.TEST_PASSWORT }}'\n"
    )
    p = tmp_path / "cases.yaml"
    p.write_text(yaml_text)
    suite = load_suite(p)
    assert suite.cases[0].steps[0].payload == "s3cret"


def test_assertions_contains_and_regex():
    resp = Response(text="Neu gespeichert: #42")
    ok, _ = a.evaluate({"contains": "gespeichert"}, resp, {})
    assert ok
    ok, _ = a.evaluate({"regex": r"#\d+"}, resp, {})
    assert ok
    ok, detail = a.evaluate({"contains": "fehlt"}, resp, {})
    assert not ok and "erwartet" in detail


def test_assertion_latency():
    resp = Response(text="ok", latency_ms=1500)
    ok, _ = a.evaluate({"latency_below": "2s"}, resp, {})
    assert ok
    ok, _ = a.evaluate({"latency_below": "1s"}, resp, {})
    assert not ok


def test_unknown_assertion():
    ok, detail = a.evaluate({"nope": 1}, Response(text=""), {})
    assert not ok and "Unbekannte" in detail
