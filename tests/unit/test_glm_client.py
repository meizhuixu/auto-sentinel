"""Contract tests for autosentinel/llm/glm_client.py — concrete OpenAI-SDK
client pointed at Zhipu BigModel base_url
(contracts/llm-client.md §"Behavioural contract" + plan.md Block 1).

Same shape as test_ark_client.py but the base_url is Zhipu's and the
model is glm-4.7 (used by the SecurityReviewer).

Today (T013 commit) tests error on collection because glm_client.py does
not exist yet. T022 implements and turns GREEN.

3 cases against httpx.MockTransport:
  1. Happy path → LLMResponse + LLMTracer opened with trace_id
  2. httpx.TimeoutException → 3 retries → LLMTimeoutError
  3. HTTP 5xx → LLMProviderError
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from autosentinel.llm.errors import LLMProviderError, LLMTimeoutError
from autosentinel.llm.glm_client import GlmLLMClient
from autosentinel.llm.protocol import LLMResponse, Message


VALID_TRACE_ID = "fedcba9876543210fedcba9876543210"
GLM_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def _complete_kwargs(**overrides) -> dict:
    base = {
        "messages": [Message(role="user", content="review this fix")],
        "model": "glm-4.7",
        "trace_id": VALID_TRACE_ID,
        "agent_name": "security_reviewer",
        "max_tokens": 2048,
        "temperature": 0.0,
    }
    base.update(overrides)
    return base


def _make_client(transport: httpx.MockTransport) -> GlmLLMClient:
    return GlmLLMClient(
        api_key="dummy-key",
        base_url=GLM_BASE_URL,
        http_client=httpx.Client(transport=transport),
    )


@patch("autosentinel.llm.glm_client.LLMTracer")
def test_happy_path_returns_llm_response_and_opens_tracer(mock_tracer_cls):
    def handler(request: httpx.Request) -> httpx.Response:
        # The OpenAI SDK targets Zhipu's /chat/completions endpoint; the
        # request URL must contain the Zhipu host so the test also pins
        # the base_url wiring.
        assert request.url.host == "open.bigmodel.cn", (
            f"GlmLLMClient sent request to wrong host: {request.url}"
        )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-glm-1",
                "object": "chat.completion",
                "created": 1_700_000_000,
                "model": "glm-4.7",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "SAFE"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 5,
                    "total_tokens": 55,
                },
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    resp = client.complete(**_complete_kwargs())

    assert isinstance(resp, LLMResponse)
    assert resp.content == "SAFE"
    assert resp.prompt_tokens == 50
    assert resp.completion_tokens == 5
    assert resp.trace_id == VALID_TRACE_ID
    assert resp.cost_usd >= Decimal("0")
    assert resp.model == "glm-4.7"

    mock_tracer_cls.assert_called_once()
    call_kwargs = mock_tracer_cls.call_args.kwargs
    assert call_kwargs.get("trace_id") == VALID_TRACE_ID
    assert call_kwargs.get("project") == "auto-sentinel"
    assert call_kwargs.get("component") == "security_reviewer"
    assert call_kwargs.get("model") == "glm-4.7"


@patch("autosentinel.llm.glm_client.LLMTracer")
def test_timeout_triggers_three_retries_then_llm_timeout_error(mock_tracer_cls):
    attempt_count = MagicMock(value=0)

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_count.value += 1
        raise httpx.TimeoutException("simulated timeout", request=request)

    client = _make_client(httpx.MockTransport(handler))

    with pytest.raises(LLMTimeoutError):
        client.complete(**_complete_kwargs())

    assert attempt_count.value == 3


@patch("autosentinel.llm.glm_client.LLMTracer")
def test_http_5xx_raises_llm_provider_error(mock_tracer_cls):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"message": "service unavailable"}})

    client = _make_client(httpx.MockTransport(handler))

    with pytest.raises(LLMProviderError):
        client.complete(**_complete_kwargs())
