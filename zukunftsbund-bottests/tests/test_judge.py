"""Tests für die judge-Assertion (LLM-as-Judge, Sprint 7).

Alle Szenarien laufen ohne echten LLM-Aufruf — der Judge-Provider
wird durch einfache Mock-Objekte ersetzt.
"""

from __future__ import annotations

import pytest

from adapters.base import Response
from assertions import core as a


# ---------------------------------------------------------------------------
# Hilfsobjekte / Mocks
# ---------------------------------------------------------------------------


class _MockJudge:
    """Einfacher Mock-Judge-Provider.

    Gibt das bei der Erzeugung übergebene Ergebnis zurück, unabhängig von
    Rubrik und Text. Zählt Aufrufe für Prüfzwecke.
    """

    def __init__(self, *, passes: bool, reason: str = "", cost_eur: float = 0.005) -> None:
        self._result = {"pass": passes, "reason": reason, "cost_eur": cost_eur}
        self.calls: list[tuple[str, str]] = []

    def evaluate(self, text: str, rubric: str) -> dict:
        self.calls.append((text, rubric))
        return dict(self._result)


# ---------------------------------------------------------------------------
# Tests: ohne Provider (Dry-Run-Modus)
# ---------------------------------------------------------------------------


def test_judge_ohne_provider_ueberspruengen():
    """Fehlt der Judge-Provider, gilt die Assertion als bestanden (übersprungen=ok).

    evaluate() gibt Detailtext nur bei Fehlschlag zurück. Wir rufen die
    Assertion-Funktion direkt auf, um den Hinweis-Text zu prüfen.
    """
    resp = Response(text="Beliebiger Text")
    # Prüfen via evaluate: Gesamt muss ok sein
    ok, _ = a.evaluate({"judge": {"rubric": "Brand-Voice v3", "max_cost": 0.02}}, resp, {})
    assert ok, "Sollte ohne Provider ok sein"
    # Detail direkt aus Registry prüfen (evaluate verwirft ok-Details per Design)
    fn = a._REGISTRY["judge"]
    ok_direct, detail_direct = fn({"rubric": "Brand-Voice v3", "max_cost": 0.02}, resp, {})
    assert ok_direct
    assert "übersprungen" in detail_direct


# ---------------------------------------------------------------------------
# Tests: mit Provider — pass-Pfad
# ---------------------------------------------------------------------------


def test_judge_mit_provider_pass():
    """Judge-Provider liefert pass -> Assertion besteht."""
    judge = _MockJudge(passes=True, cost_eur=0.008)
    ctx = {"judge": judge}
    resp = Response(text="Wir bauen Brücken zwischen Idee und Umsetzung.")
    ok, detail = a.evaluate({"judge": {"rubric": "Brand-Voice v3", "max_cost": 0.02}}, resp, ctx)
    assert ok, f"Erwartet pass, bekam: {detail}"
    assert len(judge.calls) == 1
    # Prüfen, ob Rubrik korrekt übergeben wurde
    _, rubric_arg = judge.calls[0]
    assert rubric_arg == "Brand-Voice v3"


# ---------------------------------------------------------------------------
# Tests: mit Provider — fail-Pfad
# ---------------------------------------------------------------------------


def test_judge_mit_provider_fail():
    """Judge-Provider liefert fail -> Assertion schlägt fehl, Begründung im Detail."""
    judge = _MockJudge(passes=False, reason="Enthält Bann-Wort 'ganzheitlich'", cost_eur=0.007)
    ctx = {"judge": judge}
    resp = Response(text="Dieser Text ist ganzheitlich ausgerichtet.")
    ok, detail = a.evaluate({"judge": {"rubric": "Brand-Voice v3", "max_cost": 0.02}}, resp, ctx)
    assert not ok, "Erwartet Fehlschlag bei judge=fail"
    assert "FAIL" in detail
    assert "Brand-Voice v3" in detail
    assert "ganzheitlich" in detail


# ---------------------------------------------------------------------------
# Tests: Budget-Cap überschritten
# ---------------------------------------------------------------------------


