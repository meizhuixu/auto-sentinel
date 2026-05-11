"""Typed exceptions for the LLM client and surrounding infra.

Hierarchy:
- LLMError                  ← base for "LLM call gone wrong"
    - LLMTimeoutError       ← tenacity gave up after 3 attempts of httpx.TimeoutException
    - LLMProviderError      ← non-timeout SDK error (4xx, 5xx, schema mismatch)
- ConfigurationError        ← startup misconfig (missing env var, missing endpoint, etc.)
- CostGuardError            ← raised by CostGuard.accumulate() with typed payload

CostGuardError carries an attribute payload (per data-model.md §10) so the
graph's cost_exhausted_node can serialise the spend numbers into AgentState
for the user-facing report.
"""

from __future__ import annotations

from decimal import Decimal


class LLMError(Exception):
    """Base for runtime LLM-call failures raised by concrete clients."""


class LLMTimeoutError(LLMError):
    """Wraps tenacity's RetryError after 3 attempts of httpx.TimeoutException."""


class LLMProviderError(LLMError):
    """Non-timeout provider SDK error (4xx, 5xx, malformed response, etc.)."""


class ConfigurationError(Exception):
    """Startup-time misconfiguration: missing env var, missing endpoint, malformed yaml."""


class CostGuardError(Exception):
    """Raised by CostGuard.accumulate() when cumulative spend exceeds budget.

    Attributes:
        current_spent_usd: post-accumulate cumulative total at the moment of trip.
        attempted_amount_usd: the cost of THIS call (the delta that pushed us over).
        budget_limit_usd: the configured ceiling.
    """

    def __init__(
        self,
        *,
        current_spent_usd: Decimal,
        attempted_amount_usd: Decimal,
        budget_limit_usd: Decimal,
    ) -> None:
        self.current_spent_usd = current_spent_usd
        self.attempted_amount_usd = attempted_amount_usd
        self.budget_limit_usd = budget_limit_usd
        super().__init__(
            f"CostGuard tripped: spent={current_spent_usd}USD + "
            f"attempted={attempted_amount_usd}USD > budget={budget_limit_usd}USD"
        )
