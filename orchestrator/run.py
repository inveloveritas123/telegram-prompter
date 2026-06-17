"""orchestrator.run — cron-getriebener Tick.

CLI:
    python -m orchestrator.run tick             # eine Runde (echte Engine)
    python -m orchestrator.run tick --dry-run   # erzwingt MockEngine

Ein Tick = eine begrenzte Runde:
  1. Budget/Kill-Switch prüfen.
  2. Ziel aus pipeline.yml lesen.
  3. Bauen (Engine).
  4. Testen (prompter-mcp → run_suite).
  5. Report lesen.
  6. Rot → fixen + gezielt re-testen (1–2× Flaky-Retry).
  7. Grün → Branch-Commit + PR (ohne GITHUB_TOKEN simuliert).
  8. STATE schreiben, sauber raus.

Entscheidung continue|stop|halt deterministisch via orchestrator.decide.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Pfade
_REPO_ROOT = Path(__file__).resolve().parent.parent

# State- und Report-Pfade: Env-Variable hat Vorrang.
# Fallback: innerhalb des Repos (lokal / außerhalb Docker).
def _resolve_path(env_var: str, docker_default: str, local_fallback: Path) -> Path:
    """Gibt den Pfad aus Env zurück; wenn das Env-Default nicht beschreibbar ist,
    weicht es auf den lokalen Fallback aus."""
    from_env = os.environ.get(env_var)
    if from_env:
        return Path(from_env)
    candidate = Path(docker_default)
    # Prüfe, ob der Elternpfad existiert (z. B. /app im Container angelegt).
    if candidate.parent.exists() or candidate.parent.parent.exists():
        return candidate
    return local_fallback


_CONFIG_PATH = _REPO_ROOT / "config" / "pipeline.yml"
_STATE_PATH = _resolve_path(
    "STATE_PATH", "/app/state/STATE.md", _REPO_ROOT / "app" / "state" / "STATE.md"
)
_REPORTS_DIR = _resolve_path(
    "REPORTS_DIR", "/data/reports", _REPO_ROOT / "app" / "reports"
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Orchestrator — cron-Tick")
    sub = p.add_subparsers(dest="command")
    tick = sub.add_parser("tick", help="Eine Runde fahren")
    tick.add_argument(
        "--dry-run",
        action="store_true",
        help="Mock-Engine erzwingen (kein echter Claude, kein echter MCP)",
    )
    return p.parse_args(argv)


def _print(msg: str) -> None:
    """Einheitliche Log-Ausgabe."""
    print(msg, flush=True)


def _simulate_pr(goal_id: str, run_id: str, dry_run: bool) -> str:
    """Branch-Commit + PR.

    Mit GITHUB_TOKEN: echter PR (nicht implementiert — Platzhalter).
    Ohne Token oder im Dry-Run: simulierter PR (Ausgabe).
    Kein Selbst-Merge (BUILD-CONTRACT §Leitplanken).
    """
    token = os.environ.get("GITHUB_TOKEN", "")
    if dry_run or not token:
        pr_ref = f"[SIM] PR: feat/orchestrator-{goal_id}-{run_id[:6]}"
        _print(f"   PR simuliert (kein GITHUB_TOKEN): {pr_ref}")
        return pr_ref
    # Echter PR-Flow (zukünftig via gh CLI oder PyGitHub)
    _print("   GITHUB_TOKEN vorhanden — echter PR-Flow noch nicht implementiert.")
    return f"[STUB] PR für {goal_id}"


def run_tick(dry_run: bool = False) -> int:
    """Führt einen vollständigen Tick aus. Gibt Exit-Code zurück (0/1/3)."""
    from orchestrator.budget import check_budget, load_pipeline_config
    from orchestrator.decide import decide
    from orchestrator.engine import create_engine
    from orchestrator.mcp_client import create_client
    from orchestrator import state as state_mod

    _print("── Orchestrator Tick ────────────────────────────────")
    _print(f"   dry-run={dry_run}  engine={'mock' if dry_run else os.environ.get('ORCHESTRATOR_ENGINE','mock')}")

    # --- 1. STATE laden ---
    st = state_mod.load(_STATE_PATH)
    iteration = st["iteration"] + 1
    prev_red = st["prev_red"]
    _print(f"   iteration={iteration}  prev_red={prev_red}")

    # --- 2. Pipeline-Konfiguration ---
    config = load_pipeline_config(_CONFIG_PATH)
    if not config:
        _print("WARNUNG: config/pipeline.yml fehlt oder leer — Defaults.")
    budget = config.get("budget", {})
    max_iter = budget.get("max_iterations", 10)
    flaky_retries = config.get("flaky_retries", 2)

    # --- 3. Budget-/Kill-Switch prüfen ---
    ok, reason = check_budget(config, iteration)
    if not ok:
        _print(f"⛔ {reason}")
        state_mod.save(
            _STATE_PATH, iteration=iteration, prev_red=prev_red,
            action="halt", reason=reason,
        )
        return 3

    # --- 4. Ziel lesen ---
    goals = config.get("goals", [])
    if not goals:
        _print("⛔ Keine Ziele in pipeline.yml — HALT")
        state_mod.save(
            _STATE_PATH, iteration=iteration, prev_red=prev_red,
            action="halt", reason="Keine Ziele konfiguriert",
        )
        return 3
    goal = goals[0]   # Erstmal nur das erste Ziel (erweiterbar)
    goal_id = goal.get("id", "unbekannt")
    suite_name = goal.get("suite", "kontakt-bot")
    goal_tags = goal.get("tags") or []
    _print(f"   Ziel: {goal_id}  Suite: {suite_name}")

    # --- 5. Bauen (Engine) ---
    engine = create_engine(dry_run=dry_run)
    _print(f"   Engine: {type(engine).__name__}")
    build_ctx = {
        "iteration": iteration,
        "goal_id": goal_id,
        "suite": suite_name,
        "dry_run": dry_run,
    }
    t0 = time.monotonic()
    build_result = engine.build(goal=goal.get("acceptance", goal_id), context=build_ctx)
    build_s = time.monotonic() - t0
    _print(f"   Build: success={build_result.success}  promise={build_result.promise}  ({build_s:.1f}s)")
    _print(f"   Build-Summary: {build_result.summary}")

    if not build_result.success:
        _print("⛔ Build fehlgeschlagen — HALT")
        state_mod.save(
            _STATE_PATH, iteration=iteration, prev_red=prev_red,
            action="halt", reason=f"Build fehlgeschlagen: {build_result.summary}",
            suite=suite_name,
        )
        return 3

    # --- 6. Testen (prompter-mcp) ---
    mcp = create_client(dry_run=dry_run)
    _print(f"   MCP-Client: {type(mcp).__name__}")

    run_result = mcp.run_suite(
        suite_name,
        env="staging",
        tags=goal_tags or None,
        dry_run=dry_run,
    )
    _print(
        f"   Suite-Lauf: run_id={run_result.run_id}  "
        f"{run_result.passed}/{run_result.executed} grün  all_green={run_result.all_green}"
    )

    cur_red = run_result.executed - run_result.passed
    red_cases = run_result.red_cases

    # --- 7. Flaky-Retry bei roten Fällen ---
    if not run_result.all_green and red_cases:
        _print(f"   Rote Fälle: {red_cases} — Flaky-Retry (max {flaky_retries}×)")
        for attempt in range(1, flaky_retries + 1):
            _print(f"   Re-Test Versuch {attempt}/{flaky_retries}...")
            retry_results = []
            for case_id in red_cases:
                r = mcp.run_case(suite_name, case_id, dry_run=dry_run)
                retry_results.append(r)
                _print(f"     {case_id}: all_green={r.all_green}")
            still_red = [
                rid for r, rid in zip(retry_results, red_cases) if not r.all_green
            ]
            if not still_red:
                _print("   Nach Retry alle Fälle grün.")
                cur_red = 0
                run_result = mcp.run_suite(suite_name, env="staging", dry_run=dry_run)
                break
            red_cases = still_red
            cur_red = len(still_red)
        else:
            _print(f"   Flaky-Retries erschöpft. Noch rot: {red_cases}")

    # --- 8. Report lesen ---
    report = mcp.get_report(run_result.run_id)
    _print(f"   Report: {report.get('run_id', '?')}  all_green={report.get('all_green')}")

    # --- 9. Entscheidung (ralph-Muster) ---
    gates_ok = run_result.all_green
    promise = build_result.promise
    action, reason = decide(
        gates_ok=gates_ok,
        promise=promise,
        iteration=iteration,
        max_iter=max_iter,
        prev_red=prev_red,
        cur_red=cur_red,
    )
    _print(f"   gates_ok={gates_ok}  promise={promise}  cur_red={cur_red}  → {action}: {reason}")

    # --- 10. Bei Grün: PR ---
    pr_ref = None
    if action == "stop":
        pr_ref = _simulate_pr(goal_id, run_result.run_id, dry_run)

    # --- 11. STATE schreiben ---
    state_mod.save(
        _STATE_PATH,
        iteration=iteration,
        prev_red=cur_red if action == "continue" else prev_red,
        action=action,
        reason=reason,
        run_id=run_result.run_id,
        suite=suite_name,
        extra={
            "goal_id": goal_id,
            "passed": run_result.passed,
            "executed": run_result.executed,
            "cur_red": cur_red,
            "pr_ref": pr_ref or "(kein PR)",
            "build_summary": build_result.summary[:200],
        },
    )
    _print(f"   STATE geschrieben: {_STATE_PATH}")

    # --- Ausgabe / Exit ---
    if action == "stop":
        _print(f"✅ {reason}")
        return 0
    elif action == "halt":
        _print(f"⛔ {reason}")
        return 3
    else:
        _print(f"▶ {reason}")
        return 0   # continue → nächster cron-Tick


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.command == "tick":
        return run_tick(dry_run=args.dry_run)
    _parse_args(["--help"])
    return 2


if __name__ == "__main__":
    sys.exit(main())
