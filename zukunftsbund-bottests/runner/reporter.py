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
    # Latenz-Zusammenfassung
    avg = result.avg_latency_ms
    if avg is not None:
        lines.append(
            f"Latenz:  gesamt={result.total_latency_ms:.0f}ms  "
            f"avg={avg:.0f}ms  max={result.max_latency_ms:.0f}ms"
        )
    elif result.total_duration_ms > 0:
        lines.append(f"Laufzeit: {result.total_duration_ms:.0f}ms (keine Step-Latenz erfasst)")
    if result.cost > 0.0:
        lines.append(f"Kosten:  ${result.cost:.4f}")
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
    # Aggregat-Metriken additiv einbetten (neue Felder, rückwärtskompatibel)
    d["metrics"] = {
        "total_duration_ms": result.total_duration_ms,
        "total_latency_ms": result.total_latency_ms,
        "avg_latency_ms": result.avg_latency_ms,
        "max_latency_ms": result.max_latency_ms,
        "cost": result.cost,
        "passed": result.passed,
        "failed": sum(1 for c in result.cases if c.status is Status.FAIL),
        "errors": sum(1 for c in result.cases if c.status is Status.ERROR),
        "skipped": result.skipped,
        "total": result.total,
    }
    return d
