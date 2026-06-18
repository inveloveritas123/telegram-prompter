"""Sprint 8: Tests für Metriken, compare_runs und Trend-Dashboard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from runner.compare import compare_runs
from runner.models import CaseResult, Status, StepResult, SuiteResult
from runner.reporter import _serialize, console_report


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------


def _make_suite(
    suite_name: str = "test-suite",
    run_id: str = "run-001",
    cases: list[CaseResult] | None = None,
    cost: float = 0.0,
) -> SuiteResult:
    return SuiteResult(
        suite=suite_name,
        run_id=run_id,
        cases=cases or [],
        started_at="2026-01-01T00:00:00",
        finished_at="2026-01-01T00:00:05",
        cost=cost,
    )


def _make_case(
    cid: str = "T1",
    status: Status = Status.PASS,
    duration_ms: float = 100.0,
    step_latencies: list[float] | None = None,
) -> CaseResult:
    steps = []
    for lat in (step_latencies or []):
        steps.append(StepResult(kind="expect", status=Status.PASS, latency_ms=lat))
    return CaseResult(id=cid, desc="", status=status, steps=steps, duration_ms=duration_ms)


# ---------------------------------------------------------------------------
# Metrik-Aggregation
# ---------------------------------------------------------------------------


class TestMetricAggregation:
    def test_total_latency_ms_sums_step_latencies(self):
        case = _make_case(step_latencies=[100.0, 200.0, 300.0])
        suite = _make_suite(cases=[case])
        assert suite.total_latency_ms == 600.0

    def test_avg_latency_ms(self):
        case = _make_case(step_latencies=[100.0, 200.0, 300.0])
        suite = _make_suite(cases=[case])
        assert suite.avg_latency_ms == pytest.approx(200.0)

    def test_max_latency_ms(self):
        case = _make_case(step_latencies=[50.0, 999.0, 10.0])
        suite = _make_suite(cases=[case])
        assert suite.max_latency_ms == pytest.approx(999.0)

    def test_no_latency_data_returns_none(self):
        # Steps ohne latency_ms (= None)
        step = StepResult(kind="send", status=Status.PASS, latency_ms=None)
        case = CaseResult(id="T1", desc="", status=Status.PASS, steps=[step], duration_ms=50.0)
        suite = _make_suite(cases=[case])
        assert suite.avg_latency_ms is None
        assert suite.max_latency_ms is None
        assert suite.total_latency_ms == 0.0

    def test_total_duration_ms_sums_cases(self):
        c1 = _make_case(cid="T1", duration_ms=120.0)
        c2 = _make_case(cid="T2", duration_ms=80.0)
        suite = _make_suite(cases=[c1, c2])
        assert suite.total_duration_ms == 200.0

    def test_cost_field_default_zero(self):
        suite = _make_suite()
        assert suite.cost == 0.0

    def test_cost_field_set(self):
        suite = _make_suite(cost=0.0042)
        assert suite.cost == pytest.approx(0.0042)

    def test_serialize_includes_metrics_block(self):
        case = _make_case(step_latencies=[150.0])
        suite = _make_suite(cases=[case])
        d = _serialize(suite)
        assert "metrics" in d
        m = d["metrics"]
        assert m["total_latency_ms"] == pytest.approx(150.0)
        assert m["avg_latency_ms"] == pytest.approx(150.0)
        assert m["max_latency_ms"] == pytest.approx(150.0)
        assert "passed" in m
        assert "failed" in m
        assert "total" in m

    def test_serialize_existing_fields_unchanged(self):
        """Rückwärtskompatibilität: alte Felder dürfen nicht verschwinden."""
        case = _make_case()
        suite = _make_suite(cases=[case])
        d = _serialize(suite)
        assert "suite" in d
        assert "run_id" in d
        assert "cases" in d
        assert "started_at" in d
        assert "finished_at" in d

    def test_console_report_shows_latency(self):
        case = _make_case(step_latencies=[200.0, 400.0])
        suite = _make_suite(cases=[case])
        report = console_report(suite)
        assert "Latenz" in report
        assert "600" in report  # total_latency_ms

    def test_console_report_shows_cost_when_nonzero(self):
        suite = _make_suite(cost=0.0123)
        report = console_report(suite)
        assert "Kosten" in report
        assert "0.0123" in report


# ---------------------------------------------------------------------------
# compare_runs
# ---------------------------------------------------------------------------


def _make_report(
    suite: str = "test-suite",
    run_id: str = "run-001",
    cases: list[dict] | None = None,
    metrics: dict | None = None,
) -> dict:
    return {
        "suite": suite,
        "run_id": run_id,
        "started_at": "2026-01-01T00:00:00",
        "finished_at": "2026-01-01T00:00:05",
        "cases": cases or [],
        "metrics": metrics or {},
    }


def _case_dict(cid: str, status: str, duration_ms: float = 100.0) -> dict:
    return {"id": cid, "desc": "", "status": status, "steps": [], "duration_ms": duration_ms}


class TestCompareRuns:
    def test_regression_detected_when_green_becomes_red(self):
        a = _make_report(cases=[_case_dict("T1", "pass")])
        b = _make_report(cases=[_case_dict("T1", "fail")])
        delta = compare_runs(a, b)
        assert len(delta["regressions"]) == 1
        assert delta["regressions"][0]["id"] == "T1"
        assert delta["regressions"][0]["reason"] == "status"

    def test_fix_detected_when_red_becomes_green(self):
        a = _make_report(cases=[_case_dict("T1", "fail")])
        b = _make_report(cases=[_case_dict("T1", "pass")])
        delta = compare_runs(a, b)
        assert len(delta["fixes"]) == 1
        assert delta["fixes"][0]["id"] == "T1"

    def test_latency_regression_detected(self):
        # T1 war 200 ms, jetzt 1200 ms (6x, +1000 ms > 500 ms Schwelle)
        a = _make_report(cases=[_case_dict("T1", "pass", duration_ms=200.0)])
        b = _make_report(cases=[_case_dict("T1", "pass", duration_ms=1200.0)])
        delta = compare_runs(a, b)
        assert len(delta["regressions"]) == 1
        assert delta["regressions"][0]["reason"] == "latency"
        assert delta["regressions"][0]["slowdown_factor"] == pytest.approx(6.0)

    def test_small_slowdown_not_a_regression(self):
        # +100 ms — unter beiden Schwellen
        a = _make_report(cases=[_case_dict("T1", "pass", duration_ms=200.0)])
        b = _make_report(cases=[_case_dict("T1", "pass", duration_ms=300.0)])
        delta = compare_runs(a, b)
        assert len(delta["regressions"]) == 0

    def test_unchanged_case(self):
        a = _make_report(cases=[_case_dict("T1", "pass")])
        b = _make_report(cases=[_case_dict("T1", "pass")])
        delta = compare_runs(a, b)
        assert "T1" in delta["unchanged"]

    def test_new_case_detected(self):
        a = _make_report(cases=[])
        b = _make_report(cases=[_case_dict("T99", "pass")])
        delta = compare_runs(a, b)
        assert "T99" in delta["new_cases"]

    def test_removed_case_detected(self):
        a = _make_report(cases=[_case_dict("T1", "pass")])
        b = _make_report(cases=[])
        delta = compare_runs(a, b)
        assert "T1" in delta["removed_cases"]

    def test_compare_from_file(self, tmp_path: Path):
        """compare_runs akzeptiert Pfade zu JSON-Dateien."""
        a = _make_report(cases=[_case_dict("T1", "pass")])
        b = _make_report(cases=[_case_dict("T1", "fail")])
        fa = tmp_path / "a.json"
        fb = tmp_path / "b.json"
        fa.write_text(json.dumps(a), encoding="utf-8")
        fb.write_text(json.dumps(b), encoding="utf-8")
        delta = compare_runs(fa, fb)
        assert len(delta["regressions"]) == 1

    def test_summary_is_nonempty_string(self):
        a = _make_report()
        b = _make_report()
        delta = compare_runs(a, b)
        assert isinstance(delta["summary"], str)
        assert len(delta["summary"]) > 0

    def test_metrics_delta_included(self):
        a = _make_report(metrics={"total_duration_ms": 500.0, "cost": 0.01})
        b = _make_report(metrics={"total_duration_ms": 700.0, "cost": 0.02})
        delta = compare_runs(a, b)
        md = delta["metrics_delta"]
        assert "total_duration_ms" in md
        assert md["total_duration_ms"]["delta"] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# Trend-Dashboard
# ---------------------------------------------------------------------------


class TestTrendDashboard:
    def test_dashboard_generates_html(self, tmp_path: Path):
        from scripts.trend_dashboard import build_dashboard

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        # Einen einfachen Report anlegen
        report = _make_report(
            run_id="run-abc",
            cases=[_case_dict("T1", "pass", 120.0)],
            metrics={"passed": 1, "failed": 0, "errors": 0, "skipped": 0, "total": 1,
                     "total_duration_ms": 120.0, "avg_latency_ms": None, "max_latency_ms": None, "cost": 0.0},
        )
        (reports_dir / "test-suite-run-abc.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        out = tmp_path / "trend.html"
        result_path = build_dashboard(reports_dir, out)
        assert result_path == out
        content = out.read_text(encoding="utf-8")
        assert content.startswith("<!DOCTYPE html>")
        assert "run-abc" in content

    def test_dashboard_empty_reports_dir(self, tmp_path: Path):
        from scripts.trend_dashboard import build_dashboard

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        out = tmp_path / "trend.html"
        build_dashboard(reports_dir, out)
        content = out.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        # Kein Crash, aber Hinweis auf leere Tabelle
        assert "Noch keine Reports" in content

    def test_dashboard_contains_chart_script(self, tmp_path: Path):
        from scripts.trend_dashboard import build_dashboard

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        out = tmp_path / "trend.html"
        build_dashboard(reports_dir, out)
        content = out.read_text(encoding="utf-8")
        assert "<canvas" in content
        assert "<script>" in content
