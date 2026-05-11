"""Concrete LLMClient pointed at Volcano-Engine Ark (doubao series).

Constitution VII.1: this is one of TWO files allowed to `import openai`
(the other is glm_client.py). The allowlist is hard-coded in
tests/unit/test_llm_provider_isolation.py — expanding it requires a
constitution amendment.

LLMTracer is imported at module level under the symbol
`autosentinel.llm.ark_client.LLMTracer`. Unit tests patch THAT symbol
(not the upstream source) so concrete-client tests run without an actual
Langfuse backend.

Behavioural contract (contracts/llm-client.md §"Side-effects"):
  1. Validate trace_id via LLMRequest (frozen) — ValueError surfaces unwrapped.
  2. Open LLMTracer(trace_id, project='auto-sentinel', component=agent_name, model).
  3. Call SDK inside the tracer span with tenacity retry (3 attempts).
  4. set_tokens / set_cost_breakdown on the tracer.
  5. Build LLMResponse with Decimal cost_usd.
  6. POST-response: cost_guard.accumulate(cost_usd) — may raise CostGuardError.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional

import httpx
import openai
import tenacity

from autosentinel.llm.cost_guard import get_cost_guard
from autosentinel.llm.errors import LLMProviderError, LLMTimeoutError
from autosentinel.llm.protocol import LLMRequest, LLMResponse, Message

# Module-level patch target for unit tests. Wrapping in try/except lets the
# module load on dev machines where llmops_dashboard isn't installed; tests
# patch LLMTracer regardless, and complete() refuses to run if it's None
# (production guard).
try:
    from llmops_dashboard.instrumentation.tracer import LLMTracer
except ImportError:
    LLMTracer = None  # type: ignore[assignment,misc]


# Ark per-model pricing (USD per 1M tokens). Placeholder figures pending the
# real vendor pricing page; CostGuard sees the Decimal sum computed from
# these. Exact values not test-critical (tests assert cost_usd ≥ 0 only).
_ARK_PRICING_USD_PER_M: dict[str, dict[str, float]] = {
    "doubao-1.5-lite-32k": {"input": 0.30, "output": 0.60},
    "doubao-seed-2.0-pro": {"input": 2.00, "output": 8.00},
}


class ArkLLMClient:
    """OpenAI-SDK-backed client for the Volcano-Engine Ark endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://ark.cn-beijing.volces.com/api/v3",
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._sdk = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            timeout=httpx.Timeout(30.0),
            max_retries=0,  # tenacity owns the retry policy
        )

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
        # LLMRequest validation: trace_id regex + non-empty fields. Bad
        # trace_id surfaces as ValueError unwrapped (Constitution VII.3).
        req = LLMRequest(
            messages=messages,
            model=model,
            trace_id=trace_id,
            agent_name=agent_name,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        if LLMTracer is None:
            raise RuntimeError(
                "LLMTracer is not available (llmops_dashboard not installed). "
                "Tests must patch autosentinel.llm.ark_client.LLMTracer."
            )

        with LLMTracer(
            trace_id=trace_id,
            project="auto-sentinel",
            component=agent_name,
            model=model,
        ) as tracer:
            start = time.monotonic()
            try:
                sdk_response = self._invoke_with_retry(req)
            except (httpx.TimeoutException, openai.APITimeoutError) as e:
                raise LLMTimeoutError(
                    f"Ark request timed out after 3 attempts: {e}"
                ) from e
            except openai.APIStatusError as e:
                raise LLMProviderError(
                    f"Ark provider returned error status: {e}"
                ) from e
            except openai.APIError as e:
                raise LLMProviderError(f"Ark API error: {e}") from e
            latency_ms = int((time.monotonic() - start) * 1000)

            content = sdk_response.choices[0].message.content or ""
            prompt_tokens = sdk_response.usage.prompt_tokens
            completion_tokens = sdk_response.usage.completion_tokens

            input_usd, output_usd = self._compute_cost(
                model, prompt_tokens, completion_tokens
            )

            # Tracer enrichment — absorbed by MagicMock in tests.
            if hasattr(tracer, "set_tokens"):
                tracer.set_tokens(prompt=prompt_tokens, completion=completion_tokens)
            if hasattr(tracer, "set_cost_breakdown"):
                tracer.set_cost_breakdown(input_usd=input_usd, output_usd=output_usd)

        cost_usd = Decimal(str(input_usd + output_usd))
        response = LLMResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            trace_id=trace_id,
        )

        # Post-response accumulation. CostGuardError may be raised here;
        # the caller has the LLMResponse in hand by design (contract Step 6).
        get_cost_guard().accumulate(cost_usd)

        return response

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(multiplier=1, max=8),
        retry=tenacity.retry_if_exception_type(
            (httpx.TimeoutException, openai.APITimeoutError)
        ),
        reraise=True,
    )
    def _invoke_with_retry(self, req: LLMRequest):
        return self._sdk.chat.completions.create(
            model=req.model,
            messages=[m.model_dump() for m in req.messages],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

    @staticmethod
    def _compute_cost(
        model: str, prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float]:
        prices = _ARK_PRICING_USD_PER_M.get(model, {"input": 0.0, "output": 0.0})
        input_usd = (prompt_tokens / 1_000_000) * prices["input"]
        output_usd = (completion_tokens / 1_000_000) * prices["output"]
        return input_usd, output_usd
