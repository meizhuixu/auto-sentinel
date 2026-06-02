"""Contract tests for autosentinel/llm/glm_client.py — concrete OpenAI-SDK
client for GLM-4.7, now served through the Volcano Ark proxy gateway
(contracts/llm-client.md §"Behavioural contract" + plan.md Block 1).

Same shape as test_ark_client.py. GLM-4.7 no longer routes through the
first-party Zhipu gateway (open.bigmodel.cn); all three access points live
under Volcano Ark, so the base_url is the Ark gateway and the model is the
Ark endpoint id (ep-20260508052924-6zchc) used by the SecurityReviewer.

3 cases against httpx.MockTransport:
  1. Happy path → LLMResponse (with non-zero priced cost) + LLMTracer opened
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


# Real Volcano Ark unit price for GLM-4.7 (CNY per 1M tokens), input≤32k /
# output≤200 tier: ¥2 / ¥8. Cost is recorded natively in CNY — no conversion.
GLM_CNY = {"input": 2.0, "output": 8.0}

VALID_TRACE_ID = "fedcba9876543210fedcba9876543210"
# GLM-4.7 is reached through the Volcano Ark gateway, not the Zhipu gateway.
GLM_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
# Volcano Ark endpoint id for the GLM-4.7 access point.
GLM_ENDPOINT_ID = "ep-20260508052924-6zchc"


def _complete_kwargs(**overrides) -> dict:
    base = {
        "messages": [Message(role="user", content="review this fix")],
        "model": GLM_ENDPOINT_ID,
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
        # The OpenAI SDK targets the Volcano Ark /chat/completions endpoint;
        # the request URL must contain the Ark host so the test also pins
        # the base_url wiring (GLM is no longer on open.bigmodel.cn).
        assert request.url.host == "ark.cn-beijing.volces.com", (
            f"GlmLLMClient sent request to wrong host: {request.url}"
        )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-glm-1",
                "object": "chat.completion",
                "created": 1_700_000_000,
                "model": GLM_ENDPOINT_ID,
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
    # Pricing must resolve for the Ark endpoint id (the price table is keyed
    # by the model string the factory passes — i.e. the endpoint id). Cost is
    # the native CNY amount (¥2/¥8 per 1M tokens) — no exchange conversion.
    expected_cny = (50 / 1_000_000 * GLM_CNY["input"]
                    + 5 / 1_000_000 * GLM_CNY["output"])
    assert float(resp.cost) == pytest.approx(expected_cny)
    assert resp.currency == "CNY"
    assert resp.cost > Decimal("0")
    assert resp.model == GLM_ENDPOINT_ID

    mock_tracer_cls.assert_called_once()
    call_kwargs = mock_tracer_cls.call_args.kwargs
    assert call_kwargs.get("trace_id") == VALID_TRACE_ID
    assert call_kwargs.get("project") == "auto-sentinel"
    assert call_kwargs.get("component") == "security_reviewer"
    assert call_kwargs.get("model") == GLM_ENDPOINT_ID


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
