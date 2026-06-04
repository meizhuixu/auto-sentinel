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

    Amounts are in the CostGuard's native currency (no conversion). `currency`
    is carried so the cost_exhausted_node report is unambiguous.

    Attributes:
        current_spent: post-accumulate cumulative total at the moment of trip.
        attempted_amount: the cost of THIS call (the delta that pushed us over).
        budget_limit: the configured ceiling.
        currency: the currency all three amounts are denominated in.
    """

    def __init__(
        self,
        *,
        current_spent: Decimal,
        attempted_amount: Decimal,
        budget_limit: Decimal,
        currency: str = "CNY",
    ) -> None:
        self.current_spent = current_spent
        self.attempted_amount = attempted_amount
        self.budget_limit = budget_limit
        self.currency = currency
        super().__init__(
            f"CostGuard tripped: spent={current_spent}{currency} + "
            f"attempted={attempted_amount}{currency} > budget={budget_limit}{currency}"
        )
