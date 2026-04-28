"""Tests for the Sprint 4 smoke benchmark."""

import json
import runpy
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from autosentinel.agents.state import AgentState  # exercises state.py re-export
from autosentinel.benchmark import SCENARIOS, run_benchmark


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


class TestRunBenchmark:
    def _make_mock_pipeline(self, tmp_path):
        report = tmp_path / "mock-report.md"
        report.write_text("# Mock Report\n## Sandbox Execution\n**Status**: success\n")

        def fake_pipeline(log_path):
            return report

        return fake_pipeline

    def test_returns_dict(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            result = run_benchmark()

        assert isinstance(result, dict)

    def test_scenario_count_in_result(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            result = run_benchmark()

        assert result["scenario_count"] == 5

    def test_v1_resolution_rate_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            result = run_benchmark()

        assert result["v1_resolution_rate"] is not None

    def test_v2_resolution_rate_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            result = run_benchmark()

        assert result["v2_resolution_rate"] is not None

    def test_v1_avg_ms_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            result = run_benchmark()

        assert result["v1_avg_ms"] is not None

    def test_v2_avg_ms_not_null(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            result = run_benchmark()

        assert result["v2_avg_ms"] is not None

    def test_writes_json_report(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            run_benchmark()

        report_path = tmp_path / "output" / "benchmark-report.json"
        assert report_path.exists()
        data = json.loads(report_path.read_text())
        assert data["scenario_count"] == 5

    def test_scenario_logs_already_exist_skips_write(self, tmp_path, monkeypatch):
        """Exercise the `if not log_path.exists()` False branch."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        # Pre-create the log files
        data_dir = tmp_path / "data" / "benchmark"
        data_dir.mkdir(parents=True)
        for s in SCENARIOS:
            (data_dir / s["log_file"]).write_text(
                json.dumps(s["log_content"]), encoding="utf-8"
            )

        with patch("autosentinel.benchmark.run_pipeline", side_effect=self._make_mock_pipeline(tmp_path)):
            result = run_benchmark()

        assert result["scenario_count"] == 5

    def test_run_scenario_exception_counts_as_unresolved(self, tmp_path, monkeypatch):
        """Exercise exception handling in _run_scenario."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.benchmark.run_pipeline",
                   side_effect=RuntimeError("pipeline error")):
            result = run_benchmark()

        assert result["v1_resolution_rate"] == 0.0
        assert result["v2_resolution_rate"] == 0.0

    def test_benchmark_cli_main(self, tmp_path, monkeypatch):
        """Exercise the __main__ block via runpy."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "output").mkdir()

        with patch("autosentinel.benchmark.run_pipeline",
                   side_effect=self._make_mock_pipeline(tmp_path)):
            runpy.run_module("autosentinel.benchmark", run_name="__main__", alter_sys=True)

        assert (tmp_path / "output" / "benchmark-report.json").exists()
