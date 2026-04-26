# Python Interface Contract: Core Diagnostic AI Engine

**Module**: `autosentinel`
**Branch**: `001-core-diagnostic-engine` | **Date**: 2026-04-24

This document is the authoritative contract for the public Python API and the
internal node function signatures. Implementation MUST conform to these signatures.
Tests MUST be written against these signatures before implementation begins.

---

## Public API

### `autosentinel.run_pipeline`

The single public entry point for external callers and the CLI runner.

```python
def run_pipeline(log_path: str | Path) -> Path:
    """
    Run the full diagnostic pipeline on a JSON error log.

    Args:
        log_path: Path to the source JSON log file. May be relative (resolved
                  against CWD) or absolute.

    Returns:
        Path to the written markdown report (absolute path under output/).

    Raises:
        FileNotFoundError: if log_path does not exist.
        DiagnosticError: if the pipeline halts due to a parse or analysis failure.
                         The exception message contains the human-readable error
                         from DiagnosticState.parse_error or analysis_error.
    """
```

**DiagnosticError**:
```python
class DiagnosticError(Exception):
    """Raised when the pipeline exits via an error state."""
    pass
```

---

## Graph Assembly

### `autosentinel.graph.build_graph`

```python
def build_graph() -> CompiledGraph:
    """
    Assemble and compile the LangGraph StateGraph.

    Returns:
        A compiled LangGraph graph ready for .invoke() or .stream().

    Node execution order: parse_log → analyze_error → format_report
    Error routing: any node setting parse_error or analysis_error routes to END.
    """
```

---

## Node Function Signatures

Each node is a plain Python function satisfying the LangGraph node contract:
takes a `DiagnosticState` dict, returns a **partial** dict of updated fields.

### `autosentinel.nodes.parse_log`

```python
def parse_log(state: DiagnosticState) -> dict:
    """
    Read and validate the JSON log file at state['log_path'].

    Success return (partial state):
        {"error_log": ErrorLog, "parse_error": None}

    Failure return (partial state):
        {"parse_error": "<human-readable message>", "error_log": None}

    Failure conditions:
        - File does not exist
        - File content is not valid JSON
        - Any required field (timestamp, service_name, error_type, message) is
          absent or null
        - data/ directory does not exist
    """
```

### `autosentinel.nodes.analyze_error`

```python
def analyze_error(state: DiagnosticState) -> dict:
    """
    Call the LLM (Anthropic tool_use) to classify the error in state['error_log'].

    Precondition: state['error_log'] is not None and state['parse_error'] is None.

    Success return (partial state):
        {"analysis_result": AnalysisResult, "analysis_error": None}

    Failure return (partial state):
        {"analysis_error": "<human-readable message>", "analysis_result": None}

    Failure conditions:
        - Anthropic API call raises an exception
        - API response contains no tool_use block
        - Tool input fails schema validation
        - LLM confidence below 0.0 or above 1.0
    """
```

### `autosentinel.nodes.format_report`

```python
def format_report(state: DiagnosticState) -> dict:
    """
    Format state['analysis_result'] into a markdown string and write to output/.

    Precondition: state['analysis_result'] is not None.

    Success return (partial state):
        {"report_text": "<markdown string>", "report_path": "<absolute path str>"}

    The output filename is derived from the source log filename:
        data/crash-001.json → output/crash-001-report.md
    The output/ directory is created if it does not exist.
    An existing report at the same path is silently overwritten (idempotent).
    """
```

---

## CLI Contract

The module is invocable as a CLI script:

```
python -m autosentinel <log_path>
```

| Argument | Type | Required | Description |
|----------|------|----------|-------------|
| `log_path` | positional string | ✅ | Path to JSON log file |

**Exit codes**:

| Code | Meaning |
|------|---------|
| `0` | Pipeline completed; report written to `output/` |
| `1` | Pipeline halted with a `DiagnosticError`; message printed to stderr |
| `2` | Invalid argument (missing log path); usage printed to stderr |

---

## Type Aliases (reference)

```python
from typing import TypedDict, Optional

class ErrorLog(TypedDict):
    timestamp: str
    service_name: str
    error_type: str
    message: str
    stack_trace: Optional[str]

class AnalysisResult(TypedDict):
    error_category: str   # "connectivity" | "resource_exhaustion" |
                          # "configuration" | "application_logic"
    root_cause_hypothesis: str
    confidence: float     # 0.0 – 1.0
    remediation_steps: list[str]

class DiagnosticState(TypedDict):
    log_path: str
    error_log: Optional[ErrorLog]
    parse_error: Optional[str]
    analysis_result: Optional[AnalysisResult]
    analysis_error: Optional[str]
    report_text: Optional[str]
    report_path: Optional[str]
```
