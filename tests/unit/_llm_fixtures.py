"""Shared LLMResponse fixtures for agent wiring tests.

Centralised so that schema changes touch one file. Default trace_id is
"0" * 32 (32 lowercase hex chars per LLMRequest validator); callers can
override per-test by constructing their own LLMResponse if a specific
trace_id is needed.
"""

from __future__ import annotations

from decimal import Decimal

from autosentinel.llm.protocol import LLMResponse


_DEFAULT_TRACE_ID = "0" * 32


def diagnosis_fixture(category: str = "CODE") -> LLMResponse:
    return LLMResponse(
        content=f'{{"category": "{category}", "reasoning": "mock diagnosis"}}',
        model="mock-diagnosis",
        prompt_tokens=80,
        completion_tokens=20,
        cost=Decimal("0.0003"),
        latency_ms=400,
        trace_id=_DEFAULT_TRACE_ID,
    )


def supervisor_fixture(
    specialist: str = "code_fixer",
    rationale: str = "mock routing decision",
) -> LLMResponse:
    import json as _json

    return LLMResponse(
        content=_json.dumps({"specialist": specialist, "rationale": rationale}),
        model="mock-supervisor",
        prompt_tokens=70,
        completion_tokens=15,
        cost=Decimal("0.0002"),
        latency_ms=300,
        trace_id=_DEFAULT_TRACE_ID,
    )


def code_fixer_fixture() -> LLMResponse:
    return LLMResponse(
        content='print("mock code fix")',
        model="mock-code-fixer",
        prompt_tokens=90,
        completion_tokens=25,
        cost=Decimal("0.0004"),
        latency_ms=500,
        trace_id=_DEFAULT_TRACE_ID,
    )


def infra_sre_fixture() -> LLMResponse:
    return LLMResponse(
        content='print("mock infra fix")',
        model="mock-infra-sre",
        prompt_tokens=90,
        completion_tokens=25,
        cost=Decimal("0.0004"),
        latency_ms=500,
        trace_id=_DEFAULT_TRACE_ID,
    )


def safe_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "SAFE", "reasoning": "no destructive ops"}',
        model="glm-4.7",
        prompt_tokens=100,
        completion_tokens=30,
        cost=Decimal("0.0005"),
        latency_ms=500,
        trace_id=_DEFAULT_TRACE_ID,
    )


def high_risk_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "HIGH_RISK", "reasoning": "DROP TABLE detected"}',
        model="glm-4.7",
        prompt_tokens=120,
        completion_tokens=40,
        cost=Decimal("0.0008"),
        latency_ms=850,
        trace_id=_DEFAULT_TRACE_ID,
    )


def caution_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "CAUTION", "reasoning": "ambiguous shell command"}',
        model="glm-4.7",
        prompt_tokens=110,
        completion_tokens=35,
        cost=Decimal("0.0006"),
        latency_ms=700,
        trace_id=_DEFAULT_TRACE_ID,
    )


def script_fixture(content: str, model: str = "mock-code-fixer") -> LLMResponse:
    """LLMResponse whose content is an arbitrary fix-artifact script/fragment.

    Sprint 6 (006-fix-verification-integrity): producer compile()-validation
    tests need to control the artifact text precisely.
    """
    return LLMResponse(
        content=content,
        model=model,
        prompt_tokens=90,
        completion_tokens=25,
        cost=Decimal("0.0004"),
        latency_ms=500,
        trace_id=_DEFAULT_TRACE_ID,
    )


class SequenceLLMClient:
    """LLMClient double returning a different response per complete() call.

    Sprint 6: MockLLMClient's fixture is persistent, which cannot exercise the
    producer-side "fragment first, valid script on retry" path. This double
    pops responses in order (repeating the last one when exhausted) and keeps
    every LLMRequest in `requests` for prompt-content assertions.
    """

    def __init__(self, responses: list[LLMResponse]) -> None:
        if not responses:
            raise ValueError("SequenceLLMClient needs at least one response")
        self._responses = list(responses)
        self.requests: list = []

    @property
    def call_count(self) -> int:
        return len(self.requests)

    @property
    def last_request(self):
        return self.requests[-1] if self.requests else None

    def complete(self, *, messages, model, trace_id, agent_name, max_tokens, temperature) -> LLMResponse:
        from autosentinel.llm.protocol import LLMRequest

        self.requests.append(LLMRequest(
            messages=messages,
            model=model,
            trace_id=trace_id,
            agent_name=agent_name,
            max_tokens=max_tokens,
            temperature=temperature,
        ))
        index = min(len(self.requests) - 1, len(self._responses) - 1)
        return self._responses[index]
