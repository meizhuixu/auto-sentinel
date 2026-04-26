# Research: Core Diagnostic AI Engine

**Branch**: `001-core-diagnostic-engine` | **Date**: 2026-04-24
**Phase**: 0 — resolves all technical unknowns before design begins

---

## Decision 1: LangGraph StateGraph API Pattern

**Decision**: Use `TypedDict` for state, node functions return partial-state dicts,
conditional edges for error routing. Use `START` / `END` sentinels from
`langgraph.graph`.

**Rationale**: LangGraph's canonical pattern since v0.1; TypedDict is lightweight
(no runtime overhead vs. Pydantic BaseModel), and partial-state returns mean each
node only declares what it changes — downstream nodes see accumulated state.

**Minimal working pattern**:
```python
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, START, END

class DiagnosticState(TypedDict):
    log_path: str
    error_log: Optional[dict]
    analysis_result: Optional[dict]
    report_text: Optional[str]
    parse_error: Optional[str]
    analysis_error: Optional[str]

def parse_log(state: DiagnosticState) -> dict:
    ...
    return {"error_log": parsed, "parse_error": None}

builder = StateGraph(DiagnosticState)
builder.add_node("parse_log", parse_log)
builder.add_edge(START, "parse_log")
# conditional edge after parse_log...
graph = builder.compile()
result = graph.invoke({"log_path": "data/crash.json", ...})
```

**Alternatives considered**:
- Pydantic `BaseModel` for state: adds validation but is slower and requires
  `model_copy()` patterns; unnecessary overhead for Sprint 1.
- Dataclass for state: not supported natively by LangGraph's reducer logic.

---

## Decision 2: Error Propagation Strategy

**Decision**: Nodes MUST catch exceptions internally, store structured error info
in a dedicated state field (e.g., `parse_error`, `analysis_error`), and return
immediately. Conditional edges route to `END` when an error field is set.

**Rationale**: LangGraph has no automatic exception-to-state bridge; an unhandled
exception halts the graph with no structured output. Storing errors in state lets
the graph remain in a known, inspectable terminal state and satisfies FR-007.

**Pattern**:
```python
def parse_log(state: DiagnosticState) -> dict:
    try:
        ...
    except json.JSONDecodeError as e:
        return {"parse_error": f"Invalid JSON in {state['log_path']}: {e}"}

def route_after_parse(state: DiagnosticState) -> str:
    return END if state.get("parse_error") else "analyze_error"

builder.add_conditional_edges("parse_log", route_after_parse)
```

**Alternatives considered**:
- Raising exceptions from nodes: aborts the graph with no structured output.
- A dedicated error-handler node: adds complexity without benefit for Sprint 1's
  linear pipeline.

---

## Decision 3: LLM Model Selection

**Decision**: Use `claude-haiku-4-5-20251001` (Claude Haiku 4.5) for the
`analyze_error` node in Sprint 1.

**Rationale**: Error classification with structured output (4 categories +
confidence + remediation steps) is a structured extraction task, not complex
multi-step reasoning. Haiku 4.5 is 3× faster and significantly cheaper than
Sonnet while being fully capable of this task. Sprint 1 is a local development
tool; minimising iteration latency matters more than maximum reasoning depth.

**Upgrade path**: Swap to `claude-sonnet-4-6` in later sprints when the engine
handles novel, uncategorised errors requiring deeper reasoning.

**Alternatives considered**:
- `claude-sonnet-4-6`: Better analysis quality but ~3× slower for local dev.
- Open-source local LLM (Ollama): Eliminates API dependency but requires 8+ GB
  RAM, complex setup, and worse structured-output reliability — incompatible with
  the "pure Python, local" Sprint 1 constraint.

---

## Decision 4: Structured Output Approach

**Decision**: Use the Anthropic Python SDK's tool_use API to enforce a typed
output schema for `analyze_error`. Define a single tool `diagnose_error` whose
`input_schema` maps exactly to `AnalysisResult`.

**Rationale**: Tool_use is the most reliable way to get structured JSON from
Claude without post-processing text. The model is constrained to populate the
schema fields; free-form hallucinations in the action fields are not possible.
This directly satisfies constitution Principle V (LLM Reasoning Reliability):
"Every LLM call that produces an action plan MUST include a structured output
schema; free-form text responses MUST NOT be parsed as executable instructions."

**Tool definition**:
```python
DIAGNOSE_TOOL = {
    "name": "diagnose_error",
    "description": "Classify a microservice error and return structured analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "error_category": {
                "type": "string",
                "enum": ["connectivity", "resource_exhaustion",
                         "configuration", "application_logic"]
            },
            "root_cause_hypothesis": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "remediation_steps": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1
            }
        },
        "required": ["error_category", "root_cause_hypothesis",
                     "confidence", "remediation_steps"]
    }
}
```

**Extracting the result**:
```python
for block in response.content:
    if block.type == "tool_use" and block.name == "diagnose_error":
        return block.input  # already a typed dict matching AnalysisResult
```

**Alternatives considered**:
- Prompt engineering + JSON parsing: unreliable; model may deviate from schema.
- `instructor` library: adds a dependency and wraps tool_use internally anyway.
- Pydantic `model_validate` on raw text output: brittle; fails on any prose prefix.

---

## Decision 5: Testing Strategy

**Decision**: Unit-test each node function in isolation by calling it directly
with a crafted state dict and mocking the Anthropic client via
`unittest.mock.patch`. Use `pytest-cov` for branch coverage reporting.

**Rationale**: LangGraph provides no built-in test utilities. Node functions are
plain Python callables that take and return dicts — they can be tested without
constructing a full graph. Mocking the Anthropic client eliminates network
dependency in CI and makes tests deterministic.

**Unit test pattern**:
```python
from unittest.mock import patch, MagicMock

@patch("autosentinel.nodes.analyze_error.anthropic.Anthropic")
def test_analyze_error_happy_path(mock_client_cls):
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(type="tool_use", name="diagnose_error", input={
            "error_category": "connectivity",
            "root_cause_hypothesis": "DB host unreachable",
            "confidence": 0.92,
            "remediation_steps": ["Check DB host DNS", "Verify firewall rules"]
        })
    ]
    mock_client_cls.return_value.messages.create.return_value = mock_response

    state = {"error_log": {...}, "analysis_result": None, "analysis_error": None}
    result = analyze_error(state)
    assert result["analysis_result"]["error_category"] == "connectivity"
```

**Node execution order verification** (integration test):
Use intermediate state assertions — since each node populates a different state
field, asserting `result["analysis_result"] is not None` after a full `.invoke()`
proves `analyze_error` ran. For explicit ordering, use `graph.stream()`:
```python
executed = []
for chunk in graph.stream(initial_state):
    executed.extend(chunk.keys())
assert executed == ["parse_log", "analyze_error", "format_report"]
```

**Alternatives considered**:
- LangSmith for tracing: requires external service, overkill for Sprint 1.
- `interrupt_after` config: useful for interactive debugging, not CI assertions.

---

## Decision 6: Prompt Template Versioning

**Decision**: Store the `analyze_error` prompt template as a module-level
constant in `autosentinel/nodes/analyze_error.py`, versioned in git with the
source code.

**Rationale**: Constitution Principle V requires prompt templates to be
"versioned and tested like source code." Storing them as Python string constants
(not external files or a prompt registry) satisfies this for Sprint 1 with zero
additional tooling.

**Alternatives considered**:
- External `.txt` / `.jinja2` template files: adds file I/O and loading logic.
- A dedicated prompt registry service: appropriate for Sprint 3+; overkill now.
