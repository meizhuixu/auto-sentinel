"""StateGraph assembly for the diagnostic pipeline."""

from langgraph.graph import END, START, StateGraph

from autosentinel.models import DiagnosticState
from autosentinel.nodes.analyze_error import analyze_error
from autosentinel.nodes.format_report import format_report
from autosentinel.nodes.parse_log import parse_log


def _route_after_parse(state: DiagnosticState) -> str:
    return END if state.get("parse_error") else "analyze_error"


def _route_after_analyze(state: DiagnosticState) -> str:
    return END if state.get("analysis_error") else "format_report"


def build_graph():
    """Assemble and compile the LangGraph StateGraph."""
    builder = StateGraph(DiagnosticState)
    builder.add_node("parse_log", parse_log)
    builder.add_node("analyze_error", analyze_error)
    builder.add_node("format_report", format_report)
    builder.add_edge(START, "parse_log")
    builder.add_conditional_edges("parse_log", _route_after_parse)
    builder.add_conditional_edges("analyze_error", _route_after_analyze)
    builder.add_edge("format_report", END)
    return builder.compile()
