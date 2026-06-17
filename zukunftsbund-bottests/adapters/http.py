"""HTTP-Adapter — feuert Requests gegen Webhooks/APIs.

Für Content Autopilot und n8n-Webhook-Endpunkte. Im Dry-Run werden Mock-
Antworten zurückgegeben, sodass die Pipeline ohne Netzwerk testbar bleibt.
"""

from __future__ import annotations

import json
import os
import time

from adapters.base import Adapter, Response
from runner.models import Step, StepKind, Suite


class HttpAdapter(Adapter):
    name = "http"

    def __init__(self, suite: Suite, *, dry_run: bool = False) -> None:
        super().__init__(suite, dry_run=dry_run)
        self.base_url = suite.target.base_url or ""
        self._mock_by_case = suite.target.extra.get("mock_replies", {})
        self._mock_replies: list[str] = []
        self._session = None

    def begin_case(self, case_id: str) -> None:
        if isinstance(self._mock_by_case, dict):
            self._mock_replies = list(self._mock_by_case.get(case_id, []))
        else:
            self._mock_replies = list(self._mock_by_case)

    async def setup(self) -> None:
        self._guard_test_target()
        if self.dry_run:
            return
        import httpx  # type: ignore

        self._session = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)

    async def teardown(self) -> None:
        if self._session is not None:
            await self._session.aclose()
            self._session = None

    def _guard_test_target(self) -> None:
        if self.dry_run:
            return
        prod_markers = [m.strip() for m in os.environ.get("HTTP_FORBIDDEN_HOSTS", "").split(",") if m.strip()]
        for marker in prod_markers:
            if marker and marker in self.base_url:
                raise PermissionError(
                    f"base_url {self.base_url!r} enthält gesperrten Host {marker!r} — "
                    "Tests gegen Produktion sind verboten."
                )

    async def send_step(self, step: Step) -> Response:
        start = time.perf_counter()
        if self.dry_run:
            text = self._mock_replies.pop(0) if self._mock_replies else f"[mock] {step.payload!r}"
            return Response(text=text, latency_ms=(time.perf_counter() - start) * 1000)

        # 'send' trägt hier ein dict: {method, path, json/body}
        spec = step.payload if isinstance(step.payload, dict) else {"path": str(step.payload)}
        method = spec.get("method", "POST").upper()
        path = spec.get("path", "/")
        body = spec.get("json") or spec.get("body")
        resp = await self._session.request(method, path, json=body)
        try:
            text = json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            text = resp.text
        return Response(
            text=text,
            latency_ms=(time.perf_counter() - start) * 1000,
            raw={"status_code": resp.status_code},
        )
