"""Tests für orchestrator.state — STATE.md lesen und schreiben."""

from __future__ import annotations

from orchestrator import state as state_mod


class TestStateSave:
    def test_schreibt_datei(self, tmp_path):
        p = tmp_path / "STATE.md"
        state_mod.save(p, iteration=1, prev_red=0, action="continue", reason="weiterarbeiten")
        assert p.exists()

    def test_inhalt_menschenlesbar(self, tmp_path):
        p = tmp_path / "STATE.md"
        state_mod.save(
            p,
            iteration=3,
            prev_red=2,
            action="stop",
            reason="GRUEN + promise",
            run_id="abc123",
            suite="kontakt-bot",
        )
        text = p.read_text(encoding="utf-8")
        assert "iteration: 3" in text
        assert "prev_red: 2" in text
        assert "kontakt-bot" in text
        assert "abc123" in text

    def test_erstellt_elternverzeichnis(self, tmp_path):
        nested = tmp_path / "tief" / "drin" / "STATE.md"
        state_mod.save(nested, iteration=1, prev_red=-1, action="halt", reason="Fehler")
        assert nested.exists()


class TestStateLoad:
    def test_fehlt_liefert_defaults(self, tmp_path):
        p = tmp_path / "STATE.md"
        st = state_mod.load(p)
        assert st["iteration"] == 0
        assert st["prev_red"] == -1
        assert st["last_action"] is None

    def test_roundtrip(self, tmp_path):
        p = tmp_path / "STATE.md"
        state_mod.save(
            p,
            iteration=5,
            prev_red=2,
            action="continue",
            reason="Block-Gates rot",
            run_id="deadbeef",
            suite="content-autopilot",
        )
        loaded = state_mod.load(p)
        assert loaded["iteration"] == 5
        assert loaded["prev_red"] == 2
        assert loaded["last_action"] == "continue"
        assert loaded["last_suite"] == "content-autopilot"
        assert loaded["last_run_id"] == "deadbeef"

    def test_iteration_inkrementierbar(self, tmp_path):
        p = tmp_path / "STATE.md"
        state_mod.save(p, iteration=7, prev_red=0, action="continue", reason="...")
        loaded = state_mod.load(p)
        assert loaded["iteration"] == 7
        # Nächster Tick: iteration + 1 = 8
        assert loaded["iteration"] + 1 == 8
