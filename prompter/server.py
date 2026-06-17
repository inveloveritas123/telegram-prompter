"""prompter-mcp — Test-Framework als MCP-Server (FastMCP, HTTP/streamable-http, Port 8080).

Exponiert das zukunftsbund-bottests-Framework als MCP-Tools:
    list_suites, run_suite, run_case, get_report, compare_runs

Riegel des Frameworks gelten unverändert — keine Umgehung.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import fastmcp

# Framework-Pfad ins sys.path einbinden (Container-Pfad /app/zukunftsbund-bottests,
# lokal relativ zum Repo-Wurzelverzeichnis).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_FRAMEWORK_DIR = _REPO_ROOT / "zukunftsbund-bottests"
if str(_FRAMEWORK_DIR) not in sys.path:
    sys.path.insert(0, str(_FRAMEWORK_DIR))

from runner.loader import discover_suites, load_suite
from runner.engine import run_suite as _engine_run_suite
from runner.reporter import write_json

# Konfigurierbare Verzeichnisse (via Env-Variablen, Container-Defaults).
SUITES_DIR = Path(os.environ.get("SUITES_DIR", str(_FRAMEWORK_DIR / "suites")))
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/data/reports"))

mcp = fastmcp.FastMCP("prompter-mcp")


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _suite_result_to_dict(result, report_path: Path | None = None) -> dict:
    """Wandelt ein SuiteResult in ein JSON-serialisierbares Dict um."""
    d = asdict(result)
    # Enums -> str
    for case in d["cases"]:
        case["status"] = case["status"].value if hasattr(case["status"], "value") else case["status"]
        for step in case["steps"]:
            step["status"] = step["status"].value if hasattr(step["status"], "value") else step["status"]
    return d


def _find_report_file(run_id: str) -> Path | None:
    """Sucht die Report-JSON-Datei für eine run_id unter REPORTS_DIR."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    pattern = f"*-{run_id}.json"
    matches = list(REPORTS_DIR.glob(pattern))
    if matches:
        return matches[0]
    return None


# ---------------------------------------------------------------------------
# MCP-Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_suites() -> list[str]:
    """Gibt die Namen aller verfügbaren Test-Suiten zurück."""
    suites = discover_suites(SUITES_DIR)
    return sorted(suites.keys())


@mcp.tool()
def run_suite(
    name: str,
    env: str = "staging",
    tags: Optional[list[str]] = None,
    only: Optional[list[str]] = None,
    dry_run: bool = True,
) -> dict:
    """Fährt eine Test-Suite und gibt ein kompaktes Ergebnis-Dict zurück.

    Args:
        name:     Name der Suite (muss unter SUITES_DIR existieren).
        env:      Ziel-Umgebung (default: staging — nur Test-Targets!).
        tags:     Optionale Tag-Liste — nur Fälle mit mind. einem dieser Tags.
        only:     Optionale Liste von Case-IDs — nur diese Fälle fahren.
        dry_run:  Wenn True (default) läuft die Suite im Mock-Modus ohne echte
                  Verbindungen.

    Returns:
        Dict mit run_id, suite, passed, executed, all_green, report_path.
    """
    suites = discover_suites(SUITES_DIR)
    if name not in suites:
        verfügbar = ", ".join(sorted(suites.keys())) or "(keine)"
        raise ValueError(f"Suite {name!r} nicht gefunden. Verfügbar: {verfügbar}")

    suite_obj = load_suite(suites[name])

    tags_set = set(tags) if tags else None
    only_set = set(only) if only else None

    result = asyncio.run(
        _engine_run_suite(suite_obj, dry_run=dry_run, only=only_set, tags=tags_set)
    )

    report_path = write_json(result, REPORTS_DIR)

    return {
        "run_id": result.run_id,
        "suite": result.suite,
        "passed": result.passed,
        "executed": result.executed,
        "all_green": result.all_green,
        "report_path": str(report_path),
    }


@mcp.tool()
def run_case(suite: str, case_id: str, dry_run: bool = True) -> dict:
    """Fährt einen einzelnen Testfall einer Suite.

    Intern run_suite(only={case_id}).

    Args:
        suite:    Name der Suite.
        case_id:  ID des Testfalls.
        dry_run:  Mock-Modus (default True).

    Returns:
        Dict mit run_id, suite, passed, executed, all_green, report_path.
    """
    return run_suite(suite, dry_run=dry_run, only=[case_id])


@mcp.tool()
def get_report(run_id: str) -> dict:
    """Liest den JSON-Report für eine run_id aus REPORTS_DIR.

    Args:
        run_id: Die run_id aus dem Ergebnis von run_suite/run_case.

    Returns:
        Vollständiges Report-Dict.
    """
    report_file = _find_report_file(run_id)
    if report_file is None:
        raise FileNotFoundError(
            f"Kein Report für run_id={run_id!r} in {REPORTS_DIR} gefunden."
        )
    return json.loads(report_file.read_text(encoding="utf-8"))


@mcp.tool()
def compare_runs(a: str, b: str) -> dict:
    """Vergleicht zwei Läufe und gibt Regressions- und Fixed-Diff zurück.

    Args:
        a: run_id des ersten Laufs (Referenz / alt).
        b: run_id des zweiten Laufs (neu).

    Returns:
        Dict mit 'regressions' (in b rot, in a grün) und 'fixed' (in a rot, in b grün).
    """
    report_a = get_report(a)
    report_b = get_report(b)

    # Status-Maps: case_id -> status
    status_a: dict[str, str] = {c["id"]: c["status"] for c in report_a.get("cases", [])}
    status_b: dict[str, str] = {c["id"]: c["status"] for c in report_b.get("cases", [])}

    _grün = {"pass"}
    _rot = {"fail", "error"}

    regressions: list[dict] = []
    fixed: list[dict] = []

    alle_ids = set(status_a) | set(status_b)
    for cid in sorted(alle_ids):
        sa = status_a.get(cid, "skip")
        sb = status_b.get(cid, "skip")
        if sa in _grün and sb in _rot:
            regressions.append({"case_id": cid, "status_a": sa, "status_b": sb})
        elif sa in _rot and sb in _grün:
            fixed.append({"case_id": cid, "status_a": sa, "status_b": sb})

    return {
        "run_a": a,
        "run_b": b,
        "suite_a": report_a.get("suite"),
        "suite_b": report_b.get("suite"),
        "regressions": regressions,
        "fixed": fixed,
    }


# ---------------------------------------------------------------------------
# Einstiegspunkt
# ---------------------------------------------------------------------------

def main() -> None:
    """Startet den MCP-HTTP-Server auf 0.0.0.0:8080."""
    port = int(os.environ.get("MCP_PORT", "8080"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
