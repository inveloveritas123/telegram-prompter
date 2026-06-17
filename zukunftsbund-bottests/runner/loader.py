"""Schicht 1: YAML-Szenarien laden und in Modelle übersetzen.

Unterstützt Umgebungsvariablen-Substitution per ``{{ env.NAME }}`` —
so landen Secrets (Passwörter, Tokens) nie im Klartext in der YAML.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .models import Case, Step, StepKind, Suite, Target

_ENV_PATTERN = re.compile(r"\{\{\s*env\.([A-Z0-9_]+)\s*\}\}")

# Mapping: YAML-Schlüssel -> StepKind. Reihenfolge im Dict bleibt erhalten.
_STEP_KEYS = {
    "send": StepKind.SEND,
    "send_photo": StepKind.SEND_PHOTO,
    "send_album": StepKind.SEND_ALBUM,
    "send_voice": StepKind.SEND_VOICE,
    "expect": StepKind.EXPECT,
    "wait": StepKind.WAIT,
    "assert_sheet": StepKind.ASSERT_SHEET,
    "assert_n8n": StepKind.ASSERT_N8N,
}


def _substitute_env(value: Any) -> Any:
    """Ersetzt {{ env.NAME }} rekursiv durch os.environ-Werte."""
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            name = m.group(1)
            if name not in os.environ:
                raise KeyError(f"Umgebungsvariable {name!r} ist nicht gesetzt (in YAML referenziert).")
            return os.environ[name]

        return _ENV_PATTERN.sub(repl, value)
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    return value


def _parse_step(raw: dict[str, Any]) -> Step:
    """Ein YAML-Step-Dict hat genau einen bekannten Schlüssel (send/expect/...)."""
    known = [k for k in raw if k in _STEP_KEYS]
    if len(known) != 1:
        raise ValueError(
            f"Schritt muss genau einen bekannten Schlüssel haben "
            f"({', '.join(_STEP_KEYS)}); gefunden: {list(raw)}"
        )
    key = known[0]
    return Step(kind=_STEP_KEYS[key], payload=raw[key], raw=raw)


def _parse_case(raw: dict[str, Any]) -> Case:
    return Case(
        id=raw["id"],
        desc=raw.get("desc", ""),
        setup=raw.get("setup", {}) or {},
        steps=[_parse_step(s) for s in raw.get("steps", [])],
        tags=list(raw.get("tags", []) or []),
    )


def load_suite(path: str | Path) -> Suite:
    """Lädt eine cases.yaml und gibt eine Suite zurück."""
    path = Path(path)
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data = _substitute_env(data)

    tgt = data.get("target", {})
    target = Target(
        adapter=tgt["adapter"],
        bot=tgt.get("bot"),
        base_url=tgt.get("base_url"),
        extra={k: v for k, v in tgt.items() if k not in {"adapter", "bot", "base_url"}},
    )

    return Suite(
        name=data["suite"],
        target=target,
        setup=data.get("setup", {}) or {},
        cases=[_parse_case(c) for c in data.get("cases", [])],
        source_path=str(path),
    )


def discover_suites(suites_dir: str | Path) -> dict[str, Path]:
    """Findet alle Suiten unterhalb von suites_dir (jede cases.yaml = eine Suite)."""
    suites_dir = Path(suites_dir)
    found: dict[str, Path] = {}
    for cases_file in sorted(suites_dir.glob("*/cases.yaml")):
        found[cases_file.parent.name] = cases_file
    return found
