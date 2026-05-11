"""CostGuard singleton + accumulator (contracts/cost-guard.md).

Sync stack — threading.Lock, not asyncio.Lock. State is in-process only
(documented trade-off in research.md Decision 6: Sprint 5 is single-process,
restart clears the counter).

Threshold semantics (cost-guard.md §40-66, exact wording):

    Step 1 (accumulate):  total += delta; call_count += 1; last_updated = now
    Step 2 (check):       if total > limit: raise CostGuardError(...)

Strict `>`, no buffer. The state IS updated before the raise — meaning the
caller has already received the LLMResponse for this call; the next outbound
call is what fails fast.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from threading import Lock
from typing import Optional

from pydantic import BaseModel, Field

from autosentinel.llm.errors import CostGuardError


class CostGuardState(BaseModel):
    """Snapshot schema (data-model.md §7). Returned via CostGuard.state under lock."""

    total_spent_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    budget_limit_usd: Decimal = Field(ge=Decimal("0"))
    call_count: int = Field(default=0, ge=0)
    last_updated: Optional[datetime] = None


class CostGuard:
    def __init__(self, budget_limit_usd: Decimal) -> None:
        self._lock = Lock()
        self._state = CostGuardState(budget_limit_usd=budget_limit_usd)

    @property
    def state(self) -> CostGuardState:
        """Snapshot under lock — callers never see a torn read."""
        with self._lock:
            return self._state.model_copy()

    def accumulate(self, cost_usd: Decimal) -> None:
        """Step 1 then Step 2 per contract. Raises CostGuardError if the
        post-accumulate total exceeds budget. State is updated BEFORE the
        raise (the caller has already received the response for this call)."""
        with self._lock:
            new_total = self._state.total_spent_usd + cost_usd
            self._state = self._state.model_copy(
                update={
                    "total_spent_usd": new_total,
                    "call_count": self._state.call_count + 1,
                    "last_updated": datetime.now(timezone.utc),
                }
            )
            if new_total > self._state.budget_limit_usd:
                raise CostGuardError(
                    current_spent_usd=new_total,
                    attempted_amount_usd=cost_usd,
                    budget_limit_usd=self._state.budget_limit_usd,
                )

    def reset_for_test(self) -> None:
        """PYTEST_CURRENT_TEST gate — refuses outside a pytest run."""
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            raise RuntimeError(
                "reset_for_test() may only be called from a pytest run. "
                "PYTEST_CURRENT_TEST env var was not set."
            )
        with self._lock:
            self._state = self._state.model_copy(
                update={
                    "total_spent_usd": Decimal("0"),
                    "call_count": 0,
                    "last_updated": None,
                }
            )


_singleton: Optional[CostGuard] = None
_singleton_lock = Lock()


def get_cost_guard() -> CostGuard:
    """Lazy module-level singleton. Budget read from env var
    AUTOSENTINEL_BUDGET_LIMIT_USD (default '20.6')."""
    global _singleton
    if _singleton is None:
        with _singleton_lock:
            if _singleton is None:
                budget = Decimal(
                    os.environ.get("AUTOSENTINEL_BUDGET_LIMIT_USD", "20.6")
                )
                _singleton = CostGuard(budget_limit_usd=budget)
    return _singleton
