"""T040 holdout-set evaluation against real LLM (ArkClient + supervisor endpoint).

Loads data/routing-eval/held_out_v1.yaml, runs each incident through the
real SupervisorAgent (not MockLLMClient), prints per-incident routing
decisions and overall accuracy.

Run TWICE and paste both accuracy figures into the PR-3 commit message.

Usage:
    uv run python scripts/run_holdout_eval.py

Requires .env with ARK_API_KEY set.

Why this script constructs ArkLLMClient directly (rather than going through
build_client_for_agent()):
  PR-3-scoped minimum fix. The factory currently hands out a placeholder
  MockLLMClient (DEBT.md entry #1: "PR-3 first action"); making the factory
  dispatch on endpoint_alias also requires stripping 11 xfail(strict=True)
  markers across two integration test files, which is out of scope for T040.
  This script reads the same model_routing.yaml so model/temperature/
  max_tokens stay declarative and Constitution VII.4-compliant.
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import yaml
from dotenv import load_dotenv

from autosentinel.agents.supervisor import SupervisorAgent
from autosentinel.llm.ark_client import ArkLLMClient
from autosentinel.llm.factory import _load_routing_config
from autosentinel.models import AgentState


CATEGORY_TO_SPECIALIST = {
    "CODE": "code_fixer",
    "SECURITY": "code_fixer",
    "INFRA": "infra_sre",
    "CONFIG": "infra_sre",
}

YAML_PATH = (
    Path(__file__).resolve().parents[1]
    / "data" / "routing-eval" / "held_out_v1.yaml"
)


def _make_state(error_log_text: str) -> AgentState:
    state = AgentState(
        log_path="holdout_eval",
        error_log=None,
        parse_error=None,
        analysis_result=error_log_text,
        analysis_error=None,
        fix_script=None,
        execution_result=None,
        execution_error=None,
        report_text=None,
        report_path=None,
        error_category=None,
        fix_artifact=None,
        security_verdict=None,
        routing_decision=None,
        specialist=None,
        agent_trace=[],
        approval_required=False,
    )
    state["trace_id"] = secrets.token_hex(16)
    return state


def _build_real_supervisor() -> SupervisorAgent:
    routing = _load_routing_config()
    agent_cfg = routing.agents["supervisor"]
    endpoint_cfg = routing.endpoints[agent_cfg.endpoint_alias]
    api_key = os.environ.get(endpoint_cfg.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"{endpoint_cfg.api_key_env} not set in environment. "
            "Fill it in .env before running."
        )
    client = ArkLLMClient(
        api_key=api_key,
        base_url=str(endpoint_cfg.base_url).rstrip("/"),
    )
    return SupervisorAgent(llm_client=client, model_config=agent_cfg)


def main() -> None:
    load_dotenv(override=False)
    agent = _build_real_supervisor()

    data = yaml.safe_load(YAML_PATH.read_text())
    incidents = data["incidents"]
    hits = 0
    results = []

    for inc in incidents:
        state = _make_state(inc["error_log"])
        result = agent.run(state)
        actual = result.get("specialist") or "(none)"
        expected = CATEGORY_TO_SPECIALIST[inc["expected_category"]]
        ok = actual == expected
        if ok:
            hits += 1
        results.append((inc["id"], expected, actual, ok,
                        (result.get("routing_decision") or "")[:120]))

    print(f"\nHoldout eval — {YAML_PATH.name}")
    print("-" * 72)
    for rid, expected, actual, ok, rationale in results:
        marker = "✓" if ok else "✗"
        print(f"  {marker} {rid}: expected={expected:11s} actual={actual:11s}")
        print(f"      rationale: {rationale}")
    accuracy = hits / len(incidents)
    print("-" * 72)
    print(f"  accuracy = {hits}/{len(incidents)} = {accuracy:.1%}")
    print(f"  threshold = 70%  {'PASS' if accuracy >= 0.70 else 'FAIL'}\n")


if __name__ == "__main__":
    main()
