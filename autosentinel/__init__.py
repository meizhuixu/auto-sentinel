"""AutoSentinel — Core Diagnostic AI Engine."""

import os
import uuid
from pathlib import Path

from autosentinel.graph import build_graph
from autosentinel.models import AgentState, DiagnosticState


class DiagnosticError(Exception):
    """Raised when the pipeline exits via an error state."""


def run_pipeline(log_path: str | Path) -> Path:
    """Run the full diagnostic pipeline on a JSON error log.

    Set AUTOSENTINEL_MULTI_AGENT=1 to use the v2 multi-agent graph.
    """
    path = Path(log_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    use_multi_agent = os.getenv("AUTOSENTINEL_MULTI_AGENT", "0") == "1"

    if use_multi_agent:
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
            agent_trace=[],
            approval_required=False,
        )
        graph = build_multi_agent_graph()
        cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
        result = graph.invoke(initial_state, cfg)
    else:
        initial_state = DiagnosticState(
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
        )
        graph = build_graph()
        result = graph.invoke(initial_state)

    if result.get("parse_error"):
        raise DiagnosticError(result["parse_error"])
    if result.get("analysis_error"):
        raise DiagnosticError(result["analysis_error"])

    return Path(result["report_path"])
