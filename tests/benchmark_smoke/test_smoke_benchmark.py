"""T061: CI-runnable smoke benchmark.

Runs the 5 migrated scenarios through scripts/run_benchmark.py in --use-mock
mode (MockLLMClient, $0) with Docker patched, and asserts the summary.json
schema is compliant and the CostGuard budget is never tripped at zero cost.

The runner is loaded from its file path (scripts/ is not a package).
"""

import importlib.util
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNNER_PATH = _REPO_ROOT / "scripts" / "run_benchmark.py"

# The 5 migrated scenarios cover all 4 categories after s05 reclassification
# (2 CODE, 1 INFRA, 1 CONFIG, 1 SECURITY).
SMOKE_SCENARIO_IDS = [
    "001_code_null_user_context",
    "002_infra_db_connection_refused",
    "003_config_jwt_secret_missing",
    "004_security_sql_injection_attempt",
    "005_code_weird_exception",
]


def _load_runner():
    spec = importlib.util.spec_from_file_location("run_benchmark", _RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _docker_success(mock_docker: MagicMock) -> None:
    client = MagicMock()
    container = MagicMock()
    mock_docker.from_env.return_value = client
    client.containers.run.return_value = container
    container.wait.return_value = {"StatusCode": 0}
    container.logs.side_effect = [b"ok\n", b""]


@pytest.fixture
def smoke_run(tmp_path):
    runner = _load_runner()
    with patch("autosentinel.agents.verifier.docker") as v_md, \
         patch("autosentinel.nodes.execute_fix.docker") as e_md:
        _docker_success(v_md)
        _docker_success(e_md)
        summary = runner.run(
            scenarios_dir=Path("benchmarks/scenarios"),
            budget="150",
            use_mock=True,
            only=set(SMOKE_SCENARIO_IDS),
            output_root=tmp_path,
        )
    return summary, tmp_path


class TestSmokeBenchmark:
    def test_scenario_count_is_five(self, smoke_run):
        summary, _ = smoke_run
        assert summary["scenario_count"] == 5

    def test_summary_top_level_schema(self, smoke_run):
        summary, _ = smoke_run
        for key in ("run_id", "scenario_count", "category_distribution",
                    "v1", "v2", "security_subset"):
            assert key in summary, f"missing summary key: {key}"

    def test_pipeline_sections_have_no_null_metrics(self, smoke_run):
        summary, _ = smoke_run
        for side in ("v1", "v2"):
            sec = summary[side]
            assert sec["latency_ms"]["p50"] is not None
            assert sec["latency_ms"]["p95"] is not None
            assert sec["total_cost"] is not None
            assert sec["resolution_rate"] is not None

    def test_total_cost_is_zero_under_mock(self, smoke_run):
        summary, _ = smoke_run
        # MockLLMClient never accumulates -> zero spend, budget never tripped.
        assert Decimal(summary["v2"]["total_cost"]) == Decimal("0")
        assert Decimal(summary["v1"]["total_cost"]) == Decimal("0")

    def test_security_subset_zero_false_negatives_under_mock(self, smoke_run):
        summary, _ = smoke_run
        sub = summary["security_subset"]
        # 1 SECURITY scenario (004) in the smoke set; mock returns ground-truth.
        assert sub["count"] == 1
        assert sub["v2_false_negative_count"] == 0
        assert sub["v2_false_negative_scenario_ids"] == []

    def test_results_jsonl_written_and_valid(self, smoke_run):
        summary, output_root = smoke_run
        results_path = output_root / summary["run_id"] / "results.jsonl"
        assert results_path.exists()
        lines = [l for l in results_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 5
        from autosentinel.benchmark import BenchmarkResult
        for line in lines:
            BenchmarkResult.model_validate(json.loads(line))  # schema-valid

    def test_summary_json_written(self, smoke_run):
        summary, output_root = smoke_run
        summary_path = output_root / summary["run_id"] / "summary.json"
        assert summary_path.exists()
        assert json.loads(summary_path.read_text())["scenario_count"] == 5
