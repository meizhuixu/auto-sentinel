"""Concrete LLMClient for GLM-4.7, served through the Volcano Ark proxy.

Constitution VII.1: this is one of TWO files allowed to `import openai`
(the other is ark_client.py). The allowlist is hard-coded in
tests/unit/test_llm_provider_isolation.py.

GLM-4.7 no longer routes through the first-party Zhipu gateway
(open.bigmodel.cn). All three access points are provisioned under Volcano
Ark, so this client points at the Ark gateway and authenticates with the
same ARK_API_KEY as the Doubao endpoints. The base_url and api_key are still
injected by factory.build_client_for_agent() from config/model_routing.yaml
(Constitution VII.4) — this class hard-codes neither.

Same shape as ArkLLMClient — only the model price table and the module-level
patch target for LLMTracer differ. The `glm` endpoint alias is kept distinct
from `ark` purely so the factory routes GLM-4.7 here (for its own pricing),
not because the physical gateway differs. SecurityReviewer (GLM-4.7) is the
primary caller.
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


# GLM-4.7 pricing in **CNY per 1M tokens** — the native billing currency.
# No exchange-rate conversion: cost is recorded in CNY. The factory passes the
# Ark endpoint id as `model`, so the table is keyed by the endpoint id; the
# friendly "glm-4.7" alias is retained for unit tests.
#
# Volcano Ark GLM-4.7 has three segments:
#   input ≤ 32k, output ≤ 200   → ¥2 / ¥8
#   input ≤ 32k, output > 200    → ¥3 / ¥14   ← WE USE THIS (main tier)
#   32k < input ≤ 200K           → ¥4 / ¥16
# We fix the main tier (¥3/¥14): the real scenario is a <32k log input plus a
# security-analysis output that always exceeds 200 tokens — the smoke test
# (scripts/check_endpoints.py) empirically confirmed the SecurityReviewer emits
# >200 output tokens, so the ¥2/¥8 (output≤200) tier never genuinely applies.
# Runtime segmentation is NOT implemented — the rate is fixed at the main tier.
# The rare >32k-input case is slightly under-priced (¥3 vs ¥4 input), negligible
# at the ¥150 budget scale.
_GLM_PRICING_CNY_PER_M: dict[str, dict[str, float]] = {
    "ep-20260508052924-6zchc": {"input": 3.00, "output": 14.00},  # GLM-4.7 (Ark)
    "glm-4.7": {"input": 3.00, "output": 14.00},
}


class GlmLLMClient:
    """OpenAI-SDK-backed client for GLM-4.7 on the Volcano Ark gateway."""

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

        # LLMTracer optional: when llmops_dashboard isn't installed (e.g. T066
        # benchmark / script-side runs against the real endpoint without the
        # dashboard service), skip the tracer span and run the bare SDK call.
        # Unit tests patch this module's LLMTracer symbol to a MagicMock, so the
        # patched path stays exercised. Mirrors ArkLLMClient exactly.
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
                    f"GLM request timed out after 2 attempts: {e}"
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
            messages=[m.model_dump() for m in req.messages],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
        )

    @staticmethod
    def _compute_cost(
        model: str, prompt_tokens: int, completion_tokens: int
    ) -> tuple[float, float]:
        prices = _GLM_PRICING_CNY_PER_M.get(model, {"input": 0.0, "output": 0.0})
        input_cost = (prompt_tokens / 1_000_000) * prices["input"]
        output_cost = (completion_tokens / 1_000_000) * prices["output"]
        return input_cost, output_cost
