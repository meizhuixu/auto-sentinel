"""T041 [US3] [PR-4] — CostGuard aborts the pipeline cleanly before Verifier.

Budget floor = $0.001; every LLM call costs $0.0005. With the strict-`>`
threshold the cumulative spend trips on the 3rd call (0.0015 > 0.001), so a
specialist's complete() raises CostGuardError. The graph must route to
``cost_exhausted_node`` (END) rather than propagate the error out of invoke():

  (a) CostGuardError is intercepted (not raised out of graph.invoke)
  (b) the Verifier never runs (no execution_result)
  (c) state["agent_trace"][-1] == "cost_guard_triggered"
  (d) state["cost_accumulated_usd"] mirrors the CostGuard Decimal snapshot
  (e) the float mirror equals the Decimal source of truth (drift check)

Hermetic: injects a test-local cost-accumulating mock; never touches the
production factory; never spends real budget.

FAILING until: cost_exhausted_node (T042) + CostGuardError interception (T043)
+ the build_multi_agent_graph(*, checkpointer=, agents=) seam (D2) land.
"""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

from autosentinel.llm.cost_guard import get_cost_guard
from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.integration._pr4_helpers import (
    ZERO_TRACE_ID,
    CostAccumulatingMock,
    build_injected_agents,
    force_budget,
    setup_docker_success,
)


def _write_log(tmp_path: Path) -> Path:
    log = tmp_path / "cost.json"
    log.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-29T00:00:00Z",
                "service_name": "svc",
                "error_type": "RuntimeError",
                "message": "boom",
                "stack_trace": None,
            }
        )
    )
    return log


def _initial_state(log_file: Path) -> dict:
    return {
        "log_path": str(log_file),
        "error_log": None,
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "fix_script": None,
        "execution_result": None,
        "execution_error": None,
        "report_text": None,
        "report_path": None,
        "error_category": None,
        "fix_artifact": None,
        "security_verdict": None,
        "routing_decision": None,
        "specialist": None,
        "agent_trace": [],
        "approval_required": False,
        "trace_id": ZERO_TRACE_ID,
        "cost_accumulated_usd": 0.0,
    }


def _accumulating_clients(cost_usd: Decimal) -> dict[str, object]:
    contents = {
        "diagnosis": '{"category": "CODE", "reasoning": "x"}',
        "supervisor": '{"specialist": "code_fixer", "rationale": "x"}',
        "code_fixer": 'print("fix")',
        "infra_sre": 'print("fix")',
        "security_reviewer": '{"verdict": "SAFE", "reasoning": "x"}',
    }
    return {
        name: CostAccumulatingMock(content=content, cost_usd=cost_usd)
        for name, content in contents.items()
    }


def test_cost_guard_aborts_pipeline_before_verifier(tmp_path, monkeypatch):
    force_budget(monkeypatch, "0.001")
    per_call = Decimal("0.0005")

    clients = _accumulating_clients(per_call)
    agents = build_injected_agents(clients)
    graph = build_multi_agent_graph(checkpointer=MemorySaver(), agents=agents)

    log = _write_log(tmp_path)
    cfg = {"configurable": {"thread_id": "t041-" + uuid.uuid4().hex}}

    with patch("autosentinel.agents.verifier.docker") as md:
        setup_docker_success(md)
        # (a) CostGuardError is intercepted by the graph, not raised here.
        result = graph.invoke(_initial_state(log), cfg)

    # (c) pipeline ended in the cost-exhausted node
    assert result["agent_trace"][-1] == "cost_guard_triggered"
    # (b) Verifier never ran
    assert result.get("execution_result") is None
    assert "VerifierAgent" not in result["agent_trace"]

    # Trip happened on the 3rd accumulate (0.0005 * 3 = 0.0015 > 0.001).
    guard_total = get_cost_guard().state.total_spent_usd
    assert guard_total == Decimal("0.0015")
    # (d) state mirror matches the Decimal snapshot; (e) no float/Decimal drift
    assert result["cost_accumulated_usd"] == pytest.approx(float(guard_total))
