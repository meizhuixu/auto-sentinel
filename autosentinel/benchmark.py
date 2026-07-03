"""Smoke benchmark — runs the migrated scenarios through the multi-agent pipeline.

Scenarios are sourced from yaml files under `benchmarks/scenarios/` (loaded
via the BenchmarkScenario schema below), NOT from an inline list — FR-516.

Sprint 6 (006-fix-verification-integrity US4): the v1 comparison arm is
retired — this runner measures only the production multi-agent pipeline.

SEMANTIC DECISION (carried over from Sprint 4, tightened in Sprint 6):
"resolved" means HIGH_RISK + approval handled AND the fix VERIFIABLY SUCCEEDED
in the sandbox (execution_result.status == 'success'); report presence alone
no longer counts (006 data-model.md §3). LangGraph interrupt() is a designed
control flow (SC-003), not a failure; the full agent_trace (including
SecurityReviewerAgent and VerifierAgent post-approval) is recorded for audit.

This module is the CI-runnable smoke runner (writes output/benchmark-report.json).
The full 50-scenario runner with results.jsonl + summary.json is
scripts/run_benchmark.py (T060).
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Literal, Optional

import yaml
from langgraph.types import Command
from pydantic import BaseModel, Field

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
    cost: Decimal = Field(ge=Decimal("0"))
    currency: str = "CNY"               # native billing currency of the run
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
        # Sprint 6 tightened definition (006 data-model.md §3): the fix must
        # have verifiably succeeded in the sandbox, not merely produced a report.
        execution_result = final_result.get("execution_result")
        execution_status = (
            execution_result.get("status") if isinstance(execution_result, dict)
            else getattr(execution_result, "status", None)
        )
        resolved = (
            final_result.get("report_text") is not None
            and execution_status == "success"
        )
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
    """Run the migrated smoke scenarios through the pipeline; write JSON report.

    Scenarios are globbed from yaml (benchmarks/scenarios/) and reference their
    own on-disk log fixtures via `error_log_path` — nothing is written here.
    """
    scenarios = _load_scenarios(scenarios_dir)

    scenario_details = []
    results: list[dict] = []

    for scenario in scenarios:
        log_path = scenario.error_log_path
        detail = _run_v2_detail(scenario, log_path)
        results.append(detail)
        scenario_details.append({
            "id": scenario.scenario_id,
            "category": scenario.category,
            "resolved": detail["resolved"],
            "duration_ms": detail["duration_ms"],
            "agent_trace": detail["agent_trace"],
            "security_verdict": detail["security_verdict"],
            "routing_decision": detail["routing_decision"],
            "was_interrupted": detail["was_interrupted"],
        })

    count = len(scenarios)
    resolved_count = sum(1 for r in results if r["resolved"])
    avg_ms = int(sum(r["duration_ms"] for r in results) / count)

    report = {
        "scenario_count": count,
        "resolution_rate": round(resolved_count / count, 2),
        "avg_ms": avg_ms,
        "resolved_definition": (
            "report_text present AND execution_result.status == 'success'"
        ),
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
