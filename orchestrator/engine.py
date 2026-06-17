"""Engine-Abstraktion — Interface + zwei Implementierungen.

AgentEngine.build(goal, context) -> BuildResult

MockEngine (ORCHESTRATOR_ENGINE=mock oder --dry-run):
    Simuliert einen Bau-Schritt ohne echten Claude.
    Gibt einen plausiblen BuildResult zurück, sodass der vollständige
    Dry-Run-Zyklus (bauen → testen → report → PR-Sim) durchläuft.

ClaudeCodeEngine (ORCHESTRATOR_ENGINE=claude):
    Ruft `claude -p "<task>" --output-format json` als Subprozess.
    Auth über gemountetes ~/.claude — kein API-Key nötig.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field


@dataclass
class BuildResult:
    """Ergebnis eines Bau-Schritts."""

    success: bool
    summary: str                      # Kurzbeschreibung was gebaut/geändert wurde
    changed_files: list[str] = field(default_factory=list)
    promise: bool = False             # Hat der Worker das completion-promise ausgegeben?
    raw_output: str = ""              # Rohausgabe des Workers (für Debugging)


class AgentEngine:
    """Basisklasse / Interface für Bau-Engines."""

    def build(self, goal: str, context: dict) -> BuildResult:  # pragma: no cover
        raise NotImplementedError


class MockEngine(AgentEngine):
    """Mock-Engine für Dry-Runs und Tests.

    Simuliert einen erfolgreichen Bau-Schritt ohne externe Aufrufe.
    Nach der ersten Runde wird `promise=True` gesetzt, damit ein einzelner
    Tick vollständig (continue → stop) durchläuft.
    """

    def __init__(self) -> None:
        self._call_count = 0

    def build(self, goal: str, context: dict) -> BuildResult:
        self._call_count += 1
        iteration = context.get("iteration", 1)
        # Ab Iteration 1 liefert der Mock einen promise (alles grün simuliert).
        promise = iteration >= 1
        return BuildResult(
            success=True,
            summary=f"[Mock] Bau-Schritt {self._call_count}: Ziel '{goal}' simuliert.",
            changed_files=["orchestrator/run.py"],
            promise=promise,
            raw_output="<promise>GRUEN</promise>\n[Mock] Keine echten Änderungen.",
        )


class ClaudeCodeEngine(AgentEngine):
    """Echte Engine via `claude -p` CLI.

    Voraussetzung: claude CLI installiert, ~/.claude gemountet (read-only).
    Auth erfolgt über das Host-claude-Verzeichnis — kein API-Key im Container.
    """

    def __init__(self, timeout: int = 300) -> None:
        self._timeout = timeout

    def build(self, goal: str, context: dict) -> BuildResult:  # pragma: no cover
        task = (
            f"{goal}\n\n"
            f"Kontext: {json.dumps(context, ensure_ascii=False)}\n\n"
            "Wenn fertig: gib exakt <promise>GRUEN</promise> aus."
        )
        try:
            proc = subprocess.run(
                ["claude", "-p", task, "--output-format", "json"],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError:
            return BuildResult(
                success=False,
                summary="claude CLI nicht gefunden — ORCHESTRATOR_ENGINE=claude erfordert claude im PATH.",
                raw_output="",
            )
        except subprocess.TimeoutExpired:
            return BuildResult(
                success=False,
                summary=f"claude CLI-Aufruf nach {self._timeout}s abgebrochen.",
                raw_output="",
            )

        raw = proc.stdout or ""
        # Versuche JSON zu parsen (--output-format json liefert strukturierte Ausgabe).
        summary = raw[:500]
        try:
            data = json.loads(raw)
            summary = data.get("result", data.get("content", raw))[:500]
        except (json.JSONDecodeError, KeyError):
            pass

        promise = "<promise>GRUEN</promise>" in raw
        success = proc.returncode == 0

        return BuildResult(
            success=success,
            summary=summary,
            changed_files=[],   # claude CLI gibt keine Dateiliste zurück
            promise=promise,
            raw_output=raw,
        )


def create_engine(dry_run: bool = False) -> AgentEngine:
    """Fabrik — wählt Engine anhand von Env/Flag."""
    engine_name = os.environ.get("ORCHESTRATOR_ENGINE", "mock").lower()
    if dry_run or engine_name == "mock":
        return MockEngine()
    if engine_name == "claude":
        return ClaudeCodeEngine()
    raise ValueError(
        f"Unbekannte Engine: {engine_name!r}. Gültig: mock | claude"
    )
