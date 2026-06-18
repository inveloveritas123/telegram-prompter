#!/usr/bin/env python3
"""Trend-Dashboard: erzeugt ein statisches HTML aus allen reports/*.json.

Keine externen Abhängigkeiten — nur stdlib.

Verwendung:
    python scripts/trend_dashboard.py
    python scripts/trend_dashboard.py --reports-dir reports --out reports/trend.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORTS = ROOT / "reports"
DEFAULT_OUT = ROOT / "reports" / "trend.html"


def _load_reports(reports_dir: Path) -> list[dict]:
    """Liest alle *.json aus dem Verzeichnis (außer trend.json o.ä.)."""
    reports = []
    for p in sorted(reports_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data["_file"] = p.name
            reports.append(data)
        except Exception:
            continue
    return reports


def _sort_key(report: dict) -> str:
    """Sortierung nach started_at oder Dateiname."""
    return report.get("started_at") or report.get("_file", "")


def _fmt_ms(val: float | None) -> str:
    if val is None:
        return "–"
    return f"{val:.0f} ms"


def _status_color(report: dict) -> str:
    metrics = report.get("metrics", {})
    failed = metrics.get("failed", 0) or 0
    errors = metrics.get("errors", 0) or 0
    if failed + errors == 0:
        return "#22c55e"  # grün
    return "#ef4444"  # rot


def _build_html(reports: list[dict]) -> str:
    """Baut die statische HTML-Seite."""
    reports_sorted = sorted(reports, key=_sort_key)
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Daten für Trend-Graph (Laufzeit und Pass-Rate pro Lauf)
    graph_labels: list[str] = []
    graph_duration: list[float] = []
    graph_pass_rate: list[float] = []

    for r in reports_sorted:
        metrics = r.get("metrics", {})
        label = (r.get("run_id") or r.get("_file", "?"))[:16]
        graph_labels.append(label)
        graph_duration.append(round(metrics.get("total_duration_ms") or 0.0, 1))
        total = metrics.get("total") or 0
        passed = metrics.get("passed") or 0
        graph_pass_rate.append(round((passed / total * 100) if total else 0, 1))

    labels_json = json.dumps(graph_labels)
    duration_json = json.dumps(graph_duration)
    pass_rate_json = json.dumps(graph_pass_rate)

    # Tabellen-Zeilen
    rows_html = ""
    for r in reversed(reports_sorted):  # neueste zuerst
        metrics = r.get("metrics", {})
        color = _status_color(r)
        suite = r.get("suite", "?")
        run_id = r.get("run_id", "?")
        started = r.get("started_at", "")[:19] or "–"
        passed = metrics.get("passed", "?")
        total = metrics.get("total", "?")
        failed = metrics.get("failed", 0)
        errors = metrics.get("errors", 0)
        skipped = metrics.get("skipped", 0)
        dur = _fmt_ms(metrics.get("total_duration_ms"))
        avg_lat = _fmt_ms(metrics.get("avg_latency_ms"))
        max_lat = _fmt_ms(metrics.get("max_latency_ms"))
        cost = metrics.get("cost") or 0.0
        cost_str = f"${cost:.4f}" if cost > 0 else "–"
        status_dot = f'<span style="color:{color};font-size:1.2em;">●</span>'
        rows_html += (
            f"<tr>"
            f"<td>{status_dot}</td>"
            f"<td>{suite}</td>"
            f"<td><code>{run_id[:20]}</code></td>"
            f"<td>{started}</td>"
            f"<td>{passed}/{total}</td>"
            f"<td style='color:#ef4444'>{failed + errors or '–'}</td>"
            f"<td>{skipped or '–'}</td>"
            f"<td>{dur}</td>"
            f"<td>{avg_lat}</td>"
            f"<td>{max_lat}</td>"
            f"<td>{cost_str}</td>"
            f"</tr>\n"
        )

    if not rows_html:
        rows_html = "<tr><td colspan='11' style='text-align:center;color:#6b7280'>Noch keine Reports vorhanden.</td></tr>"

    html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ZUKUNFTSBUND Bot-Test Trend-Dashboard</title>
<style>
  body {{ font-family: system-ui, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:1.5rem; }}
  h1 {{ font-size:1.4rem; margin-bottom:0.25rem; }}
  .meta {{ color:#94a3b8; font-size:.85rem; margin-bottom:1.5rem; }}
  table {{ border-collapse:collapse; width:100%; font-size:.875rem; }}
  th {{ background:#1e293b; color:#94a3b8; padding:.5rem .75rem; text-align:left; }}
  td {{ padding:.45rem .75rem; border-bottom:1px solid #1e293b; }}
  tr:hover td {{ background:#1e293b55; }}
  canvas {{ max-width:100%; margin:1.5rem 0; }}
  .section {{ margin-bottom:2rem; }}
  h2 {{ font-size:1rem; color:#94a3b8; border-bottom:1px solid #334155; padding-bottom:.25rem; margin-bottom:.75rem; }}
</style>
</head>
<body>
<h1>ZUKUNFTSBUND Bot-Test Trend-Dashboard</h1>
<p class="meta">Generiert: {generated} &nbsp;|&nbsp; {len(reports_sorted)} Reports geladen</p>

<div class="section">
<h2>Verlauf (Laufzeit &amp; Pass-Rate)</h2>
<canvas id="trendChart" height="100"></canvas>
</div>

<div class="section">
<h2>Alle Läufe</h2>
<table>
<thead>
<tr>
  <th></th><th>Suite</th><th>Run-ID</th><th>Gestartet</th>
  <th>Grün</th><th>Rot</th><th>Skip</th>
  <th>Gesamt-ms</th><th>Avg-Latenz</th><th>Max-Latenz</th><th>Kosten</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>

<script>
// Minimal-Chart ohne externe Bibliothek — reines Canvas-2D
(function() {{
  const labels = {labels_json};
  const duration = {duration_json};
  const passRate = {pass_rate_json};

  const canvas = document.getElementById('trendChart');
  if (!canvas || labels.length === 0) return;
  canvas.width = canvas.parentElement.clientWidth || 800;
  canvas.height = 180;
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const pad = {{ top: 20, right: 20, bottom: 40, left: 60 }};
  const w = W - pad.left - pad.right;
  const h = H - pad.top - pad.bottom;

  function toX(i) {{ return pad.left + (labels.length < 2 ? w / 2 : i / (labels.length - 1) * w); }}

  // Hintergrund
  ctx.fillStyle = '#1e293b';
  ctx.fillRect(0, 0, W, H);

  // Gitter
  ctx.strokeStyle = '#334155';
  ctx.lineWidth = 1;
  for (let p = 0; p <= 4; p++) {{
    const y = pad.top + h - p / 4 * h;
    ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(pad.left + w, y); ctx.stroke();
  }}

  function drawLine(data, color, maxVal) {{
    if (data.length === 0) return;
    const mv = maxVal || Math.max(...data) || 1;
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    data.forEach((v, i) => {{
      const x = toX(i);
      const y = pad.top + h - (v / mv * h);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    }});
    ctx.stroke();
    // Punkte
    ctx.fillStyle = color;
    data.forEach((v, i) => {{
      const x = toX(i), y = pad.top + h - (v / mv * h);
      ctx.beginPath(); ctx.arc(x, y, 3, 0, 2 * Math.PI); ctx.fill();
    }});
  }}

  const maxDur = Math.max(...duration) || 1;
  drawLine(duration, '#38bdf8', maxDur);
  drawLine(passRate.map(v => v / 100 * maxDur), '#22c55e', maxDur);

  // Achsenbeschriftung X
  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px system-ui';
  ctx.textAlign = 'center';
  labels.forEach((l, i) => {{
    ctx.fillText(l, toX(i), H - 6);
  }});

  // Legende
  ctx.textAlign = 'left';
  ctx.fillStyle = '#38bdf8'; ctx.fillRect(pad.left, 4, 12, 8);
  ctx.fillStyle = '#e2e8f0'; ctx.fillText('Laufzeit (ms)', pad.left + 16, 12);
  ctx.fillStyle = '#22c55e'; ctx.fillRect(pad.left + 120, 4, 12, 8);
  ctx.fillStyle = '#e2e8f0'; ctx.fillText('Pass-Rate %', pad.left + 136, 12);
}})();
</script>
</body>
</html>
"""
    return html


def build_dashboard(reports_dir: Path = DEFAULT_REPORTS, out: Path = DEFAULT_OUT) -> Path:
    """Hauptfunktion: liest Reports, baut HTML, schreibt Datei."""
    reports = _load_reports(reports_dir)
    html = _build_html(reports)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Trend-Dashboard aus reports/*.json erzeugen")
    p.add_argument("--reports-dir", default=str(DEFAULT_REPORTS), help="Verzeichnis mit JSON-Reports")
    p.add_argument("--out", default=str(DEFAULT_OUT), help="Ausgabe-HTML-Datei")
    args = p.parse_args()
    out = build_dashboard(Path(args.reports_dir), Path(args.out))
    print(f"Dashboard geschrieben: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
