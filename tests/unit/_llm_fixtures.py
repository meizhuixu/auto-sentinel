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
        cost_usd=Decimal("0.0003"),
        latency_ms=400,
        trace_id=_DEFAULT_TRACE_ID,
    )


def code_fixer_fixture() -> LLMResponse:
    return LLMResponse(
        content='print("mock code fix")',
        model="mock-code-fixer",
        prompt_tokens=90,
        completion_tokens=25,
        cost_usd=Decimal("0.0004"),
        latency_ms=500,
        trace_id=_DEFAULT_TRACE_ID,
    )


def infra_sre_fixture() -> LLMResponse:
    return LLMResponse(
        content='print("mock infra fix")',
        model="mock-infra-sre",
        prompt_tokens=90,
        completion_tokens=25,
        cost_usd=Decimal("0.0004"),
        latency_ms=500,
        trace_id=_DEFAULT_TRACE_ID,
    )


def safe_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "SAFE", "reasoning": "no destructive ops"}',
        model="glm-4.7",
        prompt_tokens=100,
        completion_tokens=30,
        cost_usd=Decimal("0.0005"),
        latency_ms=500,
        trace_id=_DEFAULT_TRACE_ID,
    )


def high_risk_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "HIGH_RISK", "reasoning": "DROP TABLE detected"}',
        model="glm-4.7",
        prompt_tokens=120,
        completion_tokens=40,
        cost_usd=Decimal("0.0008"),
        latency_ms=850,
        trace_id=_DEFAULT_TRACE_ID,
    )


def caution_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "CAUTION", "reasoning": "ambiguous shell command"}',
        model="glm-4.7",
        prompt_tokens=110,
        completion_tokens=35,
        cost_usd=Decimal("0.0006"),
        latency_ms=700,
        trace_id=_DEFAULT_TRACE_ID,
    )
