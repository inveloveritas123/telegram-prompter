"""Budget- und Kill-Switch-Prüfung.

Liest pipeline.yml und optional budget.json (Laufzeit-Zähler) und entscheidet,
ob der aktuelle Tick weiterlaufen darf oder gestoppt werden muss.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import yaml

CONFIG_PATH = Path(os.environ.get("PIPELINE_CONFIG", "/app/config/pipeline.yml"))


def load_pipeline_config(config_path: Path = CONFIG_PATH) -> dict:
    """Liest pipeline.yml. Gibt leeres dict zurück, wenn Datei fehlt."""
    if not config_path.exists():
        return {}
    with config_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def check_budget(config: dict, iteration: int) -> tuple[bool, str]:
    """Prüft ob Budget/Kill-Switch überschritten ist.

    Gibt (ok, reason) zurück.
    ok=True → Tick darf weiterlaufen.
    ok=False → Tick muss sofort stoppen (reason enthält den Grund).
    """
    budget = config.get("budget", {})
    max_iter = budget.get("max_iterations", 10)
    if iteration >= max_iter:
        return (
            False,
            f"Budget-Kill-Switch: iteration {iteration} >= max_iterations {max_iter}",
        )
    return (True, "Budget ok")


def check_time_window(config: dict) -> tuple[bool, str]:
    """Prüft ob der aktuelle Zeitpunkt im erlaubten Nacht-Fenster liegt.

    Gibt (ok, reason) zurück. Wenn kein Fenster konfiguriert → immer ok.
    """
    schedule = config.get("schedule", {})
    window = schedule.get("window")
    if not window:
        return (True, "Kein Zeitfenster konfiguriert — immer erlaubt")

    # Fenster als "HH:MM-HH:MM"
    if isinstance(window, str) and "-" in window:
        try:
            start_s, end_s = window.split("-", 1)
            now = datetime.now(UTC)
            sh, sm = int(start_s.split(":")[0]), int(start_s.split(":")[1])
            eh, em = int(end_s.split(":")[0]), int(end_s.split(":")[1])
            start_min = sh * 60 + sm
            end_min = eh * 60 + em
            cur_min = now.hour * 60 + now.minute
            # Fenster über Mitternacht: z.B. 23:00-03:00
            if start_min <= end_min:
                ok = start_min <= cur_min <= end_min
            else:
                ok = cur_min >= start_min or cur_min <= end_min
            if not ok:
                return (
                    False,
                    f"Außerhalb des Nacht-Fensters ({window}, jetzt {now.strftime('%H:%M')} UTC)",
                )
            return (True, f"Im Nacht-Fenster ({window})")
        except (ValueError, IndexError):
            pass
    return (True, "Zeitfenster-Format unbekannt — Tick erlaubt")
