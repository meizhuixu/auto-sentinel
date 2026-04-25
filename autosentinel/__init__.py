"""AutoSentinel — Core Diagnostic AI Engine."""

from pathlib import Path

from autosentinel.graph import build_graph
from autosentinel.models import DiagnosticState


class DiagnosticError(Exception):
    """Raised when the pipeline exits via an error state."""


def run_pipeline(log_path: str | Path) -> Path:
    """Run the full diagnostic pipeline on a JSON error log."""
    path = Path(log_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {path}")

    initial_state = DiagnosticState(
        log_path=str(path),
        error_log=None,
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
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
