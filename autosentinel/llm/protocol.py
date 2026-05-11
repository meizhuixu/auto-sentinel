"""LLM client surface — provider-agnostic Pydantic schemas + Protocol.

Constitution VII.1 boundary: this module is provider-neutral. The OpenAI
SDK is imported only by the concrete clients in ark_client.py / glm_client.py
(allowlist enforced by tests/unit/test_llm_provider_isolation.py).

Schemas mirror data-model.md §1-3. The LLMClient Protocol mirrors
contracts/llm-client.md "Public surface" — sync, keyword-only.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator


_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


class Message(BaseModel):
    """One chat-completion turn. Frozen so agents can't mutate after handoff."""

    model_config = {"frozen": True}

    role: Literal["system", "user", "assistant"]
    content: str


class LLMRequest(BaseModel):
    """Internal request envelope built by concrete clients before SDK dispatch.

    Acts as the single validation gate for trace_id shape — empty / malformed
    trace_ids surface as Pydantic ValidationError unwrapped (Constitution VII.3).
    """

    model_config = {"frozen": True}

    messages: list[Message] = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=32_768)
    trace_id: str
    agent_name: str = Field(min_length=1)

    @field_validator("trace_id")
    @classmethod
    def _trace_id_shape(cls, v: str) -> str:
        if not _TRACE_ID_RE.fullmatch(v):
            raise ValueError(
                f"trace_id must be 32 lowercase hex chars; got {v!r}"
            )
        return v


class LLMResponse(BaseModel):
    """Provider-agnostic response. cost_usd is Decimal — never float — so it
    feeds CostGuard.accumulate() with exact arithmetic."""

    model_config = {"frozen": True}

    content: str
    model: str = Field(min_length=1)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    latency_ms: int = Field(ge=0)
    trace_id: str

    @model_validator(mode="after")
    def _trace_id_matches_request(self) -> "LLMResponse":
        if not _TRACE_ID_RE.fullmatch(self.trace_id):
            raise ValueError("LLMResponse trace_id malformed")
        return self


class LLMClient(Protocol):
    """Provider-agnostic client surface (T015).

    Concrete implementations: ArkLLMClient, GlmLLMClient, MockLLMClient.
    No additional public methods may be added — that would defeat provider
    portability (contracts/llm-client.md §"Public surface").
    """

    def complete(
        self,
        *,
        messages: list[Message],
        model: str,
        trace_id: str,
        agent_name: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse: ...
