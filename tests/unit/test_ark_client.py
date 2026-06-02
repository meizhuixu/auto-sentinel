"""Contract tests for autosentinel/llm/ark_client.py — concrete OpenAI-SDK
client pointed at Volcano-Engine Ark base_url
(contracts/llm-client.md §"Behavioural contract" + plan.md Block 1).

Today (T012 commit) tests error on collection because ark_client.py does
not exist yet. T021 implements and turns GREEN.

3 cases against a stubbed httpx.MockTransport (the SDK's underlying
transport is replaced; we never reach the real Ark endpoint):
  1. Happy path → LLMResponse with token counts; LLMTracer opened with
     the trace_id from the request, project='auto-sentinel',
     component=agent_name
  2. httpx.TimeoutException → tenacity retries 3× then raises LLMTimeoutError
  3. HTTP 5xx response → LLMProviderError

Implementation notes the test relies on:
  - ArkLLMClient accepts an injectable `http_client: httpx.Client | None`
    kwarg so the test can pass a MockTransport-backed client. (This is
    the testability seam T021 must provide.)
  - ArkLLMClient imports LLMTracer at module level under the symbol
    `autosentinel.llm.ark_client.LLMTracer` so the patch target works
    regardless of the real source module.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from autosentinel.llm.ark_client import ArkLLMClient
from autosentinel.llm.errors import LLMProviderError, LLMTimeoutError
from autosentinel.llm.pricing import CNY_PER_USD
from autosentinel.llm.protocol import LLMResponse, Message


VALID_TRACE_ID = "0123456789abcdef0123456789abcdef"
ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"

# Real Volcano Ark unit prices (CNY per 1M tokens) — the spec these tests pin.
# Doubao-Seed-2.0-pro: ¥2.88 / ¥14.4 (9折 discounted regular-inference tier).
# Doubao-1.5-lite-32k: ¥0.3 / ¥0.6.
DOUBAO_PRO_CNY = {"input": 2.88, "output": 14.4}
DOUBAO_LITE_CNY = {"input": 0.30, "output": 0.60}


def _expected_usd(prompt_tokens: int, completion_tokens: int, cny: dict) -> float:
    cny_total = (
        prompt_tokens / 1_000_000 * cny["input"]
        + completion_tokens / 1_000_000 * cny["output"]
    )
    return cny_total / CNY_PER_USD


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


def _make_client(transport: httpx.MockTransport) -> ArkLLMClient:
    return ArkLLMClient(
        api_key="dummy-key",
        base_url=ARK_BASE_URL,
        http_client=httpx.Client(transport=transport),
    )


@patch("autosentinel.llm.ark_client.LLMTracer")
def test_happy_path_returns_llm_response_and_opens_tracer(mock_tracer_cls):
    """SDK returns OK; client builds LLMResponse with provider-reported
    token counts and opens LLMTracer with trace_id."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "created": 1_700_000_000,
                "model": "doubao-seed-2.0-pro",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 22,
                    "total_tokens": 33,
                },
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    resp = client.complete(**_complete_kwargs())

    assert isinstance(resp, LLMResponse)
    assert resp.content == "ok"
    assert resp.prompt_tokens == 11
    assert resp.completion_tokens == 22
    assert resp.trace_id == VALID_TRACE_ID
    # Cost is the CNY rate (¥2.88/¥14.4) converted to USD via the single
    # CNY_PER_USD source — not a placeholder USD figure.
    assert float(resp.cost_usd) == pytest.approx(
        _expected_usd(11, 22, DOUBAO_PRO_CNY)
    )
    assert resp.cost_usd > Decimal("0")
    assert resp.model == "doubao-seed-2.0-pro"

    # LLMTracer opened with correct kwargs:
    mock_tracer_cls.assert_called_once()
    call_kwargs = mock_tracer_cls.call_args.kwargs
    assert call_kwargs.get("trace_id") == VALID_TRACE_ID
    assert call_kwargs.get("project") == "auto-sentinel"
    assert call_kwargs.get("component") == "diagnosis"
    assert call_kwargs.get("model") == "doubao-seed-2.0-pro"


@patch("autosentinel.llm.ark_client.LLMTracer")
def test_timeout_triggers_three_retries_then_llm_timeout_error(mock_tracer_cls):
    """All three SDK attempts time out → tenacity gives up → LLMTimeoutError."""
    attempt_count = MagicMock(value=0)

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_count.value += 1
        raise httpx.TimeoutException("simulated timeout", request=request)

    client = _make_client(httpx.MockTransport(handler))

    with pytest.raises(LLMTimeoutError):
        client.complete(**_complete_kwargs())

    # tenacity: stop_after_attempt(3) ⇒ exactly 3 attempts before giving up
    assert attempt_count.value == 3


@patch("autosentinel.llm.ark_client.LLMTracer")
def test_http_5xx_raises_llm_provider_error(mock_tracer_cls):
    """Non-timeout SDK error (HTTP 500) → LLMProviderError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": {"message": "internal"}})

    client = _make_client(httpx.MockTransport(handler))

    with pytest.raises(LLMProviderError):
        client.complete(**_complete_kwargs())


@patch("autosentinel.llm.ark_client.LLMTracer")
def test_lite_model_pricing_converts_cny_to_usd(mock_tracer_cls):
    """Doubao-1.5-lite-32k (Supervisor/Verifier) is priced at ¥0.3/¥0.6 and
    converted to USD via the single CNY_PER_USD source."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-lite-1",
                "object": "chat.completion",
                "created": 1_700_000_000,
                "model": "doubao-1.5-lite-32k",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "route"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
            },
        )

    client = _make_client(httpx.MockTransport(handler))
    resp = client.complete(**_complete_kwargs(model="doubao-1.5-lite-32k"))

    assert float(resp.cost_usd) == pytest.approx(
        _expected_usd(100, 50, DOUBAO_LITE_CNY)
    )
    assert resp.cost_usd > Decimal("0")
