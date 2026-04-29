"""Tests for the Sprint 4 smoke benchmark — extended for per-scenario detail."""

import json
import runpy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from langgraph.types import Command

from autosentinel.agents.state import AgentState  # exercises state.py re-export
from autosentinel.benchmark import (
    SCENARIOS,
    SPRINT4_MOCK_APPROVAL,
    _run_v1,
    _run_v2_detail,
    run_benchmark,
)


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
        "routing_decision": "CODE → CodeFixerAgent",
        "was_interrupted": was_interrupted,
    }


def _mock_v2_side_effect(interrupted_id: str | None = None):
    def side_effect(scenario: dict, log_path: Path) -> dict:
        if scenario["id"] == interrupted_id:
            return _v2_ok(was_interrupted=True, verdict="HIGH_RISK")
        return _v2_ok()
    return side_effect


# ---------------------------------------------------------------------------
# Scenario metadata
# ---------------------------------------------------------------------------

class TestBenchmarkScenarios:
    def test_scenario_count_is_five(self):
        assert len(SCENARIOS) == 5

    def test_scenario_ids_unique(self):
        ids = [s["id"] for s in SCENARIOS]
        assert len(ids) == len(set(ids))

    def test_scenario_has_required_fields(self):
        required = {"id", "category", "log_file", "expected_verdict"}
        for s in SCENARIOS:
            assert required.issubset(s.keys()), f"Scenario {s} missing fields"

    def test_categories_cover_all_types(self):
        categories = {s["category"] for s in SCENARIOS}
        assert "CODE" in categories
        assert "INFRA" in categories
        assert "SECURITY" in categories
        assert "CONFIG" in categories

    def test_s04_security_scenario_exists(self):
        security_scenarios = [s for s in SCENARIOS if s["category"] == "SECURITY"]
        assert len(security_scenarios) >= 1

    def test_s04_expected_verdict_is_high_risk(self):
        """T024 acceptance: s04 must target the HIGH_RISK path."""
        s04 = next(s for s in SCENARIOS if s["id"] == "s04")
        assert s04["expected_verdict"] == "HIGH_RISK"


# ---------------------------------------------------------------------------
# SPRINT4_MOCK_APPROVAL shape
# ---------------------------------------------------------------------------

class TestMockApproval:
    def test_has_mock_marker(self):
        assert SPRINT4_MOCK_APPROVAL.get("_mock") is True

    def test_approved_by_identifies_benchmark(self):
        assert "sprint4_benchmark_mock" in SPRINT4_MOCK_APPROVAL["approved_by"]


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
                    "routing_decision": "SECURITY → CodeFixerAgent",
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
                "routing_decision": "CODE → CodeFixerAgent",
            }

        mock_graph.invoke.side_effect = fake_invoke
        return mock_graph

    def _s(self, sid: str) -> dict:
        return next(s for s in SCENARIOS if s["id"] == sid)

    def test_normal_scenario_not_interrupted(self, tmp_path):
        log = tmp_path / "log.json"
        log.write_text("{}")
        with patch("autosentinel.benchmark.build_multi_agent_graph",
                   return_value=self._make_graph()):
            result = _run_v2_detail(self._s("s01"), log)
        assert result["was_interrupted"] is False
        assert result["resolved"] is True
        assert isinstance(result["agent_trace"], list)

    def test_s04_interrupt_triggers_and_resumes(self, tmp_path):
        log = tmp_path / "log.json"
        log.write_text("{}")
        with patch("autosentinel.benchmark.build_multi_agent_graph",
                   return_value=self._make_graph(interrupt_on_first=True)):
            result = _run_v2_detail(self._s("s04"), log)
        assert result["was_interrupted"] is True
        assert result["security_verdict"] == "HIGH_RISK"
        assert result["resolved"] is True

    def test_non_s04_does_not_patch_code_fixer(self, tmp_path):
        """nullcontext path: _get_fix_for_security must not be called for non-s04."""
        log = tmp_path / "log.json"
        log.write_text("{}")
        with patch("autosentinel.benchmark.build_multi_agent_graph",
                   return_value=self._make_graph(verdict="SAFE")), \
             patch("autosentinel.agents.code_fixer.CodeFixerAgent"
                   "._get_fix_for_security") as mock_fix:
            _run_v2_detail(self._s("s02"), log)
        mock_fix.assert_not_called()

    def test_exception_returns_unresolved(self, tmp_path):
        log = tmp_path / "log.json"
        log.write_text("{}")
        with patch("autosentinel.benchmark.build_multi_agent_graph",
                   side_effect=RuntimeError("graph unavailable")):
            result = _run_v2_detail(self._s("s01"), log)
        assert result["resolved"] is False
        assert result["was_interrupted"] is False
        assert result["agent_trace"] == []


# ---------------------------------------------------------------------------
# run_benchmark() end-to-end (mocked internals)
# ---------------------------------------------------------------------------

class TestRunBenchmark:
    def _patches(self):
        """Context: patch _run_v1 and _run_v2_detail at the module level."""
        return (
            patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()),
            patch("autosentinel.benchmark._run_v2_detail",
                  side_effect=_mock_v2_side_effect("s04")),
        )

    def test_returns_dict(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert isinstance(result, dict)

    def test_scenario_count_in_result(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert result["scenario_count"] == 5

    def test_v1_resolution_rate_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert result["v1_resolution_rate"] is not None

    def test_v2_resolution_rate_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert result["v2_resolution_rate"] is not None

    def test_v1_avg_ms_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert result["v1_avg_ms"] is not None

    def test_v2_avg_ms_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert result["v2_avg_ms"] is not None

    def test_writes_json_report(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            run_benchmark()
        report_path = tmp_path / "output" / "benchmark-report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert data["scenario_count"] == 5

    def test_report_has_scenarios_array(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert "scenarios" in result
        assert len(result["scenarios"]) == 5

    def test_s04_was_interrupted_true(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        s04 = next(s for s in result["scenarios"] if s["id"] == "s04")
        assert s04["v2"]["was_interrupted"] is True

    def test_s04_security_verdict_high_risk(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        s04 = next(s for s in result["scenarios"] if s["id"] == "s04")
        assert s04["v2"]["security_verdict"] == "HIGH_RISK"

    def test_v2_detail_has_agent_trace(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        for s in result["scenarios"]:
            assert "agent_trace" in s["v2"]

    def test_scenario_logs_already_exist_skips_write(self, tmp_path, monkeypatch):
        """Exercise the `if not log_path.exists()` False branch."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()
        data_dir = tmp_path / "data" / "benchmark"
        data_dir.mkdir(parents=True)
        for s in SCENARIOS:
            (data_dir / s["log_file"]).write_text(
                json.dumps(s["log_content"]), encoding="utf-8"
            )
        with patch("autosentinel.benchmark._run_v1", return_value=_v1_ok()), \
             patch("autosentinel.benchmark._run_v2_detail",
                   side_effect=_mock_v2_side_effect("s04")):
            result = run_benchmark()
        assert result["scenario_count"] == 5

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
                   side_effect=_mock_v2_side_effect("s04")):
            runpy.run_module("autosentinel.benchmark", run_name="__main__",
                             alter_sys=True)
        assert (tmp_path / "output" / "benchmark-report.json").exists()
