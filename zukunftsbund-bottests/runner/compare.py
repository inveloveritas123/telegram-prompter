"""Vergleich zweier JSON-Reports: Regressionen und Fixes erkennen.

Verwendung:
    from runner.compare import compare_runs
    delta = compare_runs("reports/suite-run-a.json", "reports/suite-run-b.json")
    print(delta)

Oder direkt als CLI:
    python -m runner.compare reports/suite-run-a.json reports/suite-run-b.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Union

# Latenz-Grenzwert: +50 % und mindestens +500 ms gilt als "deutlich langsamer"
_LATENCY_FACTOR = 1.5
_LATENCY_ABS_MS = 500.0


def _load(src: Union[dict, str, Path]) -> dict:
    """Lädt einen Report aus einem Dict, Pfad-String oder Path-Objekt."""
    if isinstance(src, dict):
        return src
    path = Path(src)
    return json.loads(path.read_text(encoding="utf-8"))


def compare_runs(
    report_a: Union[dict, str, Path],
    report_b: Union[dict, str, Path],
) -> dict:
    """Vergleicht zwei Suite-Reports A (alt/Basis) und B (neu/aktuell).

    Gibt ein Dict zurück mit:
        regressions   – Fälle, die in A grün waren und in B rot sind
                        ODER sich deutlich verlangsamt haben
        fixes         – Fälle, die in A rot waren und in B grün sind
        unchanged     – Fälle, die sich nicht geändert haben
        new_cases     – Fälle, die nur in B vorkommen
        removed_cases – Fälle, die nur in A vorkommen
        summary       – lesbare Zusammenfassung
    """
    a = _load(report_a)
    b = _load(report_b)

    # Indexiere nach Case-ID
    a_cases = {c["id"]: c for c in a.get("cases", [])}
    b_cases = {c["id"]: c for c in b.get("cases", [])}

    _green = {"pass"}
    _red = {"fail", "error"}

    regressions: list[dict] = []
    fixes: list[dict] = []
    unchanged: list[str] = []
    new_cases: list[str] = []
    removed_cases: list[str] = []

    for cid, cb in b_cases.items():
        if cid not in a_cases:
            new_cases.append(cid)
            continue
        ca = a_cases[cid]
        a_status = ca["status"]
        b_status = cb["status"]
        a_dur = ca.get("duration_ms", 0.0) or 0.0
        b_dur = cb.get("duration_ms", 0.0) or 0.0

        # Status-Regression: vorher grün, jetzt rot
        if a_status in _green and b_status in _red:
            regressions.append({
                "id": cid,
                "desc": cb.get("desc", ""),
                "reason": "status",
                "a_status": a_status,
                "b_status": b_status,
                "a_duration_ms": a_dur,
                "b_duration_ms": b_dur,
            })
        # Fix: vorher rot, jetzt grün
        elif a_status in _red and b_status in _green:
            fixes.append({
                "id": cid,
                "desc": cb.get("desc", ""),
                "a_status": a_status,
                "b_status": b_status,
                "a_duration_ms": a_dur,
                "b_duration_ms": b_dur,
            })
        else:
            # Latenz-Regression: beide grün, aber B deutlich langsamer
            if (
                a_status in _green
                and b_status in _green
                and a_dur > 0
                and b_dur >= a_dur * _LATENCY_FACTOR
                and (b_dur - a_dur) >= _LATENCY_ABS_MS
            ):
                regressions.append({
                    "id": cid,
                    "desc": cb.get("desc", ""),
                    "reason": "latency",
                    "a_status": a_status,
                    "b_status": b_status,
                    "a_duration_ms": a_dur,
                    "b_duration_ms": b_dur,
                    "slowdown_factor": round(b_dur / a_dur, 2),
                })
            else:
                unchanged.append(cid)

    for cid in a_cases:
        if cid not in b_cases:
            removed_cases.append(cid)

    # Metriken-Vergleich (aus metrics-Block wenn vorhanden)
    a_metrics = a.get("metrics", {})
    b_metrics = b.get("metrics", {})
    metrics_delta: dict = {}
    for key in ("total_duration_ms", "total_latency_ms", "avg_latency_ms", "cost"):
        av = a_metrics.get(key)
        bv = b_metrics.get(key)
        if av is not None and bv is not None:
            metrics_delta[key] = {"a": av, "b": bv, "delta": round(bv - av, 2)}

    # Lesbare Zusammenfassung
    lines: list[str] = [
        f"Vergleich: {a.get('suite', '?')} "
        f"A={a.get('run_id', '?')} → B={b.get('run_id', '?')}",
    ]
    if regressions:
        lines.append(f"  ❌ Regressionen ({len(regressions)}):")
        for r in regressions:
            if r["reason"] == "latency":
                lines.append(
                    f"    {r['id']}: {r['a_duration_ms']:.0f}ms → {r['b_duration_ms']:.0f}ms "
                    f"(x{r['slowdown_factor']})"
                )
            else:
                lines.append(f"    {r['id']}: {r['a_status']} → {r['b_status']}")
    if fixes:
        lines.append(f"  ✅ Fixes ({len(fixes)}):")
        for f_ in fixes:
            lines.append(f"    {f_['id']}: {f_['a_status']} → {f_['b_status']}")
    if not regressions and not fixes:
        lines.append("  Keine Änderungen gegenüber dem Basis-Report.")
    if new_cases:
        lines.append(f"  Neu: {', '.join(new_cases)}")
    if removed_cases:
        lines.append(f"  Entfernt: {', '.join(removed_cases)}")

    return {
        "suite_a": a.get("suite"),
        "suite_b": b.get("suite"),
        "run_id_a": a.get("run_id"),
        "run_id_b": b.get("run_id"),
        "regressions": regressions,
        "fixes": fixes,
        "unchanged": unchanged,
        "new_cases": new_cases,
        "removed_cases": removed_cases,
        "metrics_delta": metrics_delta,
        "summary": "\n".join(lines),
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Verwendung: python -m runner.compare <report_a.json> <report_b.json>")
        sys.exit(1)
    result = compare_runs(sys.argv[1], sys.argv[2])
    print(result["summary"])
    if result["regressions"]:
        sys.exit(1)
