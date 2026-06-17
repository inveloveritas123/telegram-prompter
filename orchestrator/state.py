"""STATE.md lesen und schreiben.

Format: Markdown, menschenlesbar. Der State persistiert den letzten Tick
so, dass ein Crash-Neustart genau dort weiterarbeiten kann.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

# Standard-Pfad (im Container /app/state/STATE.md, lokal überschreibbar)
DEFAULT_STATE_PATH = Path(os.environ.get("STATE_PATH", "/app/state/STATE.md"))


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def load(path: Path = DEFAULT_STATE_PATH) -> dict:
    """Liest STATE.md und gibt ein dict mit den Schlüsselwerten zurück.

    Fehlende oder leere Datei → sauberer Startzustand.
    """
    state: dict = {
        "iteration": 0,
        "prev_red": -1,
        "last_action": None,
        "last_run_id": None,
        "last_suite": None,
        "last_tick": None,
    }
    if not path.exists():
        return state
    text = path.read_text(encoding="utf-8")
    # Einfaches Schlüssel-Wert-Parsing (Zeilen der Form `- key: value`)
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("- ") and ": " in line:
            key, _, val = line[2:].partition(": ")
            key = key.strip()
            val = val.strip()
            if key in state:
                # Typen zurückkonvertieren
                if key in ("iteration",):
                    try:
                        state[key] = int(val)
                    except ValueError:
                        pass
                elif key == "prev_red":
                    try:
                        state[key] = int(val)
                    except ValueError:
                        pass
                else:
                    state[key] = val if val not in ("None", "") else None
    return state


def save(
    path: Path,
    iteration: int,
    prev_red: int,
    action: str,
    reason: str,
    run_id: str | None = None,
    suite: str | None = None,
    extra: dict | None = None,
) -> None:
    """Schreibt den aktuellen Stand in STATE.md (menschenlesbar)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    extra = extra or {}
    lines = [
        "# Orchestrator STATE",
        "",
        f"> Letzter Tick: {_now()}",
        "",
        "## Letzter Tick",
        "",
        f"- iteration: {iteration}",
        f"- prev_red: {prev_red}",
        f"- last_action: {action}",
        f"- last_suite: {suite}",
        f"- last_run_id: {run_id}",
        f"- last_tick: {_now()}",
        "",
        "## Entscheidung",
        "",
        f"**{action.upper()}** — {reason}",
        "",
    ]
    if extra:
        lines.append("## Details")
        lines.append("")
        for k, v in extra.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
