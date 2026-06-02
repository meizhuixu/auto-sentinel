"""Contract tests for autosentinel/llm/cost_guard.py — CostGuard singleton.

Sprint 5 refactor: cost is accounted in the model's **native currency** (no
exchange-rate conversion). All three Volcano Ark models bill in CNY, so the
CostGuard runs in CNY with a ¥150 budget. The amount now travels with a
currency tag; accumulation is same-currency only — a mismatched currency is a
hard error (Constitution VII.2: no silent skip / no abort-bypass), never a
cross-currency add.

Cases:
  1. Over-threshold raises CostGuardError with currency-tagged payload
  2. reset_for_test() PYTEST_CURRENT_TEST gate
  3. Threading-lock safety: 100 threads × accumulate(0.001) → exact 0.100
  4. Cross-currency accumulate raises and does NOT pollute the total
  5. get_cost_guard() default is ¥150 CNY
"""

import threading
from decimal import Decimal

import pytest

import autosentinel.llm.cost_guard as cost_guard_mod
from autosentinel.llm.cost_guard import CostGuard, get_cost_guard
from autosentinel.llm.errors import CostGuardError


def test_over_threshold_raises_with_payload():
    guard = CostGuard(budget_limit=Decimal("0.10"), currency="CNY")

    # First call: cumulative 0.06 ≤ 0.10 → ok
    guard.accumulate(Decimal("0.06"), currency="CNY")
    assert guard.state.total_spent == Decimal("0.06")
    assert guard.state.currency == "CNY"
    assert guard.state.call_count == 1

    # Second call: cumulative 0.12 > 0.10 → raises
    with pytest.raises(CostGuardError) as exc_info:
        guard.accumulate(Decimal("0.06"), currency="CNY")

    err = exc_info.value
    assert err.current_spent == Decimal("0.12")
    assert err.attempted_amount == Decimal("0.06")
    assert err.budget_limit == Decimal("0.10")
    assert err.currency == "CNY"
    # Cost was added to state BEFORE the raise (Step 1 then Step 2):
    assert guard.state.total_spent == Decimal("0.12")
    assert guard.state.call_count == 2


def test_reset_for_test_pytest_gate(monkeypatch):
    guard = CostGuard(budget_limit=Decimal("1.00"), currency="CNY")
    guard.accumulate(Decimal("0.50"), currency="CNY")
    assert guard.state.total_spent == Decimal("0.50")

    # PYTEST_CURRENT_TEST is set automatically by pytest — reset works:
    guard.reset_for_test()
    assert guard.state.total_spent == Decimal("0")
    assert guard.state.call_count == 0

    # Without PYTEST_CURRENT_TEST, reset_for_test() must refuse:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(RuntimeError):
        guard.reset_for_test()


def test_threading_lock_safety_no_race():
    """100 threads each accumulate(0.001) on a generous budget. After join,
    total must be exact Decimal("0.100") — Decimal exact arithmetic + lock."""
    guard = CostGuard(budget_limit=Decimal("100"), currency="CNY")

    def worker():
        guard.accumulate(Decimal("0.001"), currency="CNY")

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert guard.state.total_spent == Decimal("0.100")
    assert guard.state.call_count == 100


def test_cross_currency_accumulate_is_hard_error_not_bypass():
    """A CNY guard must reject a USD amount with a raise (VII.2: no silent
    skip, no abort-bypass). The mismatched amount must NOT be added to the
    CNY total, and it must NOT be a CostGuardError (that means 'over budget')."""
    guard = CostGuard(budget_limit=Decimal("150"), currency="CNY")
    guard.accumulate(Decimal("10"), currency="CNY")

    with pytest.raises(ValueError):
        guard.accumulate(Decimal("5"), currency="USD")

    # No cross-currency pollution of the CNY total, and the call_count for the
    # rejected call is not committed.
    assert guard.state.total_spent == Decimal("10")
    assert guard.state.call_count == 1


def test_get_cost_guard_default_budget_is_150_cny(monkeypatch):
    monkeypatch.delenv("AUTOSENTINEL_BUDGET_LIMIT_CNY", raising=False)
    cost_guard_mod._singleton = None
    try:
        guard = get_cost_guard()
        assert guard.state.budget_limit == Decimal("150")
        assert guard.state.currency == "CNY"
    finally:
        cost_guard_mod._singleton = None
