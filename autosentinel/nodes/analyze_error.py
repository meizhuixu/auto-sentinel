"""analyze_error node — classifies error via Anthropic tool_use."""

from autosentinel.models import DiagnosticState

DIAGNOSE_PROMPT = ""  # placeholder
DIAGNOSE_TOOL: dict = {}  # placeholder


def analyze_error(state: DiagnosticState) -> dict:
    """Call the LLM to classify the error in state['error_log']."""
    raise NotImplementedError
