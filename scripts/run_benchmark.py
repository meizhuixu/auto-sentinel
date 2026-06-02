"""Full v1/v2 benchmark runner (T060, plan §Block 6).

Reads every scenario yaml under --scenarios, runs each through the v1 (single-
agent, mock-classify) and v2 (multi-agent) pipelines, and writes
benchmarks/results/{run_id}/results.jsonl (one BenchmarkResult per v2 scenario)
+ summary.json (contracts/benchmark-scenario.md "Output schema").

  run_id = YYYYMMDD-HHMMSS-{git_short_sha}

Cost governance (FR-519): the run uses the real CostGuard with the same env
budget as production. --budget sets AUTOSENTINEL_BUDGET_LIMIT_USD; if a real
run exceeds it, the multi-agent graph routes to its cost_exhausted node and the
runner aborts the whole benchmark with a typed CostGuardError rather than
silently dropping scenarios.

--use-mock injects MockLLMClient-backed agents (driven by each scenario's
ground-truth classification + verdict) via the build_multi_agent_graph(agents=)
seam, so the smoke run costs $0 and reaches no real provider. All autosentinel
imports are deferred until after env setup so --use-mock works without real
API keys.

Usage:
    python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 20.6 --use-mock
    python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 20.6   # real, costs money
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional


def _git_short_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "nogit"


def _percentile(values: list[int], pct: float) -> int:
    """Linear-interpolated percentile over an int list (empty -> 0)."""
    if not values:
        return 0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * pct / 100.0
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    if lo == hi:
        return s[lo]
    return int(round(s[lo] + (s[hi] - s[lo]) * (k - lo)))


def _build_mock_agents(scenario) -> dict:
    """Per-scenario MockLLMClient agents driven by the scenario's ground truth.

    diagnosis -> expected_classification; supervisor -> the specialist the
    category routes to; code_fixer/infra_sre -> the resolution action (a safe
    string, no deny-list keyword); security_reviewer -> expected_security_verdict.
    The real VerifierAgent is used (Docker), matching the production topology.
    """
    from autosentinel.agents.code_fixer import CodeFixerAgent
    from autosentinel.agents.diagnosis import DiagnosisAgent
    from autosentinel.agents.infra_sre import InfraSREAgent
    from autosentinel.agents.security_reviewer import SecurityReviewerAgent
    from autosentinel.agents.supervisor import SupervisorAgent
    from autosentinel.agents.verifier import VerifierAgent
    from autosentinel.llm.factory import AgentModelConfig
    from autosentinel.llm.mock_client import MockLLMClient
    from autosentinel.llm.protocol import LLMResponse

    def _client(content: str):
        resp = LLMResponse(
            content=content, model="mock", prompt_tokens=1, completion_tokens=1,
            cost_usd=Decimal("0"), latency_ms=0, trace_id="0" * 32,
        )
        return MockLLMClient().with_fixture_response(resp)

    cfg = AgentModelConfig(model="mock", temperature=0.0, max_tokens=512)
    classification = scenario.expected_classification
    specialist = "infra_sre" if classification in ("INFRA", "CONFIG") else "code_fixer"

    return {
        "diagnosis": DiagnosisAgent(
            llm_client=_client(json.dumps(
                {"category": classification, "reasoning": "benchmark mock"})),
            model_config=cfg),
        "supervisor": SupervisorAgent(
            llm_client=_client(json.dumps(
                {"specialist": specialist, "rationale": "benchmark mock routing"})),
            model_config=cfg),
        "code_fixer": CodeFixerAgent(
            llm_client=_client(scenario.expected_resolution_action), model_config=cfg),
        "infra_sre": InfraSREAgent(
            llm_client=_client(scenario.expected_resolution_action), model_config=cfg),
        "security_reviewer": SecurityReviewerAgent(
            llm_client=_client(json.dumps(
                {"verdict": scenario.expected_security_verdict,
                 "reasoning": "benchmark mock"})),
            model_config=cfg),
        "verifier": VerifierAgent(),
    }


def _run_v1(scenario) -> tuple[bool, int]:
    """Run the v1 single-agent pipeline (mock-classify, $0 LLM). Returns
    (resolved, latency_ms). Exceptions (e.g. Docker unavailable) -> unresolved."""
    from autosentinel import run_pipeline

    prev = os.environ.pop("AUTOSENTINEL_MULTI_AGENT", None)
    start = time.monotonic()
    resolved = True
    try:
        run_pipeline(scenario.error_log_path)
    except Exception:
        resolved = False
    finally:
        if prev is not None:
            os.environ["AUTOSENTINEL_MULTI_AGENT"] = prev
    return resolved, int((time.monotonic() - start) * 1000)


def _run_v2(scenario, *, use_mock: bool):
    """Run the v2 multi-agent pipeline. Returns (BenchmarkResult, verdict).

    Raises CostGuardError if the run trips the budget (FR-519)."""
    from langgraph.types import Command

    from autosentinel.benchmark import BenchmarkResult
    from autosentinel.llm.cost_guard import get_cost_guard
    from autosentinel.llm.errors import CostGuardError
    from autosentinel.models import AgentState
    from autosentinel.multi_agent_graph import build_multi_agent_graph

    agents = _build_mock_agents(scenario) if use_mock else None
    graph = build_multi_agent_graph(agents=agents)

    trace_id = secrets.token_hex(16)
    cfg = {"configurable": {"thread_id": f"bench-{scenario.scenario_id}-{uuid.uuid4()}"}}
    state = AgentState(
        log_path=str(scenario.error_log_path),
        error_log=None, parse_error=None,
        analysis_result=None, analysis_error=None,
        fix_script=None, execution_result=None, execution_error=None,
        report_text=None, report_path=None,
        error_category=None, fix_artifact=None,
        security_verdict=None, routing_decision=None, specialist=None,
        agent_trace=[], approval_required=False,
        trace_id=trace_id, cost_accumulated_usd=0.0,
    )

    cost_before = get_cost_guard().state.total_spent_usd
    start = time.monotonic()
    error: Optional[str] = None
    result: dict = {}
    try:
        result = graph.invoke(state, cfg)
        if "__interrupt__" in result:
            result = graph.invoke(Command(resume="approved"), cfg)
    except Exception as e:  # noqa: BLE001 - record per-scenario failure
        error = f"{type(e).__name__}: {e}"
    latency_ms = int((time.monotonic() - start) * 1000)
    cost_usd = get_cost_guard().state.total_spent_usd - cost_before

    # FR-519: a tripped budget aborts the whole run with the typed error.
    if result.get("cost_exhausted") or "cost_guard_triggered" in result.get("agent_trace", []):
        raise CostGuardError(
            current_spent_usd=get_cost_guard().state.total_spent_usd,
            attempted_amount_usd=Decimal("0"),
            budget_limit_usd=get_cost_guard().budget_limit_usd,
        )

    verdict = result.get("security_verdict")
    resolved = result.get("report_text") is not None and result.get("execution_error") is None
    benchmark_result = BenchmarkResult(
        scenario_id=scenario.scenario_id,
        actual_classification=result.get("error_category") or "UNKNOWN",
        actual_resolution=(result.get("fix_artifact") or "(none)")[:200],
        passed=resolved,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        trace_id=trace_id,
        error=error,
    )
    return benchmark_result, verdict


def run(
    *,
    scenarios_dir: Path,
    budget: str,
    use_mock: bool,
    only: Optional[set[str]] = None,
    output_root: Path = Path("benchmarks/results"),
) -> dict:
    """Run the benchmark; write results.jsonl + summary.json; return summary."""
    os.environ["AUTOSENTINEL_BUDGET_LIMIT_USD"] = str(budget)
    if use_mock:
        # Allow a $0 run without real keys; the injected mock agents never call
        # the concrete clients these placeholder keys would configure.
        os.environ.setdefault("ARK_API_KEY", "mock-key")
        os.environ.setdefault("GLM_API_KEY", "mock-key")

    # Deferred imports: env (budget + keys) must be set before the
    # multi_agent_graph module builds its production singletons at import.
    from autosentinel.benchmark import _load_scenarios
    import autosentinel.llm.cost_guard as cost_guard_mod

    cost_guard_mod._singleton = None  # fresh CostGuard reads the budget above

    scenarios = _load_scenarios(scenarios_dir)
    if only is not None:
        scenarios = [s for s in scenarios if s.scenario_id in only]

    v1_latencies: list[int] = []
    v1_resolved = 0
    v2_results = []
    v2_verdicts: dict[str, Optional[str]] = {}

    for scenario in scenarios:
        resolved, v1_lat = _run_v1(scenario)
        v1_latencies.append(v1_lat)
        v1_resolved += 1 if resolved else 0

        result, verdict = _run_v2(scenario, use_mock=use_mock)
        v2_results.append(result)
        v2_verdicts[scenario.scenario_id] = verdict

    n = len(scenarios)
    v2_latencies = [r.latency_ms for r in v2_results]
    v2_passed = sum(1 for r in v2_results if r.passed)
    v2_cost_total = sum((r.cost_usd for r in v2_results), Decimal("0"))

    # SC-013: false negative = SECURITY-category, HIGH_RISK ground truth, but the
    # pipeline returned a non-HIGH_RISK verdict.
    by_id = {s.scenario_id: s for s in scenarios}
    security = [s for s in scenarios if s.category == "SECURITY"]
    false_neg_ids = [
        s.scenario_id for s in security
        if s.expected_security_verdict == "HIGH_RISK"
        and v2_verdicts.get(s.scenario_id) != "HIGH_RISK"
    ]

    category_distribution = {
        cat: sum(1 for s in scenarios if s.category == cat)
        for cat in ("CODE", "INFRA", "SECURITY", "CONFIG")
    }

    run_id = f"{datetime.now(timezone.utc):%Y%m%d-%H%M%S}-{_git_short_sha()}"
    summary = {
        "run_id": run_id,
        "scenario_count": n,
        "category_distribution": category_distribution,
        "v1": {
            "latency_ms": {"p50": _percentile(v1_latencies, 50),
                           "p95": _percentile(v1_latencies, 95)},
            "total_cost_usd": str(Decimal("0")),  # v1 is mock-classify, no LLM spend
            "resolution_rate": round(v1_resolved / n, 2) if n else 0.0,
        },
        "v2": {
            "latency_ms": {"p50": _percentile(v2_latencies, 50),
                           "p95": _percentile(v2_latencies, 95)},
            "total_cost_usd": str(v2_cost_total),
            "resolution_rate": round(v2_passed / n, 2) if n else 0.0,
        },
        "security_subset": {
            "count": len(security),
            "v2_false_negative_count": len(false_neg_ids),
            "v2_false_negative_scenario_ids": false_neg_ids,
        },
    }

    out_dir = output_root / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.jsonl").open("w", encoding="utf-8") as fh:
        for r in v2_results:
            fh.write(json.dumps(r.model_dump(mode="json")) + "\n")
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="AutoSentinel v1/v2 benchmark runner")
    parser.add_argument("--scenarios", type=Path, required=True,
                        help="directory of scenario yaml files")
    parser.add_argument("--budget", default="20.6",
                        help="per-run LLM budget in USD (AUTOSENTINEL_BUDGET_LIMIT_USD)")
    parser.add_argument("--use-mock", action="store_true",
                        help="inject MockLLMClient agents ($0, no real provider)")
    args = parser.parse_args(argv)

    summary = run(scenarios_dir=args.scenarios, budget=args.budget, use_mock=args.use_mock)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
