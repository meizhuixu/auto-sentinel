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
  3. Call SDK inside the tracer span with tenacity retry (2 attempts).
  4. set_tokens / set_cost_breakdown on the tracer.
  5. Build LLMResponse with Decimal cost.
  6. POST-response: cost_guard.accumulate(cost) — may raise CostGuardError.
"""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Optional, cast

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


# Ark per-model pricing in **CNY per 1M tokens** — the native billing currency.
# No exchange-rate conversion happens anywhere: cost is recorded in CNY and the
# CostGuard runs a CNY budget. The factory passes the Ark endpoint id as
# `model`, so the table is keyed by endpoint id; friendly names are retained as
# aliases for unit tests and readability.
#
# Doubao-1.5-lite-32k (Supervisor/Verifier): ¥0.3 in / ¥0.6 out — flat tier.
# Doubao-Seed-2.0-pro (Diagnosis/CodeFixer/InfraSRE): ¥3.2 in / ¥16 out — the
#   list price of the regular inference tier (NOT the low-latency "Fast" tier
#   at ¥9.6/¥48). Using list price avoids depending on a possibly-limited-time
#   discount.
_ARK_PRICING_CNY_PER_M: dict[str, dict[str, float]] = {
    "ep-20260508052205-6x8hm": {"input": 0.30, "output": 0.60},  # doubao-1.5-lite-32k
    "doubao-1.5-lite-32k": {"input": 0.30, "output": 0.60},
    "ep-20260508052420-fwq5q": {"input": 3.20, "output": 16.00},  # doubao-seed-2.0-pro
    "doubao-seed-2.0-pro": {"input": 3.20, "output": 16.00},
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
            timeout=httpx.Timeout(45.0),  # reasoning models run >30s; give one attempt room
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

        # LLMTracer optional: when llmops_dashboard isn't installed (e.g. T040
        # script-side runs against the real endpoint without the dashboard
        # service), skip the tracer span and run the bare SDK call. Unit tests
        # patch this module's LLMTracer symbol to a MagicMock, so the patched
        # path stays exercised.
        from contextlib import nullcontext

        tracer_cm = (
            LLMTracer(
                trace_id=trace_id,
                project="auto-sentinel",
                component=agent_name,
                model=model,
            )
            if LLMTracer is not None
            else nullcontext()
        )

        with tracer_cm as tracer:
            start = time.monotonic()
            try:
                sdk_response = self._invoke_with_retry(req)
            except (httpx.TimeoutException, openai.APITimeoutError) as e:
                raise LLMTimeoutError(
                    f"Ark request timed out after 2 attempts: {e}"
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

            input_cost, output_cost = self._compute_cost(
                model, prompt_tokens, completion_tokens
            )

            # Tracer enrichment — absorbed by MagicMock in tests; no-op when
            # the dashboard isn't installed (tracer is None). Costs are CNY
            # (Ark's billing currency); the tracer call is currency-neutral.
            if tracer is not None and hasattr(tracer, "set_tokens"):
                tracer.set_tokens(prompt=prompt_tokens, completion=completion_tokens)
            if tracer is not None and hasattr(tracer, "set_cost_breakdown"):
                tracer.set_cost_breakdown(
                    input_cost=input_cost, output_cost=output_cost, currency="CNY"
                )

        cost = Decimal(str(input_cost + output_cost))
        response = LLMResponse(
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            currency="CNY",
            latency_ms=latency_ms,
            trace_id=trace_id,
        )

        # Post-response accumulation. CostGuardError may be raised here;
        # the caller has the LLMResponse in hand by design (contract Step 6).
        get_cost_guard().accumulate(cost, "CNY")

        return response

    @tenacity.retry(
        stop=tenacity.stop_after_attempt(2),
        wait=tenacity.wait_exponential(multiplier=1, max=8),
        retry=tenacity.retry_if_exception_type(
            (httpx.TimeoutException, openai.APITimeoutError)
        ),
        reraise=True,
    )
    def _invoke_with_retry(self, req: LLMRequest):
        return self._sdk.chat.completions.create(
            model=req.model,
            messages=cast(Any, [m.model_dump() for m in req.messages]),
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

    @staticmethod
    def _compute_cost(
        model: str, prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float]:
        prices = _ARK_PRICING_CNY_PER_M.get(model, {"input": 0.0, "output": 0.0})
        input_cost = (prompt_tokens / 1_000_000) * prices["input"]
        output_cost = (completion_tokens / 1_000_000) * prices["output"]
        return input_cost, output_cost
