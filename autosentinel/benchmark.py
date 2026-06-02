"""Smoke benchmark — runs the migrated scenarios through v1 and v2 pipelines.

Scenarios are sourced from yaml files under `benchmarks/scenarios/` (loaded
via the BenchmarkScenario schema below), NOT from an inline list — FR-516.
T050 replaced the Sprint-4 inline `SCENARIOS: list[dict]` and the
`SPRINT4_MOCK_APPROVAL` constant with this yaml-driven runner; the HIGH_RISK
interrupt is now resumed with a plain approval token, since the real
CostGuard path preserves partial state across the interrupt.

SEMANTIC DECISION (carried over from Sprint 4): HIGH_RISK + approval +
verifier success counts as "resolved". LangGraph interrupt() is a designed
control flow (SC-003), not a failure; the full agent_trace (including
SecurityReviewerAgent and VerifierAgent post-approval) is recorded for audit.

This module is the CI-runnable smoke runner (writes output/benchmark-report.json
in the Sprint-4 schema). The full 50-scenario runner with results.jsonl +
summary.json is scripts/run_benchmark.py (T060).
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

import yaml
from langgraph.types import Command
from pydantic import BaseModel, Field

from autosentinel import run_pipeline
from autosentinel.models import AgentState
from autosentinel.multi_agent_graph import build_multi_agent_graph


# ──────────────────────────────────────────────────────────────────────────
# Benchmark schemas (T048, data-model.md §9). PR-5 T050 rewrites the runner
# below to load yaml scenarios into BenchmarkScenario and emit BenchmarkResult
# rows; these two models are the durable contract and stay put across that
# rewrite.
# ──────────────────────────────────────────────────────────────────────────


class BenchmarkScenario(BaseModel):
    model_config = {"frozen": True}

    scenario_id: str = Field(pattern=r"^\d{3}_[a-z]+_[a-z0-9_]+$")  # e.g. 001_code_null_pointer
    category: Literal["CODE", "INFRA", "SECURITY", "CONFIG"]
    error_log_path: Path
    expected_classification: str        # ground-truth error_category
    expected_resolution_action: str     # short prose label
    # Ground-truth security verdict (FR-517 "expected security verdict"). The
    # structured carrier for the SC-013 / Constitution Principle V invariant —
    # mirrors the verdict adjudicated in ground_truth_notes. HIGH_RISK iff the
    # remediation touches a sensitive surface, independent of `category`.
    expected_security_verdict: Literal["SAFE", "CAUTION", "HIGH_RISK"]
    ground_truth_notes: str             # free-form rationale
    human_labeled_by: str = Field(min_length=1)
    labeled_at: date


class BenchmarkResult(BaseModel):
    model_config = {"frozen": True}

    scenario_id: str
    actual_classification: str
    actual_resolution: str
    passed: bool
    latency_ms: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    trace_id: str
    error: Optional[str] = None         # populated if pipeline raised before Verifier


# ──────────────────────────────────────────────────────────────────────────
# Scenario loading (FR-516: scenarios live in yaml under benchmarks/scenarios/,
# not inline in this runner). Repo-anchored so the glob is stable regardless
# of the process CWD.
# ──────────────────────────────────────────────────────────────────────────

_DEFAULT_SCENARIOS_DIR = (
    Path(__file__).resolve().parent.parent / "benchmarks" / "scenarios"
)


def _load_scenarios(scenarios_dir: Path | None = None) -> list[BenchmarkScenario]:
    """Load every `*.yaml` under the scenarios dir into a BenchmarkScenario.

    Files are read in sorted order so the report is deterministic; a malformed
    scenario surfaces as a pydantic ValidationError at load time.
    """
    directory = scenarios_dir or _DEFAULT_SCENARIOS_DIR
    scenarios: list[BenchmarkScenario] = []
    for path in sorted(directory.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        scenarios.append(BenchmarkScenario.model_validate(data))
    return scenarios


def _run_v1(log_path: Path) -> dict:
    """Run through v1 pipeline (AUTOSENTINEL_MULTI_AGENT unset); return {resolved, duration_ms}."""
    original = dict(os.environ)
    os.environ.pop("AUTOSENTINEL_MULTI_AGENT", None)
    resolved = True
    start = time.monotonic()
    try:
        run_pipeline(log_path)
    except Exception:
        resolved = False
    finally:
        os.environ.clear()
        os.environ.update(original)
    return {"resolved": resolved, "duration_ms": int((time.monotonic() - start) * 1000)}


def _run_v2_detail(scenario: BenchmarkScenario, log_path: Path) -> dict:
    """Run through v2 graph directly; detect interrupt; return full detail dict.

    A SECURITY-class fix artifact trips SecurityReviewerAgent's deny-list /
    HIGH_RISK verdict, firing interrupt() via security_gate. was_interrupted=True
    is hard evidence SC-003 fires; the run is then resumed with a plain approval
    token (the real CostGuard path preserves partial state across the interrupt,
    so the Sprint-4 mock-approval payload is no longer needed).
    """
    was_interrupted = False
    final_result: dict = {}
    resolved = False
    start = time.monotonic()
    try:
        graph = build_multi_agent_graph()
        thread_id = f"benchmark-{scenario.scenario_id}-{uuid.uuid4()}"
        config = {"configurable": {"thread_id": thread_id}}
        initial_state = AgentState(
            log_path=str(log_path),
            error_log=None, parse_error=None,
            analysis_result=None, analysis_error=None,
            fix_script=None, execution_result=None, execution_error=None,
            report_text=None, report_path=None,
            error_category=None, fix_artifact=None,
            security_verdict=None, routing_decision=None,
            specialist=None,
            agent_trace=[], approval_required=False,
        )
        first_result = graph.invoke(initial_state, config)
        was_interrupted = "__interrupt__" in first_result
        if was_interrupted:
            # Resume past the HIGH_RISK gate; upstream nodes do not re-run.
            final_result = graph.invoke(Command(resume="approved"), config)
        else:
            final_result = first_result
        resolved = final_result.get("report_text") is not None
    except Exception:
        pass  # resolved=False, was_interrupted keeps value set before exception
    duration_ms = int((time.monotonic() - start) * 1000)
    return {
        "resolved": resolved,
        "duration_ms": duration_ms,
        "agent_trace": final_result.get("agent_trace", []),
        "security_verdict": final_result.get("security_verdict"),
        "routing_decision": final_result.get("routing_decision"),
        "was_interrupted": was_interrupted,
    }


def run_benchmark(scenarios_dir: Path | None = None) -> dict:
    """Run the migrated smoke scenarios through v1 and v2; write JSON report.

    Scenarios are globbed from yaml (benchmarks/scenarios/) and reference their
    own on-disk log fixtures via `error_log_path` — nothing is written here.
    """
    scenarios = _load_scenarios(scenarios_dir)

    scenario_details = []
    v1_results: list[dict] = []
    v2_results: list[dict] = []

    for scenario in scenarios:
        log_path = scenario.error_log_path
        v1 = _run_v1(log_path)
        v2 = _run_v2_detail(scenario, log_path)
        v1_results.append(v1)
        v2_results.append(v2)
        scenario_details.append({
            "id": scenario.scenario_id,
            "category": scenario.category,
            "v1": {"resolved": v1["resolved"], "duration_ms": v1["duration_ms"]},
            "v2": {
                "resolved": v2["resolved"],
                "duration_ms": v2["duration_ms"],
                "agent_trace": v2["agent_trace"],
                "security_verdict": v2["security_verdict"],
                "routing_decision": v2["routing_decision"],
                "was_interrupted": v2["was_interrupted"],
            },
        })

    count = len(scenarios)
    v1_resolved = sum(1 for r in v1_results if r["resolved"])
    v2_resolved = sum(1 for r in v2_results if r["resolved"])
    v1_avg_ms = int(sum(r["duration_ms"] for r in v1_results) / count)
    v2_avg_ms = int(sum(r["duration_ms"] for r in v2_results) / count)

    report = {
        "scenario_count": count,
        "v1_resolution_rate": round(v1_resolved / count, 2),
        "v2_resolution_rate": round(v2_resolved / count, 2),
        "v1_avg_ms": v1_avg_ms,
        "v2_avg_ms": v2_avg_ms,
        "scenarios": scenario_details,
    }

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "benchmark-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    result = run_benchmark()
    print(json.dumps(result, indent=2))
