"""analyze_error node — classifies error via Anthropic tool_use."""

import anthropic

from autosentinel.models import AnalysisResult, DiagnosticState

_MODEL = "claude-haiku-4-5-20251001"

DIAGNOSE_PROMPT = (
    "You are a microservice reliability engineer. Analyse the following error log "
    "and use the diagnose_error tool to return a structured diagnosis.\n\n"
    "Service: {service_name}\n"
    "Error type: {error_type}\n"
    "Message: {message}\n"
    "Stack trace: {stack_trace}\n"
    "Timestamp: {timestamp}"
)

DIAGNOSE_TOOL = {
    "name": "diagnose_error",
    "description": "Classify a microservice error and return structured analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "error_category": {
                "type": "string",
                "enum": [
                    "connectivity",
                    "resource_exhaustion",
                    "configuration",
                    "application_logic",
                ],
            },
            "root_cause_hypothesis": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "remediation_steps": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
        },
        "required": [
            "error_category",
            "root_cause_hypothesis",
            "confidence",
            "remediation_steps",
        ],
    },
}


def analyze_error(state: DiagnosticState) -> dict:
    """Call the LLM to classify the error in state['error_log']."""
    log = state["error_log"]
    prompt = DIAGNOSE_PROMPT.format(
        service_name=log["service_name"],
        error_type=log["error_type"],
        message=log["message"],
        stack_trace=log["stack_trace"] or "Not provided",
        timestamp=log["timestamp"],
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=_MODEL,
            max_tokens=1024,
            tools=[DIAGNOSE_TOOL],
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        return {
            "analysis_result": None,
            "analysis_error": f"Anthropic API error: {exc}",
        }

    tool_block = next(
        (b for b in response.content if b.type == "tool_use" and b.name == "diagnose_error"),
        None,
    )
    if tool_block is None:
        return {
            "analysis_result": None,
            "analysis_error": "LLM returned no tool_use block for diagnose_error",
        }

    data = tool_block.input
    result = AnalysisResult(
        error_category=data["error_category"],
        root_cause_hypothesis=data["root_cause_hypothesis"],
        confidence=data["confidence"],
        remediation_steps=data["remediation_steps"],
    )
    return {"analysis_result": result, "analysis_error": None}
