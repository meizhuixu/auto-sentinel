# Implementation Plan: Core Diagnostic AI Engine

**Branch**: `001-core-diagnostic-engine` | **Date**: 2026-04-24 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/001-core-diagnostic-engine/spec.md`

## Summary

Build a local Python module (`autosentinel`) that reads a JSON microservice crash
log from `data/`, runs it through a three-node LangGraph `StateGraph`
(`parse_log` → `analyze_error` → `format_report`), and writes a markdown
diagnostic report to `output/`. The `analyze_error` node calls Claude Haiku 4.5
via Anthropic's tool_use API for structured error classification. Tests are
written and confirmed failing before any node implementation (constitution
Principle III — Test-First, NON-NEGOTIABLE).

## Technical Context

**Language/Version**: Python 3.10+
**Primary Dependencies**: `langgraph` (latest stable), `anthropic` (latest stable)
**Storage**: Local filesystem — JSON files in `data/`, markdown reports in `output/`
**Testing**: `pytest`, `pytest-cov` (branch coverage), `unittest.mock` (LLM mocking)
**Target Platform**: Developer laptop (macOS / Linux); no server, no Docker
**Project Type**: Local Python library + CLI module (`python -m autosentinel`)
**Performance Goals**: Full pipeline completes in < 30 seconds on a developer laptop
**Constraints**: No web server, no FastAPI, no Docker in Sprint 1; local-only
  except the Anthropic API call inside `analyze_error`
**Scale/Scope**: Sprint 1 MVP; single log file per invocation; 3 sample fixtures

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. AI Agent Sandboxing | ⚠️ EXCEPTION | No Docker in Sprint 1 (explicit scope constraint in spec). Justified in Complexity Tracking. Docker isolation deferred to Sprint 2. |
| II. Self-Healing First (MTTR) | ✅ | Diagnostic engine is the foundational analysis layer for future MTTR reduction. No MTTR target applies to the engine itself. |
| III. Test-First (NON-NEGOTIABLE) | ✅ | FR-008 + SC-003 mandate tests written and failing before implementation. Enforced by git commit order. |
| IV. Observability & Distributed Tracing | ✅ (Sprint 1 scope) | Engine emits structured progress logs to stdout. W3C trace propagation deferred to Sprint 2+ (no distributed services yet). |
| V. LLM Reasoning Reliability | ✅ | `analyze_error` uses Anthropic tool_use (typed schema). `AnalysisResult.confidence` field present. Prompt template versioned as Python constant. No production state mutation → action manifest not applicable. |

**Post-design re-check**: All ✅ gates hold after Phase 1 design. Principle I
exception documented in Complexity Tracking below.

## Project Structure

### Documentation (this feature)

```text
specs/001-core-diagnostic-engine/
├── plan.md              # This file
├── research.md          # Phase 0 — technical decisions
├── data-model.md        # Phase 1 — entity definitions and state schema
├── quickstart.md        # Phase 1 — developer setup guide
├── contracts/
│   └── python-interface.md  # Phase 1 — public API + node contracts
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
autosentinel/            # Python package
├── __init__.py          # exposes run_pipeline()
├── models.py            # ErrorLog, AnalysisResult, DiagnosticState TypedDicts
├── graph.py             # build_graph() — StateGraph assembly and compilation
└── nodes/
    ├── __init__.py
    ├── parse_log.py     # parse_log node — reads + validates JSON log
    ├── analyze_error.py # analyze_error node — Anthropic tool_use call
    └── format_report.py # format_report node — markdown generation + file write

data/                    # Sample JSON log fixtures (checked into version control)
├── crash-connectivity.json
├── crash-resource.json
└── crash-config.json

output/                  # Generated reports — gitignored

tests/
├── __init__.py
├── conftest.py          # Shared pytest fixtures (sample state dicts, mock factories)
├── unit/
│   ├── test_parse_log.py       # parse_log happy + error paths
│   ├── test_analyze_error.py   # analyze_error happy + error paths (mocked LLM)
│   └── test_format_report.py   # format_report happy path + output file naming
└── integration/
    └── test_pipeline.py        # Full graph: correct output, node order, error routing

