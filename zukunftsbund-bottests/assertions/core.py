"""Schicht 3: Assertions — das *Wogegen*.

Sie machen aus „lief durch" ein „lief *richtig* durch". Jede Assertion bekommt
die Antwort (Text + Kontext) und gibt (ok, detail) zurück. detail beschreibt
bei Fehlschlag den Diff für den Report.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from adapters.base import Response

# Signatur: (spec, response, context) -> (ok, detail)
AssertionFn = Callable[[Any, Response, dict], tuple[bool, str]]

_REGISTRY: dict[str, AssertionFn] = {}


def assertion(name: str) -> Callable[[AssertionFn], AssertionFn]:
    def deco(fn: AssertionFn) -> AssertionFn:
        _REGISTRY[name] = fn
        return fn

    return deco


def evaluate(spec: dict[str, Any], response: Response, context: dict) -> tuple[bool, str]:
    """Wertet ein expect-/assert-Dict aus.

    Beispiel-spec: {"contains": "Erkannt"} oder
    {"regex": "Neu gespeichert: #\\d+"} oder {"latency_below": "2s"}.
    Mehrere Schlüssel = UND-Verknüpfung.
    """
    if not isinstance(spec, dict):
        return False, f"Assertion-Spec ist kein Dict: {spec!r}"
    results: list[str] = []
    ok_all = True
    for key, value in spec.items():
        fn = _REGISTRY.get(key)
        if fn is None:
            return False, f"Unbekannte Assertion {key!r}. Bekannt: {', '.join(sorted(_REGISTRY))}"
        ok, detail = fn(value, response, context)
        ok_all = ok_all and ok
        if not ok:
            results.append(detail)
    return ok_all, "; ".join(results)


# --- Text-Assertions ---


@assertion("contains")
def _contains(value: str, resp: Response, ctx: dict) -> tuple[bool, str]:
    ok = str(value) in resp.text
    return ok, "" if ok else f"erwartet enthält {value!r}, bekam: {_clip(resp.text)}"


@assertion("not_contains")
def _not_contains(value: str, resp: Response, ctx: dict) -> tuple[bool, str]:
    ok = str(value) not in resp.text
    return ok, "" if ok else f"sollte {value!r} NICHT enthalten, bekam: {_clip(resp.text)}"


@assertion("equals")
def _equals(value: str, resp: Response, ctx: dict) -> tuple[bool, str]:
    ok = resp.text.strip() == str(value).strip()
    return ok, "" if ok else f"erwartet: {value!r}, bekam: {_clip(resp.text)}"


@assertion("regex")
def _regex(value: str, resp: Response, ctx: dict) -> tuple[bool, str]:
    ok = re.search(str(value), resp.text) is not None
    return ok, "" if ok else f"Regex {value!r} matcht nicht: {_clip(resp.text)}"


# --- Metrik-Assertions ---


@assertion("latency_below")
def _latency_below(value: str, resp: Response, ctx: dict) -> tuple[bool, str]:
    limit_ms = _parse_duration_ms(value)
    ok = resp.latency_ms <= limit_ms
    return ok, "" if ok else f"Latenz {resp.latency_ms:.0f}ms > Limit {limit_ms:.0f}ms"


# --- Zustands-Assertions (Test-Sheet / n8n) ---


@assertion("sheet_row")
def _sheet_row(value: dict, resp: Response, ctx: dict) -> tuple[bool, str]:
    """Prüft erwartete Spaltenwerte der letzten Zeile im (Test-)Sheet.

    Erwartet einen Sheet-Provider in context["sheet"] mit Methode
    last_row(tab) -> dict. Ohne Provider (Dry-Run) wird übersprungen=ok.
    """
    provider = ctx.get("sheet")
    if provider is None:
        return True, "(sheet-Provider fehlt — übersprungen)"
    tab = value.get("tab")
    expected = value.get("last_row", value)
    row = provider.last_row(tab)
    diffs = [f"{k}: erwartet {v!r}, bekam {row.get(k)!r}" for k, v in expected.items() if row.get(k) != v]
    return (not diffs), "; ".join(diffs)


@assertion("n8n_execution_ok")
def _n8n_ok(value: Any, resp: Response, ctx: dict) -> tuple[bool, str]:
    client = ctx.get("n8n")
    if client is None:
        return True, "(n8n-Client fehlt — übersprungen)"
    workflow_id = value if isinstance(value, str) else value.get("workflow_id")
    ok = client.last_execution_ok(workflow_id)
    return ok, "" if ok else f"n8n-Workflow {workflow_id} lief NICHT grün"


# --- LLM-as-Judge ---


@assertion("judge")
def _judge(spec: dict, resp: Response, ctx: dict) -> tuple[bool, str]:
    """LLM-as-Judge: Bewertet eine Antwort anhand einer Rubrik.

    Erwartet einen Judge-Provider in context["judge"] mit Methode
    evaluate(text, rubric) -> {"pass": bool, "reason": str, "cost_eur": float}.

    spec-Felder:
        rubric   – Name/Beschreibung der Bewertungsrubrik (z. B. "Brand-Voice v3")
        max_cost – Budget-Grenze in EUR pro Aufruf (Default 0.02)

    Ohne Provider (Dry-Run): übersprungen=ok.
    Budget-Überschreitung: Fehler mit Kostendetail.
    """
    provider = ctx.get("judge")
    if provider is None:
        return True, "(judge-Provider fehlt — übersprungen)"

    rubric: str = spec.get("rubric", "Brand-Voice")
    max_cost: float = float(spec.get("max_cost", 0.02))

    try:
        result = provider.evaluate(resp.text, rubric)
    except Exception as exc:
        return False, f"judge-Provider-Fehler: {exc}"

    cost: float = float(result.get("cost_eur", 0.0))
    if cost > max_cost:
        return False, (
            f"judge-Budget überschritten: {cost:.4f} EUR > Limit {max_cost:.4f} EUR "
            f"(Rubrik: {rubric!r})"
        )

    ok: bool = bool(result.get("pass", False))
    reason: str = result.get("reason", "")
    if not ok:
        return False, f"judge FAIL ({rubric!r}): {reason}"
    return True, ""


# --- Helpers ---


def _clip(text: str, n: int = 160) -> str:
    text = text.replace("\n", " ⏎ ")
    return text if len(text) <= n else text[:n] + "…"


def _parse_duration_ms(value: str | int | float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower()
    if s.endswith("ms"):
        return float(s[:-2])
    if s.endswith("s"):
        return float(s[:-1]) * 1000
    return float(s)
