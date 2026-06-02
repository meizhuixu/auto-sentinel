"""Single source of truth for the CNY→USD conversion used in LLM cost accounting.

Volcano Ark bills every access point (Doubao + GLM-4.7) in **CNY**, but
LLMResponse.cost_usd and LLMTracer.set_cost_breakdown both store **USD**. The
conversion therefore happens in exactly one place — the CNY_PER_USD constant
below. Per-model rates live in each client's price table in CNY per 1M tokens
(ark_client.py / glm_client.py) and are divided by CNY_PER_USD at cost-compute
time. Do NOT convert anywhere else; import this constant instead.

Exchange rate: 1 USD = CNY_PER_USD. Mid-market USD/CNY looked up 2026-06-01
(≈ 6.767). This is a hard-coded snapshot, not a live feed — refresh it here (and
only here) if a materially different rate matters for budget accuracy. The
project budget cap (CostGuard, ¥150 ≈ $20.6) was sized at an older ~7.3 rate;
that ceiling is intentionally conservative and unaffected by this finer figure.
"""

from __future__ import annotations

# 1 USD = CNY_PER_USD. Snapshot taken 2026-06-01 (USD/CNY ≈ 6.767).
CNY_PER_USD: float = 6.77
