"""Shared PR-4 integration-test helpers.

PR-4 tests are hermetic: they inject their own test-local LLM clients into the
multi-agent graph via the as-built `build_multi_agent_graph(*, checkpointer=,
agents=)` injection seam (D2). They never touch the production factory, never
hit a real provider, and never spend budget. See specs/005-real-llm-integration
PR-4 plan + the Sprint-5 collaboration notes.

Two test-local client doubles live here:

* ``RecordingMock`` — captures the ``trace_id`` / ``agent_name`` of every
  ``complete()`` call. Returns per-agent canned content so each agent's parser
  is satisfied. Used by T044 trace-propagation.
* ``CostAccumulatingMock`` — mirrors the real ``ArkLLMClient`` Step-6 contract
  (``get_cost_guard().accumulate(cost_usd)`` on every call). The shared
  ``MockLLMClient`` deliberately does NOT accumulate, so T041 needs this double
  to drive the global CostGuard to its ceiling through the graph.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest

from autosentinel.agents.code_fixer import CodeFixerAgent
from autosentinel.agents.diagnosis import DiagnosisAgent
from autosentinel.agents.infra_sre import InfraSREAgent
from autosentinel.agents.security_reviewer import SecurityReviewerAgent
from autosentinel.agents.supervisor import SupervisorAgent
from autosentinel.agents.verifier import VerifierAgent
from autosentinel.llm.cost_guard import get_cost_guard
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient
from autosentinel.llm.protocol import LLMRequest, LLMResponse, Message

# Local-dev checkpointer DSN (infra/docker-compose.checkpointer.yml, port 5434).
CHECKPOINTER_DSN = "postgresql://postgres:postgres@localhost:5434/postgres"

# Valid 32-char lowercase hex — passes LLMRequest.trace_id regex.
ZERO_TRACE_ID = "0" * 32

# Canned per-agent content so each agent's response parser is satisfied.
_AGENT_CONTENT = {
    "diagnosis": '{"category": "CODE", "reasoning": "test"}',
    "supervisor": '{"specialist": "code_fixer", "rationale": "test"}',
    "code_fixer": 'print("test fix")',
    "infra_sre": 'print("test infra fix")',
    "security_reviewer": '{"verdict": "SAFE", "reasoning": "test"}',
}


def _mk_response(content: str, trace_id: str, cost: Decimal) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="test-model",
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=cost,
        latency_ms=0,
        trace_id=trace_id,
    )


def _cfg() -> AgentModelConfig:
    return AgentModelConfig(model="test-model", temperature=0.0, max_tokens=512)


def build_injected_agents(clients: dict[str, object]) -> dict[str, object]:
    """Assemble the 6-agent dict consumed by build_multi_agent_graph(agents=).

    `clients` maps the 5 LLM-call agent names to an LLMClient double. The
    Verifier takes no client.
    """
    return {
        "diagnosis": DiagnosisAgent(llm_client=clients["diagnosis"], model_config=_cfg()),
        "supervisor": SupervisorAgent(llm_client=clients["supervisor"], model_config=_cfg()),
        "code_fixer": CodeFixerAgent(llm_client=clients["code_fixer"], model_config=_cfg()),
        "infra_sre": InfraSREAgent(llm_client=clients["infra_sre"], model_config=_cfg()),
        "security_reviewer": SecurityReviewerAgent(
            llm_client=clients["security_reviewer"], model_config=_cfg()
        ),
        "verifier": VerifierAgent(),
    }


def build_fixture_clients(*, code_fixer_artifact: str = 'print("test fix")') -> dict[str, object]:
    """Five MockLLMClients pre-loaded with canned per-agent responses.

    `code_fixer_artifact` overrides the CodeFixer fix body — pass a deny-listed
    string (e.g. "DROP TABLE users") to force a HIGH_RISK verdict via the
    SecurityReviewer deny-list override.
    """
    contents = dict(_AGENT_CONTENT)
    contents["code_fixer"] = code_fixer_artifact
    return {
        name: MockLLMClient().with_fixture_response(
            _mk_response(content, ZERO_TRACE_ID, Decimal("0"))
        )
        for name, content in contents.items()
    }


class RecordingMock:
    """LLMClient double that records every complete() call's trace_id."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (agent_name, trace_id)

    def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        trace_id: str,
        agent_name: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        # Validate trace_id shape exactly like the real clients (VII.3).
        LLMRequest(
            messages=messages,
            model=model,
            trace_id=trace_id,
            agent_name=agent_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self.calls.append((agent_name, trace_id))
        content = _AGENT_CONTENT.get(agent_name, '{"category": "CODE"}')
        return _mk_response(content, trace_id, Decimal("0"))


class CostAccumulatingMock:
    """LLMClient double mirroring ArkLLMClient Step-6: accumulate cost_usd
    through the global CostGuard on every complete() call (may raise
    CostGuardError)."""

    def __init__(self, *, content: str, cost_usd: Decimal) -> None:
        self._content = content
        self._cost = cost_usd
        self.call_count = 0

    def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        trace_id: str,
        agent_name: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        LLMRequest(
            messages=messages,
            model=model,
            trace_id=trace_id,
            agent_name=agent_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        self.call_count += 1
        resp = _mk_response(self._content, trace_id, self._cost)
        # Step 6: accumulate AFTER building the response (caller has it in hand).
        get_cost_guard().accumulate(self._cost)
        return resp


def force_budget(monkeypatch, limit_usd: str) -> None:
    """Rebuild the CostGuard singleton with a low test budget.

    The singleton caches its budget at first construction, so setting the env
    var alone is insufficient — we null the cached singleton and let the next
    get_cost_guard() rebuild it from the env value.
    """
    monkeypatch.setenv("AUTOSENTINEL_BUDGET_LIMIT_USD", limit_usd)
    monkeypatch.setattr("autosentinel.llm.cost_guard._singleton", None)


def setup_docker_success(mock_docker) -> None:
    """Configure a docker mock simulating a successful container run."""
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.containers.run.return_value = mock_container
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = [b"Fix applied\n", b""]


def checkpointer_available() -> bool:
    """True if the local PostgresSaver container is reachable on :5434."""
    try:
        import psycopg

        with psycopg.connect(CHECKPOINTER_DSN, connect_timeout=2):
            return True
    except Exception:
        return False


requires_checkpointer = pytest.mark.skipif(
    not checkpointer_available(),
    reason="PostgresSaver container not reachable on localhost:5434 "
    "(start: docker compose -f infra/docker-compose.checkpointer.yml up -d)",
)
