"""Tests für den vollständigen Mock-Zyklus.

Verifiziert:
- MockEngine liefert success=True und promise=True (ab Iteration 1)
- MockMcpClient liefert all_green=True
- run_tick(dry_run=True) läuft durch und endet mit 0 (stop oder continue)
- STATE.md wird korrekt geschrieben
"""

from __future__ import annotations

from orchestrator.decide import decide
from orchestrator.engine import MockEngine
from orchestrator.mcp_client import MockMcpClient


class TestMockEngine:
    def test_build_success(self):
        eng = MockEngine()
        result = eng.build("Test-Ziel", {"iteration": 1})
        assert result.success is True

    def test_build_promise(self):
        """Ab Iteration 1 muss promise=True sein."""
        eng = MockEngine()
        result = eng.build("Ziel", {"iteration": 1})
        assert result.promise is True

    def test_build_summary_nicht_leer(self):
        eng = MockEngine()
        result = eng.build("Irgendwas", {"iteration": 1})
        assert result.summary

    def test_build_zaehlt_aufrufe(self):
        eng = MockEngine()
        eng.build("Z1", {"iteration": 1})
        eng.build("Z2", {"iteration": 2})
        assert eng._call_count == 2


class TestMockMcpClient:
    def test_list_suites(self):
        client = MockMcpClient()
        suites = client.list_suites()
        assert isinstance(suites, list)
        assert len(suites) > 0

    def test_run_suite_all_green(self):
        client = MockMcpClient()
        result = client.run_suite("kontakt-bot", dry_run=True)
        assert result.all_green is True
        assert result.executed > 0
        assert result.passed == result.executed

    def test_run_suite_hat_run_id(self):
        client = MockMcpClient()
        result = client.run_suite("kontakt-bot", dry_run=True)
        assert result.run_id
        assert len(result.run_id) == 12

    def test_run_case(self):
        client = MockMcpClient()
        result = client.run_case("kontakt-bot", "T1-init", dry_run=True)
        assert result.all_green is True

    def test_get_report(self):
        client = MockMcpClient()
        result = client.run_suite("kontakt-bot", dry_run=True)
        report = client.get_report(result.run_id)
        assert report.get("all_green") is True


class TestMockZyklusGreenPath:
    """MockEngine + MockMcpClient → grüner Zyklus → decide→stop."""

    def test_entscheidung_stop_mit_mock(self):
        eng = MockEngine()
        mcp = MockMcpClient()

        build = eng.build("Ziel", {"iteration": 1})
        run = mcp.run_suite("kontakt-bot", dry_run=True)

        cur_red = run.executed - run.passed
        action, reason = decide(
            gates_ok=run.all_green,
            promise=build.promise,
            iteration=1,
            max_iter=10,
            prev_red=-1,
            cur_red=cur_red,
        )
        assert action == "stop", f"Erwartete 'stop', erhielt '{action}': {reason}"


class TestRunTick:
    """Integrations-Test: run_tick(dry_run=True) durchläuft vollständig."""

    def test_tick_dry_run_exitcode(self, tmp_path):
        """Tick mit Dry-Run muss 0 zurückgeben (stop oder continue, kein Crash)."""
        state_path = tmp_path / "STATE.md"
        config_path = tmp_path / "pipeline.yml"

        # Minimale pipeline.yml
        config_path.write_text(
            "goals:\n"
            "  - id: test-ziel\n"
            "    suite: kontakt-bot\n"
            "    acceptance: Gruen\n"
            "    tags: []\n"
            "budget:\n"
            "  max_iterations: 10\n"
            "flaky_retries: 2\n",
            encoding="utf-8",
        )

        import orchestrator.budget as budget_mod
        import orchestrator.state as state_mod

        orig_state = state_mod.DEFAULT_STATE_PATH
        orig_config = budget_mod.CONFIG_PATH

        state_mod.DEFAULT_STATE_PATH = state_path
        budget_mod.CONFIG_PATH = config_path

        # Überschreibe die Modul-Pfade im run-Modul ebenfalls
        import orchestrator.run as run_mod

        orig_run_state = run_mod._STATE_PATH
        orig_run_config = run_mod._CONFIG_PATH

        run_mod._STATE_PATH = state_path
        run_mod._CONFIG_PATH = config_path

        try:
            code = run_mod.run_tick(dry_run=True)
        finally:
            state_mod.DEFAULT_STATE_PATH = orig_state
            budget_mod.CONFIG_PATH = orig_config
            run_mod._STATE_PATH = orig_run_state
            run_mod._CONFIG_PATH = orig_run_config

        assert code in (0, 3), f"Unerwarteter Exit-Code: {code}"

    def test_tick_schreibt_state(self, tmp_path):
        """Nach einem Tick muss STATE.md existieren."""
        state_path = tmp_path / "STATE.md"
        config_path = tmp_path / "pipeline.yml"

        config_path.write_text(
            "goals:\n"
            "  - id: test-ziel\n"
            "    suite: kontakt-bot\n"
            "    acceptance: Gruen\n"
            "    tags: []\n"
            "budget:\n"
            "  max_iterations: 10\n"
            "flaky_retries: 2\n",
            encoding="utf-8",
        )

        import orchestrator.budget as budget_mod
        import orchestrator.run as run_mod
        import orchestrator.state as state_mod

        state_mod.DEFAULT_STATE_PATH = state_path
        budget_mod.CONFIG_PATH = config_path
        run_mod._STATE_PATH = state_path
        run_mod._CONFIG_PATH = config_path

        try:
            run_mod.run_tick(dry_run=True)
        finally:
            pass  # Pfade bleiben für diesen Test

        assert state_path.exists(), "STATE.md wurde nicht geschrieben"
        content = state_path.read_text(encoding="utf-8")
        assert "iteration" in content
        assert (
            "action" in content or "STOP" in content or "CONTINUE" in content or "HALT" in content
        )
