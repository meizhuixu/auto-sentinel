"""Concrete LLMClient pointed at Zhipu BigModel (glm-4.7).

Constitution VII.1: this is one of TWO files allowed to `import openai`
(the other is ark_client.py). The allowlist is hard-coded in
tests/unit/test_llm_provider_isolation.py.

Same shape as ArkLLMClient — only the base_url, model price table, and
the module-level patch target for LLMTracer differ. SecurityReviewer
(GLM-4.7) is the primary caller in PR-2.
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

try:
    from llmops_dashboard.instrumentation.tracer import LLMTracer
except ImportError:
    LLMTracer = None  # type: ignore[assignment,misc]


# GLM per-model pricing (USD per 1M tokens). Placeholder figures; exact
# values not test-critical.
_GLM_PRICING_USD_PER_M: dict[str, dict[str, float]] = {
    "glm-4.7": {"input": 5.00, "output": 15.00},
}


class GlmLLMClient:
    """OpenAI-SDK-backed client for the Zhipu BigModel endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://open.bigmodel.cn/api/paas/v4",
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._sdk = openai.OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            timeout=httpx.Timeout(30.0),
            max_retries=0,
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
                "Tests must patch autosentinel.llm.glm_client.LLMTracer."
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
                    f"GLM request timed out after 3 attempts: {e}"
                ) from e
            except openai.APIStatusError as e:
                raise LLMProviderError(
                    f"GLM provider returned error status: {e}"
                ) from e
            except openai.APIError as e:
                raise LLMProviderError(f"GLM API error: {e}") from e
            latency_ms = int((time.monotonic() - start) * 1000)

            content = sdk_response.choices[0].message.content or ""
            prompt_tokens = sdk_response.usage.prompt_tokens
            completion_tokens = sdk_response.usage.completion_tokens

            input_usd, output_usd = self._compute_cost(
                model, prompt_tokens, completion_tokens
            )

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
        prices = _GLM_PRICING_USD_PER_M.get(model, {"input": 0.0, "output": 0.0})
        input_usd = (prompt_tokens / 1_000_000) * prices["input"]
        output_usd = (completion_tokens / 1_000_000) * prices["output"]
        return input_usd, output_usd