pyproject.toml           # Package metadata + dev dependencies
```

**Structure Decision**: Single-project layout (Option 1). No frontend/backend
split; no web layer. The `autosentinel/` package is the library; `__main__.py`
(or a `runner.py` entry point) provides the CLI. All paths are relative to the
repository root.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Principle I: No Docker isolation for `analyze_error` LLM agent | Sprint 1 scope constraint — spec explicitly prohibits Docker in this phase | Docker would be the correct solution; it is deferred, not dropped. Sprint 2 will containerise the engine. Running without Docker is a temporary, documented exception, not a permanent design choice. |

## Phase 0: Research Findings

All technical unknowns resolved. See [research.md](research.md) for full
rationale. Summary of key decisions:

- **LangGraph state**: `TypedDict` + partial-state returns from node functions
- **Error routing**: State fields (`parse_error`, `analysis_error`) + conditional
  edges to `END`; exceptions are caught inside nodes, never propagate to graph
- **LLM model**: `claude-haiku-4-5-20251001` (fast, cheap; sufficient for
  structured extraction); upgrade path to `claude-sonnet-4-6` in later sprints
- **Structured output**: Anthropic tool_use with `diagnose_error` tool schema;
  `block.input` is already a typed dict, no text parsing needed
- **Testing**: `unittest.mock.patch` on `anthropic.Anthropic`; direct node
  function calls for unit tests; `graph.stream()` for integration order assertion
- **Prompt versioning**: Module-level Python constant in `analyze_error.py`

## Phase 1: Design Artefacts

All Phase 1 artefacts are complete:

- **Data model**: [data-model.md](data-model.md) — defines `ErrorLog`,
  `AnalysisResult`, `DiagnosticState`, `DiagnosticReport` markdown structure,
  and the three sample fixture schemas
- **Contracts**: [contracts/python-interface.md](contracts/python-interface.md)
  — defines `run_pipeline()`, `build_graph()`, all three node function signatures,
  CLI contract (arguments + exit codes), and `DiagnosticError` exception
- **Quickstart**: [quickstart.md](quickstart.md) — install, API key, run,
  test, and troubleshooting

### Node Implementation Notes

**`parse_log`**:
- Open `state["log_path"]`; raise `FileNotFoundError` only if `data/` is missing
  (let the error bubble to `run_pipeline` which converts it); catch
  `json.JSONDecodeError` and missing-field errors internally → populate
  `parse_error`
- Required fields: `timestamp`, `service_name`, `error_type`, `message`
- `stack_trace` is optional; set to `None` if absent

**`analyze_error`**:
- Construct the Anthropic client; call `client.messages.create()` with the
  `diagnose_error` tool and `claude-haiku-4-5-20251001`
- Extract `tool_use` block from response; validate it has the expected name
- Any `anthropic.APIError` or missing tool block → populate `analysis_error`
- Prompt template (versioned constant):
  ```
  You are a microservice reliability engineer. Analyse the following error log
  and use the diagnose_error tool to return a structured diagnosis.

  Service: {service_name}
  Error type: {error_type}
  Message: {message}
  Stack trace: {stack_trace or 'Not provided'}
  Timestamp: {timestamp}
  ```

**`format_report`**:
- Derive output filename: `Path(state["log_path"]).stem + "-report.md"` under
  `output/`
- Create `output/` with `Path.mkdir(parents=True, exist_ok=True)` before writing
- Overwrite silently if file exists (idempotent per spec edge case)
- Markdown structure defined in [data-model.md](data-model.md)

### Graph Wiring

```python
builder = StateGraph(DiagnosticState)
builder.add_node("parse_log", parse_log)
builder.add_node("analyze_error", analyze_error)
builder.add_node("format_report", format_report)

builder.add_edge(START, "parse_log")
builder.add_conditional_edges(
    "parse_log",
    lambda s: END if s.get("parse_error") else "analyze_error"
)
builder.add_conditional_edges(
    "analyze_error",
    lambda s: END if s.get("analysis_error") else "format_report"
)
builder.add_edge("format_report", END)
```
