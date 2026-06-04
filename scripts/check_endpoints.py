"""Live connectivity + pricing smoke test for the three Volcano Ark access points.

After repointing GLM-4.7 from the Zhipu gateway to the Volcano Ark proxy
(config/model_routing.yaml), all three endpoints — Doubao-Seed-2.0-pro,
Doubao-1.5-lite-32k, and GLM-4.7 — authenticate with the SAME ARK_API_KEY.
This script sends one trivial "ping" completion to each, going through the
declarative factory (build_client_for_agent), and prints HTTP status, latency,
token usage, and computed cost. It is the necessary pre-flight before any real
benchmark run: it confirms the key swap works on all three paths and that
pricing resolves (cost > 0) for each model.

This costs a few cents of real spend and requires network access + a real
ARK_API_KEY. It is deliberately NOT part of the hermetic pytest suite.

**Tracer-independent**: this is a *pure connectivity + pricing probe*, not a
trace test. It installs a local no-op LLMTracer stub into the client modules,
so it runs WITHOUT the project-4 `llmops_dashboard` installed and is immune to
the `set_cost_breakdown` signature. No spans are shipped to Langfuse here —
real trace propagation is verified separately (T068, after the project-4
LLMTracer signature is synced). We still exercise the real `complete()` path:
real Volcano Ark SDK call + real token usage + real CNY price-table cost.

Usage:
    uv run python scripts/check_endpoints.py

Requires .env with ARK_API_KEY set (copy from .env.example).
Exit code 0 only if all three endpoints return 200 with priced cost > 0.
"""

from __future__ import annotations

import secrets
import sys
from decimal import Decimal

from dotenv import load_dotenv

from autosentinel.llm.factory import build_client_for_agent
from autosentinel.llm.protocol import Message


class _NoOpTracer:
    """Local stand-in for the project-4 LLMTracer so this probe runs without
    the dashboard and without coupling to its method signatures. It does NOT
    ship spans — this script is a connectivity/pricing probe, not a trace test.
    Accepts arbitrary kwargs on every method so a future signature change can't
    break the probe."""

    def __init__(self, **kwargs) -> None: ...
    def __enter__(self) -> "_NoOpTracer": return self
    def __exit__(self, *exc) -> bool: return False
    def set_tokens(self, **kwargs) -> None: ...
    def set_cost_breakdown(self, **kwargs) -> None: ...


def _install_noop_tracer() -> None:
    """Replace the LLMTracer symbol in both concrete client modules. ark_client
    falls back to nullcontext when its symbol is None, but glm_client hard-raises
    without a tracer — stubbing both makes all three endpoints probeable here."""
    import autosentinel.llm.ark_client as ark_mod
    import autosentinel.llm.glm_client as glm_mod

    ark_mod.LLMTracer = _NoOpTracer
    glm_mod.LLMTracer = _NoOpTracer

# One agent per distinct Ark endpoint id — together they cover all three
# access points exactly once. Supervisor → Doubao-1.5-lite-32k,
# diagnosis → Doubao-Seed-2.0-pro, security_reviewer → GLM-4.7 (Ark proxy).
AGENTS = ("supervisor", "diagnosis", "security_reviewer")

# Keep each call tiny to minimise spend; the configured max_tokens (up to 4096)
# is irrelevant for a connectivity probe.
PING_MAX_TOKENS = 16


def _probe(agent_name: str, trace_id: str) -> tuple[bool, str]:
    client, cfg = build_client_for_agent(agent_name)
    resp = client.complete(
        messages=[Message(role="user", content="ping")],
        model=cfg.model,
        trace_id=trace_id,
        agent_name=agent_name,
        max_tokens=PING_MAX_TOKENS,
        temperature=cfg.temperature,
    )
    priced = resp.cost > Decimal("0")
    line = (
        f"  endpoint={cfg.model}  latency={resp.latency_ms}ms  "
        f"tokens={resp.prompt_tokens}+{resp.completion_tokens}  "
        f"cost={resp.cost:.6f} {resp.currency}"
        f"{'' if priced else '   ⚠️  cost is 0 — price table miss!'}"
    )
    return priced, line


def main() -> int:
    load_dotenv()
    _install_noop_tracer()
    trace_id = secrets.token_hex(16)
    print(f"Connectivity smoke test (tracer stubbed) — trace_id={trace_id}\n")

    all_ok = True
    for agent in AGENTS:
        print(f"[{agent}]")
        try:
            priced, line = _probe(agent, trace_id)
            print(f"  status=OK 200")
            print(line)
            all_ok = all_ok and priced
        except Exception as e:  # noqa: BLE001 — surface any failure per-endpoint
            all_ok = False
            print(f"  status=FAIL — {type(e).__name__}: {e}")
        print()

    print("All three Ark access points reachable + priced." if all_ok
          else "One or more endpoints FAILED — see above.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
