"""AutoSentinel — Core Diagnostic AI Engine."""

import uuid
from pathlib import Path

from autosentinel.models import AgentState


class DiagnosticError(Exception):
    """Raised when the pipeline exits via an error state."""


def run_pipeline(log_path: str | Path, *, trace_id: str | None = None) -> Path:
    """Run the multi-agent diagnostic pipeline on a JSON error log.

    Sprint 6 (006-fix-verification-integrity US4): the v1 single-agent
    pipeline and its AUTOSENTINEL_MULTI_AGENT opt-in flag are retired — the
    multi-agent graph is the only path.

    trace_id (T046, boundary 3): the ingest-stamped 32-char hex id, threaded
    into AgentState["trace_id"] unregenerated. When None (e.g. CLI runs), the
    multi-agent graph's `dispatch` node defensively seeds one.
    """
    path = Path(log_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    from autosentinel.multi_agent_graph import build_multi_agent_graph

    initial_state = AgentState(
        log_path=str(path),
        error_log=None,
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
        fix_script=None,
        execution_result=None,
        execution_error=None,
        report_text=None,
        report_path=None,
        error_category=None,
        fix_artifact=None,
        security_verdict=None,
        routing_decision=None,
        specialist=None,
        agent_trace=[],
        approval_required=False,
    )
    if trace_id:
        initial_state["trace_id"] = trace_id
        # US4/T068: open the parent Langfuse trace once so the per-agent
        # generation spans (all attached via owns_trace=False) nest under a
        # real trace object tagged project/component. Best-effort no-op when
        # the `tracing` extra is absent or Langfuse is unconfigured.
        from autosentinel.tracing import open_parent_trace
        open_parent_trace(trace_id)
    graph = build_multi_agent_graph()
    # thread_id ties the LangGraph checkpoint to this incident; reuse the
    # trace_id (== incident id) when present so a later /resume can target it.
    cfg = {"configurable": {"thread_id": trace_id or str(uuid.uuid4())}}
    result = graph.invoke(initial_state, cfg)

    if result.get("parse_error"):
        raise DiagnosticError(result["parse_error"])
    if result.get("analysis_error"):
        raise DiagnosticError(result["analysis_error"])

    return Path(result["report_path"])
