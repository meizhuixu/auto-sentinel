"""Contract tests for autosentinel/llm/protocol.py — Message / LLMRequest /
LLMResponse Pydantic v2 schemas (data-model.md §1-3).

Today (T008 commit) every test errors on collection because protocol.py
does not exist yet. T014 implements the schemas and turns this file GREEN.

4 cases per contracts/llm-client.md "Coverage & test surface":
  1. LLMRequest accepts a valid 32-char hex trace_id
  2. LLMRequest rejects empty / malformed trace_id with ValueError
  3. LLMResponse rejects negative prompt_tokens / completion_tokens / cost_usd
  4. Message is frozen (mutation raises ValidationError)
"""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from autosentinel.llm.protocol import LLMRequest, LLMResponse, Message


VALID_TRACE_ID = "0123456789abcdef0123456789abcdef"  # 32-char lowercase hex


def _valid_request_kwargs(**overrides) -> dict:
    base = {
        "messages": [Message(role="user", content="hi")],
        "model": "doubao-seed-2.0-pro",
        "temperature": 0.2,
        "max_tokens": 1024,
        "trace_id": VALID_TRACE_ID,
        "agent_name": "diagnosis",
    }
    base.update(overrides)
    return base


def _valid_response_kwargs(**overrides) -> dict:
    base = {
        "content": "ok",
        "model": "doubao-seed-2.0-pro",
        "prompt_tokens": 12,
        "completion_tokens": 34,
        "cost_usd": Decimal("0.001"),
        "latency_ms": 250,
        "trace_id": VALID_TRACE_ID,
    }
    base.update(overrides)
    return base


def test_llm_request_accepts_valid_trace_id():
    req = LLMRequest(**_valid_request_kwargs())
    assert req.trace_id == VALID_TRACE_ID
    assert req.agent_name == "diagnosis"
    assert req.messages[0].content == "hi"


@pytest.mark.parametrize(
    "bad_trace_id",
    [
        "",
        "GGGGGGGGGGGGGGGGGGGGGGGGGGGGGGGG",  # not hex
        "0123456789ABCDEF0123456789ABCDEF",  # uppercase rejected
        "0123",  # too short
        "0123456789abcdef0123456789abcdef0",  # too long (33 chars)
        "0123456789abcdef 123456789abcdef",  # space
    ],
)
def test_llm_request_rejects_invalid_trace_id(bad_trace_id):
    with pytest.raises(ValidationError):
        LLMRequest(**_valid_request_kwargs(trace_id=bad_trace_id))


@pytest.mark.parametrize(
    "field, bad_value",
    [
        ("prompt_tokens", -1),
        ("completion_tokens", -1),
        ("cost_usd", Decimal("-0.0001")),
    ],
)
def test_llm_response_rejects_negative_fields(field, bad_value):
    with pytest.raises(ValidationError):
        LLMResponse(**_valid_response_kwargs(**{field: bad_value}))


def test_message_is_frozen():
    m = Message(role="user", content="hi")
    with pytest.raises(ValidationError):
        m.content = "changed"  # type: ignore[misc]
