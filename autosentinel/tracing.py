"""Parent Langfuse trace creation for the multi-agent pipeline (US4 / T068).

Each agent's LLMTracer attaches its generation span to an existing trace via
`trace_id` (owns_trace=False), so no agent ever creates the parent trace
object. This module opens that parent trace once per incident at the pipeline
entry point: a real Langfuse trace whose id == the incident trace_id, tagged
project/component, under which the per-agent generations nest.

Best-effort and fully optional: a no-op when the `tracing` extra
(llmops-dashboard) is not installed, when Langfuse is unconfigured, or on any
client error — tracing must never break the pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _langfuse_client() -> Optional[Any]:
    """Return a configured Langfuse client, or None when tracing is unavailable.

    None when: the optional `tracing` extra (llmops-dashboard / langfuse) is not
    installed, or the Langfuse public/secret keys are not configured.
    """
    try:
        from langfuse import Langfuse
        from llmops_dashboard.config import settings
    except ImportError:
        return None
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    return Langfuse(
        host=settings.langfuse_host,
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
    )


def open_parent_trace(
    trace_id: str, *, project: str = "auto-sentinel", component: str = "pipeline"
) -> None:
    """Create the parent Langfuse trace for an incident (best-effort, never raises).

    The agent generation spans (emitted by each LLMTracer with the same
    trace_id) nest under this trace, so the Langfuse UI shows one parent trace
    tagged project/component with a child span per LLM-call agent.
    """
    if not trace_id:
        return
    try:
        client = _langfuse_client()
        if client is None:
            return
        client.trace(
            id=trace_id,
            name=f"{project}/{component}",
            tags=[f"project:{project}", f"component:{component}"],
        )
        client.flush()
    except Exception:  # noqa: BLE001 - tracing must never break the pipeline
        logger.exception("failed to open parent Langfuse trace for %s", trace_id)
