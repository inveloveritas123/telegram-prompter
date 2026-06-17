"""prompter-mcp-Anbindung.

Verbindet mit dem MCP-Server (FastMCP, HTTP/streamable-http) über
PROMPTER_MCP_URL (Standard: http://prompter-mcp:8080/mcp).

Im Mock-Modus (dry_run=True oder ORCHESTRATOR_ENGINE=mock) wird der
MCP-Aufruf lokal simuliert — kein echter Netzwerk-Call.

Verfügbare MCP-Tools (laut BUILD-CONTRACT):
  list_suites() -> [name]
  run_suite(name, env, tags, only, dry_run) -> {run_id, suite, passed, executed, all_green, report_path}
  run_case(suite, case_id, dry_run) -> {...}
  get_report(run_id) -> dict
  compare_runs(a, b) -> {regressions, fixed}
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass


MCP_URL = os.environ.get("PROMPTER_MCP_URL", "http://prompter-mcp:8080/mcp")


@dataclass
class SuiteRunResult:
    run_id: str
    suite: str
    passed: int
    executed: int
    all_green: bool
    report_path: str
    red_cases: list[str]    # IDs der roten Fälle


class MockMcpClient:
    """Lokaler Mock — kein Netzwerk. Simuliert immer einen grünen Lauf."""

    def list_suites(self) -> list[str]:
        return ["kontakt-bot", "content-autopilot"]

    def run_suite(
        self,
        name: str,
        *,
        env: str = "staging",
        tags: list[str] | None = None,
        only: list[str] | None = None,
        dry_run: bool = True,
    ) -> SuiteRunResult:
        run_id = uuid.uuid4().hex[:12]
        return SuiteRunResult(
            run_id=run_id,
            suite=name,
            passed=3,
            executed=3,
            all_green=True,
            report_path=f"/data/reports/{name}-{run_id}.json",
            red_cases=[],
        )

    def run_case(
        self, suite: str, case_id: str, *, dry_run: bool = True
    ) -> SuiteRunResult:
        run_id = uuid.uuid4().hex[:12]
        return SuiteRunResult(
            run_id=run_id,
            suite=suite,
            passed=1,
            executed=1,
            all_green=True,
            report_path=f"/data/reports/{suite}-{run_id}.json",
            red_cases=[],
        )

    def get_report(self, run_id: str) -> dict:
        return {
            "run_id": run_id,
            "all_green": True,
            "passed": 3,
            "executed": 3,
            "cases": [],
        }


class HttpMcpClient:
    """Echter HTTP-Client gegen prompter-mcp (FastMCP, streamable-http).

    Wird nur bei ORCHESTRATOR_ENGINE=claude genutzt (kein dry_run).
    """

    def __init__(self, url: str = MCP_URL) -> None:
        self._url = url.rstrip("/")

    def _call(self, tool: str, params: dict) -> dict:  # pragma: no cover
        try:
            import httpx
        except ImportError as e:
            raise RuntimeError("httpx nicht installiert — pip install httpx") from e

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": params},
        }
        resp = httpx.post(
            f"{self._url}",
            json=payload,
            timeout=120,
            headers={"Content-Type": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP-Fehler: {data['error']}")
        # FastMCP gibt result.content[0].text (JSON-String) zurück
        content = data.get("result", {}).get("content", [{}])
        text = content[0].get("text", "{}") if content else "{}"
        return json.loads(text)

    def list_suites(self) -> list[str]:  # pragma: no cover
        return self._call("list_suites", {})

    def run_suite(  # pragma: no cover
        self,
        name: str,
        *,
        env: str = "staging",
        tags: list[str] | None = None,
        only: list[str] | None = None,
        dry_run: bool = True,
    ) -> SuiteRunResult:
        params: dict = {"name": name, "env": env, "dry_run": dry_run}
        if tags:
            params["tags"] = tags
        if only:
            params["only"] = only
        data = self._call("run_suite", params)
        return SuiteRunResult(
            run_id=data["run_id"],
            suite=data["suite"],
            passed=data["passed"],
            executed=data["executed"],
            all_green=data["all_green"],
            report_path=data.get("report_path", ""),
            red_cases=data.get("red_cases", []),
        )

    def run_case(  # pragma: no cover
        self, suite: str, case_id: str, *, dry_run: bool = True
    ) -> SuiteRunResult:
        data = self._call("run_case", {"suite": suite, "case_id": case_id, "dry_run": dry_run})
        return SuiteRunResult(
            run_id=data["run_id"],
            suite=data["suite"],
            passed=data["passed"],
            executed=data["executed"],
            all_green=data["all_green"],
            report_path=data.get("report_path", ""),
            red_cases=data.get("red_cases", []),
        )

    def get_report(self, run_id: str) -> dict:  # pragma: no cover
        return self._call("get_report", {"run_id": run_id})


def create_client(dry_run: bool = False) -> MockMcpClient | HttpMcpClient:
    """Fabrik — wählt Client anhand von Env/Flag."""
    engine = os.environ.get("ORCHESTRATOR_ENGINE", "mock").lower()
    if dry_run or engine == "mock":
        return MockMcpClient()
    return HttpMcpClient()
