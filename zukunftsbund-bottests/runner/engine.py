"""Orchestrierung: lädt Suite, fährt Adapter, prüft Assertions, sammelt Ergebnis.

Verbindet alle vier Schichten. Kennt nur den Adapter-Vertrag und die
Assertion-Registry — bleibt damit kanalunabhängig.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone

from adapters.base import Adapter, Response
from assertions import core as assertions
from runner.models import (
    Case,
    CaseResult,
    Status,
    Step,
    StepKind,
    StepResult,
    Suite,
    SuiteResult,
)

# Adapter-Registry: Name aus YAML -> Klasse.
from adapters.http import HttpAdapter
from adapters.telegram import TelegramAdapter

ADAPTERS: dict[str, type[Adapter]] = {
    "telegram": TelegramAdapter,
    "http": HttpAdapter,
}

_SENDING = {StepKind.SEND, StepKind.SEND_PHOTO, StepKind.SEND_ALBUM, StepKind.SEND_VOICE}


def build_adapter(suite: Suite, *, dry_run: bool) -> Adapter:
    cls = ADAPTERS.get(suite.target.adapter)
    if cls is None:
        raise ValueError(f"Kein Adapter für {suite.target.adapter!r}. Bekannt: {list(ADAPTERS)}")
    return cls(suite, dry_run=dry_run)


async def run_suite(
    suite: Suite,
    *,
    dry_run: bool = False,
    context: dict | None = None,
    only: set[str] | None = None,
    tags: set[str] | None = None,
) -> SuiteResult:
    """Fährt eine Suite.

    `only` = Teilmenge von Case-IDs, `tags` = nur Fälle mit mind. einem dieser
    Tags. Beides dient gezieltem Re-Testen nach einer Änderung.
    """
    context = context or {}
    adapter = build_adapter(suite, dry_run=dry_run)
    result = SuiteResult(
        suite=suite.name,
        run_id=uuid.uuid4().hex[:12],
        started_at=_now(),
    )

    # Sprint 2: reset_static_data vor dem Lauf, falls der Suite-Setup es verlangt
    # und ein n8n-Client im Context verfügbar ist.
    n8n_client = context.get("n8n")
    reset_workflow_id = suite.setup.get("reset_static_data")
    if n8n_client is not None and reset_workflow_id:
        n8n_client.reset_static_data(reset_workflow_id)

    await adapter.setup()
    try:
        for case in suite.cases:
            selected = (not only or case.id in only) and (not tags or bool(tags & set(case.tags)))
            if not selected:
                result.cases.append(
                    CaseResult(id=case.id, desc=case.desc, status=Status.SKIP)
                )
                continue
            result.cases.append(await _run_case(adapter, case, context))
    finally:
        await adapter.teardown()
        result.finished_at = _now()
    return result


async def _run_case(adapter: Adapter, case: Case, context: dict) -> CaseResult:
    case_start = time.perf_counter()
    adapter.begin_case(case.id)
    cr = CaseResult(id=case.id, desc=case.desc, status=Status.PASS)
    last_response = Response()
    try:
        for step in case.steps:
            sr = await _run_step(adapter, step, context, last_response)
            cr.steps.append(sr)
            if step.kind in _SENDING and sr.latency_ms is not None:
                # Antwort des letzten Sende-Schritts merken (für nachfolgende expects)
                last_response = Response(text=sr.detail or "", latency_ms=sr.latency_ms)
            if sr.status in (Status.FAIL, Status.ERROR):
                cr.status = sr.status
                break  # Fail-fast pro Case
    except Exception as exc:  # pragma: no cover
        cr.status = Status.ERROR
        cr.error = repr(exc)
    cr.duration_ms = (time.perf_counter() - case_start) * 1000
    return cr


async def _run_step(adapter: Adapter, step: Step, context: dict, last: Response) -> StepResult:
    # Nicht-sendende Schritte zuerst.
    if step.kind is StepKind.WAIT:
        await asyncio.sleep(assertions._parse_duration_ms(step.payload) / 1000)
        return StepResult(kind=step.kind.value, status=Status.PASS)

    if step.kind in (StepKind.EXPECT, StepKind.ASSERT_SHEET, StepKind.ASSERT_N8N):
        spec = step.payload
        if step.kind is StepKind.ASSERT_SHEET:
            spec = {"sheet_row": step.payload}
        elif step.kind is StepKind.ASSERT_N8N:
            spec = {"n8n_execution_ok": step.payload}
        ok, detail = assertions.evaluate(spec, last, context)
        return StepResult(
            kind=step.kind.value,
            status=Status.PASS if ok else Status.FAIL,
            detail=detail,
        )

    # Sendende Schritte.
    resp = await adapter.send_step(step)
    # detail trägt hier die Antwort weiter (Hack über StepResult.detail).
    return StepResult(kind=step.kind.value, status=Status.PASS, detail=resp.text, latency_ms=resp.latency_ms)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
