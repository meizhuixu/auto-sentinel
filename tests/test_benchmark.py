"""Tests for the smoke benchmark — yaml-sourced after T050.

The 5 scenarios are loaded from benchmarks/scenarios/*.yaml via the T048
BenchmarkScenario schema (no inline SCENARIOS list); the runner internals
(_run_v1 / _run_v2_detail / run_benchmark) are exercised with mocked
pipelines so the suite stays hermetic and zero-cost.
"""

import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph.types import Command

from autosentinel.agents.state import AgentState  # exercises state.py re-export
from autosentinel.benchmark import (
    BenchmarkScenario,
    _load_scenarios,
    _run_v1,
    _run_v2_detail,
    run_benchmark,
)

_SECURITY_ID = "004_security_sql_injection_attempt"
_CODE_ID = "001_code_null_user_context"


# ---------------------------------------------------------------------------
# Shared mock factories
# ---------------------------------------------------------------------------

def _v1_ok() -> dict:
    return {"resolved": True, "duration_ms": 5}


def _v2_ok(*, was_interrupted: bool = False, verdict: str = "SAFE") -> dict:
    return {
        "resolved": True,
        "duration_ms": 5,
        "agent_trace": [
            "DiagnosisAgent", "SupervisorAgent", "CodeFixerAgent",
            "SecurityReviewerAgent", "VerifierAgent",
        ],
        "security_verdict": verdict,
        "routing_decision": "CODE -> CodeFixerAgent",
        "was_interrupted": was_interrupted,
    }


def _mock_v2_side_effect(interrupted_id: str | None = None):
    def side_effect(scenario: BenchmarkScenario, log_path: Path) -> dict:
        if scenario.scenario_id == interrupted_id:
            return _v2_ok(was_interrupted=True, verdict="HIGH_RISK")
        return _v2_ok()
    return side_effect


# ---------------------------------------------------------------------------
# Scenario loading (yaml-sourced)
# ---------------------------------------------------------------------------

class TestLoadScenarios:
    def test_loads_one_scenario_per_yaml_file(self):
        # The loader returns one BenchmarkScenario per yaml file; the set grows
        # toward 50, so assert against the glob count, not a hard-coded number.
        yaml_count = len(list(Path("benchmarks/scenarios").glob("*.yaml")))
        assert yaml_count >= 5  # at least the migrated set is present
        assert len(_load_scenarios()) == yaml_count

    def test_all_are_benchmark_scenario_instances(self):
        assert all(isinstance(s, BenchmarkScenario) for s in _load_scenarios())

    def test_scenario_ids_unique(self):
        ids = [s.scenario_id for s in _load_scenarios()]
        assert len(ids) == len(set(ids))

    def test_categories_cover_all_types(self):
        categories = {s.category for s in _load_scenarios()}
        assert {"CODE", "INFRA", "SECURITY", "CONFIG"}.issubset(categories)

    def test_security_scenario_exists(self):
        assert any(s.category == "SECURITY" for s in _load_scenarios())


# ---------------------------------------------------------------------------
# _run_v1 unit
# ---------------------------------------------------------------------------

class TestRunV1:
    def test_resolved_on_success(self, tmp_path):
        report = tmp_path / "report.md"
        report.write_text("# Report")
        with patch("autosentinel.benchmark.run_pipeline", return_value=report):
            result = _run_v1(tmp_path / "log.json")
        assert result["resolved"] is True
        assert isinstance(result["duration_ms"], int)

    def test_unresolved_on_exception(self, tmp_path):
        with patch("autosentinel.benchmark.run_pipeline",
                   side_effect=RuntimeError("v1 pipeline down")):
            result = _run_v1(tmp_path / "log.json")
        assert result["resolved"] is False


# ---------------------------------------------------------------------------
# _run_v2_detail unit
# ---------------------------------------------------------------------------

