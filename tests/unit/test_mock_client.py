"""Contract tests for autosentinel/llm/mock_client.py — the test double
that agent unit tests will inject in place of a real provider client
(contracts/llm-client.md "MockLLMClient contract").

Today (T011 commit) every test errors on collection because mock_client.py
does not exist yet. T020 implements and turns GREEN.

3 cases:
  1. with_fixture_response(resp) returns resp on .complete(...)
  2. with_error(exc) raises exc on .complete(...)
  3. call_count increments per call AND last_request mirrors the
     LLMRequest the client constructed from the kwargs
"""

from decimal import Decimal

import pytest

from autosentinel.llm.mock_client import MockLLMClient
from autosentinel.llm.protocol import LLMResponse, Message


VALID_TRACE_ID = "0123456789abcdef0123456789abcdef"


def _complete_kwargs(**overrides) -> dict:
    base = {
        "messages": [Message(role="user", content="hi")],
        "model": "doubao-seed-2.0-pro",
        "trace_id": VALID_TRACE_ID,
        "agent_name": "diagnosis",
        "max_tokens": 1024,
        "temperature": 0.2,
    }
    base.update(overrides)
    return base


def _fixture_response() -> LLMResponse:
    return LLMResponse(
        content="mocked",
        model="doubao-seed-2.0-pro",
        prompt_tokens=10,
        completion_tokens=20,
        cost_usd=Decimal("0.0005"),
        latency_ms=12,
        trace_id=VALID_TRACE_ID,
    )


def test_with_fixture_response_returns_response():
    resp = _fixture_response()
    client = MockLLMClient().with_fixture_response(resp)

    actual = client.complete(**_complete_kwargs())

    assert actual == resp


def test_with_error_raises_on_call():
    sentinel = RuntimeError("boom")
    client = MockLLMClient().with_error(sentinel)

    with pytest.raises(RuntimeError) as exc_info:
        client.complete(**_complete_kwargs())

    assert exc_info.value is sentinel


def test_call_count_and_last_request_tracking():
    client = MockLLMClient().with_fixture_response(_fixture_response())

    assert client.call_count == 0
    assert client.last_request is None

    kwargs = _complete_kwargs(agent_name="supervisor")
    client.complete(**kwargs)

    assert client.call_count == 1
    assert client.last_request is not None
    assert client.last_request.agent_name == "supervisor"
    assert client.last_request.trace_id == VALID_TRACE_ID
    assert client.last_request.model == kwargs["model"]
    assert client.last_request.messages[0].content == "hi"

    # Second call still returns the (last-set) fixture, increments count:
    client.complete(**_complete_kwargs(agent_name="code_fixer"))
    assert client.call_count == 2
    assert client.last_request is not None
    assert client.last_request.agent_name == "code_fixer"
