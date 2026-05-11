"""Contract tests for autosentinel/llm/cost_guard.py — CostGuard singleton.

Today (T009 commit) every test errors on collection because cost_guard.py
and errors.py do not exist yet. T016+T017 implement them and turn GREEN.

3 cases per contracts/cost-guard.md "Test surface":
  1. Over-threshold raises CostGuardError with correct attribute payload
  2. reset_for_test() PYTEST_CURRENT_TEST gate (works in pytest, raises
     RuntimeError when env var is absent)
  3. Threading-lock safety: 100 threads × accumulate(0.001) → exact
     Decimal("0.100") (no race, no torn read)
"""

import threading
from decimal import Decimal

import pytest

from autosentinel.llm.cost_guard import CostGuard
from autosentinel.llm.errors import CostGuardError


def test_over_threshold_raises_with_payload():
    guard = CostGuard(budget_limit_usd=Decimal("0.10"))

    # First call: cumulative 0.06 ≤ 0.10 → ok
    guard.accumulate(Decimal("0.06"))
    assert guard.state.total_spent_usd == Decimal("0.06")
    assert guard.state.call_count == 1

    # Second call: cumulative 0.12 > 0.10 → raises
    with pytest.raises(CostGuardError) as exc_info:
        guard.accumulate(Decimal("0.06"))

    err = exc_info.value
    assert err.current_spent_usd == Decimal("0.12")
    assert err.attempted_amount_usd == Decimal("0.06")
    assert err.budget_limit_usd == Decimal("0.10")
    # Cost was added to state BEFORE the raise (per contract Step 1 then Step 2):
    assert guard.state.total_spent_usd == Decimal("0.12")
    assert guard.state.call_count == 2


def test_reset_for_test_pytest_gate(monkeypatch):
    guard = CostGuard(budget_limit_usd=Decimal("1.00"))
    guard.accumulate(Decimal("0.50"))
    assert guard.state.total_spent_usd == Decimal("0.50")

    # PYTEST_CURRENT_TEST is set automatically by pytest — reset works:
    guard.reset_for_test()
    assert guard.state.total_spent_usd == Decimal("0")
    assert guard.state.call_count == 0

    # Without PYTEST_CURRENT_TEST, reset_for_test() must refuse:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    with pytest.raises(RuntimeError):
        guard.reset_for_test()


def test_threading_lock_safety_no_race():
    """100 threads each accumulate(0.001) on a generous budget. After join,
    total must be exact Decimal("0.100") — Decimal exact arithmetic + lock
    means no rounding error AND no torn write."""
    guard = CostGuard(budget_limit_usd=Decimal("100"))

    def worker():
        guard.accumulate(Decimal("0.001"))

    threads = [threading.Thread(target=worker) for _ in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert guard.state.total_spent_usd == Decimal("0.100")
    assert guard.state.call_count == 100