class TestRunV2Detail:
    def _make_graph(self, *, interrupt_on_first: bool = False, verdict: str = "SAFE"):
        mock_graph = MagicMock()
        call_count = {"n": 0}

        def fake_invoke(state_or_command, config=None):
            call_count["n"] += 1
            if isinstance(state_or_command, Command):
                return {
                    "report_text": "# Report\n## Security Review\n",
                    "agent_trace": ["SecurityReviewerAgent", "VerifierAgent"],
                    "security_verdict": "HIGH_RISK",
                    "routing_decision": "SECURITY -> CodeFixerAgent",
                }
            if interrupt_on_first and call_count["n"] == 1:
                return {"__interrupt__": [{"value": {"reason": "HIGH_RISK"}}]}
            return {
                "report_text": "# Report\n",
                "agent_trace": [
                    "DiagnosisAgent", "CodeFixerAgent",
                    "SecurityReviewerAgent", "VerifierAgent",
                ],
                "security_verdict": verdict,
                "routing_decision": "CODE -> CodeFixerAgent",
            }

        mock_graph.invoke.side_effect = fake_invoke
        return mock_graph

    def _s(self, sid: str) -> BenchmarkScenario:
        return next(s for s in _load_scenarios() if s.scenario_id == sid)

    def test_normal_scenario_not_interrupted(self, tmp_path):
        log = tmp_path / "log.json"
        log.write_text("{}")
        with patch("autosentinel.benchmark.build_multi_agent_graph",
                   return_value=self._make_graph()):
            result = _run_v2_detail(self._s(_CODE_ID), log)
        assert result["was_interrupted"] is False
        assert result["resolved"] is True
        assert isinstance(result["agent_trace"], list)

    def test_security_interrupt_triggers_and_resumes(self, tmp_path):
        log = tmp_path / "log.json"
        log.write_text("{}")
        with patch("autosentinel.benchmark.build_multi_agent_graph",
                   return_value=self._make_graph(interrupt_on_first=True)):
            result = _run_v2_detail(self._s(_SECURITY_ID), log)
        assert result["was_interrupted"] is True
        assert result["security_verdict"] == "HIGH_RISK"
        assert result["resolved"] is True

    def test_exception_returns_unresolved(self, tmp_path):
        log = tmp_path / "log.json"
        log.write_text("{}")
        with patch("autosentinel.benchmark.build_multi_agent_graph",
                   side_effect=RuntimeError("graph unavailable")):
            result = _run_v2_detail(self._s(_CODE_ID), log)
        assert result["resolved"] is False
        assert result["was_interrupted"] is False
        assert result["agent_trace"] == []


# ---------------------------------------------------------------------------
# run_benchmark() end-to-end (mocked internals)
# ---------------------------------------------------------------------------

class TestRunBenchmark:
    def _run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect(_SECURITY_ID)):
            return run_benchmark()

    def test_returns_dict(self, tmp_path, monkeypatch):
        assert isinstance(self._run(tmp_path, monkeypatch), dict)

    def test_scenario_count_in_result(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch)["scenario_count"] == len(_load_scenarios())

    def test_v1_resolution_rate_not_null(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch)["v1_resolution_rate"] is not None

    def test_v2_resolution_rate_not_null(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch)["v2_resolution_rate"] is not None

    def test_v1_avg_ms_not_null(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch)["v1_avg_ms"] is not None

    def test_v2_avg_ms_not_null(self, tmp_path, monkeypatch):
        assert self._run(tmp_path, monkeypatch)["v2_avg_ms"] is not None

    def test_writes_json_report(self, tmp_path, monkeypatch):
        self._run(tmp_path, monkeypatch)
        report_path = tmp_path / "output" / "benchmark-report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert data["scenario_count"] == len(_load_scenarios())

    def test_report_has_scenarios_array(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch)
        assert "scenarios" in result
        assert len(result["scenarios"]) == len(_load_scenarios())

    def test_security_was_interrupted_true(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch)
        sec = next(s for s in result["scenarios"] if s["id"] == _SECURITY_ID)
        assert sec["v2"]["was_interrupted"] is True

    def test_security_verdict_high_risk(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch)
        sec = next(s for s in result["scenarios"] if s["id"] == _SECURITY_ID)
        assert sec["v2"]["security_verdict"] == "HIGH_RISK"

    def test_v2_detail_has_agent_trace(self, tmp_path, monkeypatch):
        result = self._run(tmp_path, monkeypatch)
        for s in result["scenarios"]:
            assert "agent_trace" in s["v2"]

    def test_run_scenario_exception_counts_as_unresolved(self, tmp_path, monkeypatch):
        """All scenarios unresolved when helpers return resolved=False."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1",
                   return_value={"resolved": False, "duration_ms": 0}), \
             patch("autosentinel.benchmark._run_v2_detail",
                   return_value={"resolved": False, "duration_ms": 0,
                                 "agent_trace": [], "security_verdict": None,
                                 "routing_decision": None, "was_interrupted": False}):
            result = run_benchmark()
        assert result["v1_resolution_rate"] == 0.0
        assert result["v2_resolution_rate"] == 0.0

    def test_benchmark_cli_main(self, tmp_path, monkeypatch):
        """Exercise the __main__ block via runpy."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect(_SECURITY_ID)):
            runpy.run_module("autosentinel.benchmark", run_name="__main__",
                             alter_sys=True)
        assert (tmp_path / "output" / "benchmark-report.json").exists()
