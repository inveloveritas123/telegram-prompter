"""Entscheidungs-Engine — deterministisch, kein LLM.

Eine Quelle der Wahrheit für „weitermachen / fertig / anhalten".
Nachgebaut nach ralph_decide.py (ralph-Loop-Muster).

Regeln (Reihenfolge zählt):
1. Drift-Pausegate: mehr rote Fälle als in der Vorrunde → HALT.
2. Fertig: alle Fälle grün UND completion-promise vorhanden → STOP.
3. Sicherheitsnetz: iteration >= max_iterations → HALT (eskalieren).
4. Sonst → CONTINUE (mit Grund, was noch fehlt).
"""

from __future__ import annotations


def decide(
    gates_ok: bool,
    promise: bool,
    iteration: int,
    max_iter: int,
    prev_red: int = -1,
    cur_red: int = 0,
) -> tuple[str, str]:
    """Gibt (action, reason) zurück. action in {"continue", "stop", "halt"}."""
    # 1. Drift-Pausegate
    if prev_red >= 0 and cur_red > prev_red:
        return (
            "halt",
            f"Drift-Pausegate: rote Fälle gestiegen ({prev_red} → {cur_red}) — anhalten, Ursache nennen",
        )
    # 2. Fertig
    if gates_ok and promise:
        return ("stop", "GRUEN + completion-promise — fertig")
    # 3. Sicherheitsnetz
    if iteration >= max_iter:
        return (
            "halt",
            f"max-iterations ({max_iter}) erreicht ohne GRUEN+promise — eskalieren",
        )
    # 4. Weitermachen
    fehlend: list[str] = []
    if not gates_ok:
        fehlend.append("Block-Gates rot")
    if not promise:
        fehlend.append("promise fehlt")
    return ("continue", "weiterarbeiten: %s" % (", ".join(fehlend) or "unklar"))
