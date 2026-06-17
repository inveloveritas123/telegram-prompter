"""Tests für orchestrator.decide — Entscheidungslogik (ralph-Muster).

Abgedeckt:
- continue: weder grün noch promise noch Drift noch max-iter
- stop: grün + promise
- halt: Drift (cur_red > prev_red)
- halt: max-iter erreicht
- Erster Tick (prev_red=-1): kein Drift-Alarm
"""

import pytest

from orchestrator.decide import decide


class TestContinue:
    def test_gates_nok_kein_promise(self):
        action, reason = decide(
            gates_ok=False, promise=False, iteration=1, max_iter=10
        )
        assert action == "continue"
        assert "weiterarbeiten" in reason

    def test_gates_ok_kein_promise(self):
        action, reason = decide(
            gates_ok=True, promise=False, iteration=1, max_iter=10
        )
        assert action == "continue"
        assert "promise fehlt" in reason

    def test_gates_nok_promise(self):
        action, reason = decide(
            gates_ok=False, promise=True, iteration=1, max_iter=10
        )
        assert action == "continue"
        assert "Block-Gates rot" in reason


class TestStop:
    def test_gruen_und_promise(self):
        action, reason = decide(
            gates_ok=True, promise=True, iteration=1, max_iter=10
        )
        assert action == "stop"
        assert "GRUEN" in reason

    def test_gruen_und_promise_erste_iteration(self):
        action, reason = decide(
            gates_ok=True, promise=True, iteration=0, max_iter=10
        )
        assert action == "stop"


class TestHalt:
    def test_drift_pausegate(self):
        """Mehr rote als vorher → HALT."""
        action, reason = decide(
            gates_ok=False, promise=False,
            iteration=2, max_iter=10,
            prev_red=1, cur_red=3,
        )
        assert action == "halt"
        assert "Drift" in reason
        assert "1" in reason and "3" in reason

    def test_drift_bei_gleichstand_kein_halt(self):
        """Gleiche Anzahl roter → kein Drift-HALT."""
        action, _ = decide(
            gates_ok=False, promise=False,
            iteration=2, max_iter=10,
            prev_red=2, cur_red=2,
        )
        assert action == "continue"

    def test_drift_rueckgang_kein_halt(self):
        """Weniger rote als vorher → kein Drift-HALT."""
        action, _ = decide(
            gates_ok=False, promise=False,
            iteration=2, max_iter=10,
            prev_red=3, cur_red=1,
        )
        assert action != "halt"

    def test_max_iter(self):
        action, reason = decide(
            gates_ok=False, promise=False,
            iteration=10, max_iter=10,
        )
        assert action == "halt"
        assert "max-iterations" in reason

    def test_max_iter_ueberschritten(self):
        action, reason = decide(
            gates_ok=False, promise=False,
            iteration=15, max_iter=10,
        )
        assert action == "halt"

    def test_erster_tick_kein_drift(self):
        """Erster Tick: prev_red=-1 → kein Drift-Alarm, egal wie viele cur_red."""
        action, _ = decide(
            gates_ok=False, promise=False,
            iteration=1, max_iter=10,
            prev_red=-1, cur_red=99,
        )
        assert action == "continue"


class TestDriftVorMaxIter:
    def test_drift_schlaegt_maxiter(self):
        """Drift hat höhere Priorität als max-iter (Reihenfolge der Regeln)."""
        action, reason = decide(
            gates_ok=False, promise=False,
            iteration=10, max_iter=10,
            prev_red=1, cur_red=5,
        )
        assert action == "halt"
        assert "Drift" in reason
