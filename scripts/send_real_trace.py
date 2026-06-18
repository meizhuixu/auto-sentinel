"""T068 — end-to-end real trace propagation into Langfuse (project-4 LLMOps Dashboard).

Unlike scripts/check_endpoints.py (which stubs a no-op tracer and ships NO spans),
this script keeps the REAL `llmops_dashboard` LLMTracer wired into the concrete
client, so a genuine generation span — with token usage and CNY cost breakdown —
is pushed to the local Langfuse backend on the tracer's __exit__.

It makes ONE real Volcano Ark completion against the cheapest endpoint
(supervisor → Doubao-1.5-lite-32k, ¥0.3/¥0.6 per 1M tokens) with a tiny prompt,
so real spend is a fraction of a cent.

Requirements (.env in repo root):
  - ARK_API_KEY            — real Volcano Ark key (the real LLM call)
  - LANGFUSE_HOST          — e.g. http://localhost:3000
  - LANGFUSE_PUBLIC_KEY    — pk-lf-...
  - LANGFUSE_SECRET_KEY    — sk-lf-...
The `tracing` extra must be installed:  uv sync --extra tracing

Usage:
    uv run python scripts/send_real_trace.py
    # then check Langfuse UI → Traces, filter tag project:auto-sentinel

Exit code 0 only if the real call succeeded and the real LLMTracer was active.
Deliberately NOT part of the hermetic pytest suite (real network + real spend).
"""

from __future__ import annotations

import secrets
import sys
from decimal import Decimal

from dotenv import load_dotenv

from autosentinel.llm.factory import build_client_for_agent
from autosentinel.llm.protocol import Message

# Cheapest endpoint, single call.
AGENT = "supervisor"  # → Doubao-1.5-lite-32k
PING_MAX_TOKENS = 16


def main() -> int:
    load_dotenv()

    # Confirm the REAL tracer is wired — this is the whole point of T068.
    import autosentinel.llm.ark_client as ark_mod

    if ark_mod.LLMTracer is None:
        print(
            "FAIL: llmops_dashboard.LLMTracer is not installed in this env "
            "(run: uv sync --extra tracing). No span would be shipped.",
            file=sys.stderr,
        )
        return 1
    print(f"Real LLMTracer active: {ark_mod.LLMTracer}")

    trace_id = secrets.token_hex(16)  # 32-char hex, OTel-compatible
    print(f"trace_id = {trace_id}")

    # Mirror run_pipeline: open the parent trace once so the agent generation
    # nests under a real trace tagged project:auto-sentinel (filterable in UI).
    from autosentinel.tracing import open_parent_trace

    open_parent_trace(trace_id)

    client, cfg = build_client_for_agent(AGENT)
    resp = client.complete(
        messages=[Message(role="user", content="ping")],
        model=cfg.model,
        trace_id=trace_id,
        agent_name=AGENT,
        max_tokens=PING_MAX_TOKENS,
        temperature=cfg.temperature,
    )

    priced = resp.cost > Decimal("0")
    print(
        f"[{AGENT}] endpoint={cfg.model} latency={resp.latency_ms}ms "
        f"tokens={resp.prompt_tokens}+{resp.completion_tokens} "
        f"cost={resp.cost:.6f} {resp.currency}"
        f"{'' if priced else '   WARNING: cost is 0 — price-table miss!'}"
    )
    print(
        "Span shipped to Langfuse on tracer __exit__. "
        f"Filter Traces by tag project:auto-sentinel (trace_id={trace_id})."
    )
    return 0 if priced else 1


if __name__ == "__main__":
    sys.exit(main())