def test_judge_budget_cap_ueberschritten():
    """Kosten über max_cost -> Assertion schlägt fehl, auch wenn judge=pass."""
    # Kosten deutlich über dem Limit
    judge = _MockJudge(passes=True, cost_eur=0.05)
    ctx = {"judge": judge}
    resp = Response(text="Qualitativ hochwertiger Post.")
    ok, detail = a.evaluate(
        {"judge": {"rubric": "Brand-Voice v3", "max_cost": 0.02}},
        resp,
        ctx,
    )
    assert not ok, "Budget-Überschreitung muss zu Fehlschlag führen"
    assert "Budget" in detail or "budget" in detail.lower() or "überschritten" in detail.lower()
    assert "0.05" in detail or "0.0500" in detail


def test_judge_budget_cap_genau_an_grenze():
    """Kosten exakt am Limit -> Assertion besteht (Grenzwert inklusiv)."""
    judge = _MockJudge(passes=True, cost_eur=0.02)
    ctx = {"judge": judge}
    resp = Response(text="Grenzwertiger Post.")
    ok, detail = a.evaluate(
        {"judge": {"rubric": "Brand-Voice v3", "max_cost": 0.02}},
        resp,
        ctx,
    )
    # 0.02 <= 0.02 -> nicht überschritten
    assert ok, f"Genau am Limit sollte ok sein, bekam: {detail}"


def test_judge_budget_cap_knapp_darunter():
    """Kosten knapp unter dem Limit -> Assertion besteht."""
    judge = _MockJudge(passes=True, cost_eur=0.0199)
    ctx = {"judge": judge}
    resp = Response(text="Günstiger Post.")
    ok, detail = a.evaluate(
        {"judge": {"rubric": "Brand-Voice v3", "max_cost": 0.02}},
        resp,
        ctx,
    )
    assert ok, f"Knapp unter Limit sollte ok sein, bekam: {detail}"


# ---------------------------------------------------------------------------
# Tests: Rubrik-Weitergabe & default max_cost
# ---------------------------------------------------------------------------


def test_judge_rubrik_wird_weitergegeben():
    """Rubrik aus spec wird korrekt an den Provider übergeben."""
    judge = _MockJudge(passes=True, cost_eur=0.001)
    ctx = {"judge": judge}
    resp = Response(text="Test-Post.")
    a.evaluate({"judge": {"rubric": "Meine Rubrik", "max_cost": 0.05}}, resp, ctx)
    assert judge.calls[0][1] == "Meine Rubrik"


def test_judge_default_max_cost():
    """Fehlt max_cost in spec, greift der Default von 0.02 EUR."""
    # Kosten knapp über dem Default-Limit
    judge = _MockJudge(passes=True, cost_eur=0.025)
    ctx = {"judge": judge}
    resp = Response(text="Teurer Post.")
    # spec ohne max_cost -> Default 0.02
    ok, detail = a.evaluate({"judge": {"rubric": "Brand-Voice v3"}}, resp, ctx)
    assert not ok, "Default-Budget 0.02 muss greifen"
    assert "überschritten" in detail.lower() or "budget" in detail.lower() or "Budget" in detail


# ---------------------------------------------------------------------------
# Tests: Provider-Fehler
# ---------------------------------------------------------------------------


class _BrokenJudge:
    """Judge-Provider, der bei jedem Aufruf eine Exception wirft."""

    def evaluate(self, text: str, rubric: str) -> dict:
        raise RuntimeError("Verbindung zum Judge-Endpoint fehlgeschlagen")


def test_judge_provider_fehler():
    """Exception im Provider -> Assertion schlägt fehl, Fehlermeldung im Detail."""
    ctx = {"judge": _BrokenJudge()}
    resp = Response(text="Irgendein Text.")
    ok, detail = a.evaluate({"judge": {"rubric": "Brand-Voice v3", "max_cost": 0.02}}, resp, ctx)
    assert not ok, "Provider-Fehler muss zu Fehlschlag führen"
    assert "Fehler" in detail or "fehlgeschlagen" in detail.lower()
