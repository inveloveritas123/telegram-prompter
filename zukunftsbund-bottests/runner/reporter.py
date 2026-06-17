"""Schicht 4: Reporting — Konsole, JSON, optional Telegram.

Macht aus einem SuiteResult einen lesbaren Konsolen-Report mit Diffs, ein
JSON-Artefakt für CI/MCP und eine kurze Zusammenfassung für Telegram.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from runner.models import Status, SuiteResult

_GLYPH = {
    Status.PASS: "✅",
    Status.FAIL: "❌",
    Status.ERROR: "💥",
    Status.SKIP: "⏭️",
}


def console_report(result: SuiteResult) -> str:
    lines: list[str] = []
    lines.append(f"Suite: {result.suite}   run={result.run_id}")
    lines.append("─" * 56)
    for c in result.cases:
        lines.append(f"{_GLYPH[c.status]}  {c.id}  ({c.duration_ms:.0f}ms)  {c.desc}")
        if c.status is Status.FAIL:
            for s in c.steps:
                if s.status is Status.FAIL and s.detail:
                    lines.append(f"      ↳ {s.kind}: {s.detail}")
        if c.status is Status.ERROR and c.error:
            lines.append(f"      ↳ Fehler: {c.error}")
    lines.append("─" * 56)
    tail = f"  ({result.skipped} übersprungen)" if result.skipped else ""
    lines.append(f"Ergebnis: {result.passed}/{result.executed} grün{tail}")
    return "\n".join(lines)


def write_json(result: SuiteResult, reports_dir: str | Path) -> Path:
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    out = reports_dir / f"{result.suite}-{result.run_id}.json"
    out.write_text(json.dumps(_serialize(result), ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def telegram_summary(result: SuiteResult) -> str:
    """Kurze Nachricht, die der Runner dir nach dem Lauf schicken kann."""
    head = "🟢" if result.all_green else "🔴"
    reds = [c.id for c in result.cases if c.status in (Status.FAIL, Status.ERROR)]
    msg = f"{head} Suite {result.suite}: {result.passed}/{result.executed} grün"
    if result.skipped:
        msg += f" ({result.skipped} übersprungen)"
    if reds:
        msg += f" — rot: {', '.join(reds)}"
    return msg


def _serialize(result: SuiteResult) -> dict:
    d = asdict(result)
    # Enums -> str
    for case in d["cases"]:
        case["status"] = case["status"].value if hasattr(case["status"], "value") else case["status"]
        for step in case["steps"]:
            step["status"] = step["status"].value if hasattr(step["status"], "value") else step["status"]
    return d
