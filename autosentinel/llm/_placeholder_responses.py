"""PR-2 transitional placeholder LLMResponse fixtures.

Used by factory.build_client_for_agent() to wire MockLLMClient instances
into the production graph (multi_agent_graph.py module-level singletons)
during the window between batch 3b (agent bodies call .complete()) and
PR-3 (ArkLLMClient / GlmLLMClient ship). Without these, the production
graph would crash on the first specialist run because a bare
MockLLMClient.complete() raises by contract.

DELETE this module when factory dispatch wires real concrete clients.
"""

from __future__ import annotations

from decimal import Decimal

from autosentinel.llm.protocol import LLMResponse


_PLACEHOLDER_TRACE_ID = "0" * 32


def _placeholder(content: str, model: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model=model,
        prompt_tokens=1,
        completion_tokens=1,
        cost_usd=Decimal("0"),
        latency_ms=0,
        trace_id=_PLACEHOLDER_TRACE_ID,
    )


_RESPONSES: dict[str, LLMResponse] = {
    "diagnosis": _placeholder(
        '{"category": "CODE", "reasoning": "placeholder"}',
        "doubao-seed-2.0-pro",
    ),
    "supervisor": _placeholder(
        '{"route": "code_fixer", "reasoning": "placeholder"}',
        "doubao-1.5-lite-32k",
    ),
    "code_fixer": _placeholder(
        'print("placeholder fix")',
        "doubao-seed-2.0-pro",
    ),
    "infra_sre": _placeholder(
        'print("placeholder infra fix")',
        "doubao-seed-2.0-pro",
    ),
    "security_reviewer": _placeholder(
        '{"verdict": "SAFE", "reasoning": "placeholder"}',
        "glm-4.7",
    ),
}


def get_placeholder_response(agent_name: str) -> LLMResponse:
    """Return the placeholder LLMResponse for a given agent name.

    Raises KeyError if agent_name is unknown — factory should pass a
    name already validated against model_routing.yaml.
    """
    return _RESPONSES[agent_name]
