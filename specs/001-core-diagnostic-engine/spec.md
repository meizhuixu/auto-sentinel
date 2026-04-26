# Feature Specification: Core Diagnostic AI Engine

**Feature Branch**: `001-core-diagnostic-engine`
**Created**: 2026-04-24
**Status**: Draft
**Input**: User description: "Sprint 1 - Core Diagnostic AI Engine (Local LangGraph Pipeline)"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Analyze a Crash Log and Receive a Diagnostic Report (Priority: P1)

A developer working on a distributed microservice system has a JSON error log from
a crashed service. They run the diagnostic engine locally, pointing it at the log
file. The engine processes the log through a multi-agent LangGraph pipeline and
produces a markdown report explaining the root cause and recommended remediation steps.

**Why this priority**: This is the entire purpose of Sprint 1. Without a working
end-to-end pipeline from log input to diagnostic report output, no other work in
this sprint has value.

**Independent Test**: Can be fully tested by providing a known sample JSON log file
and asserting that the output markdown report contains the expected root cause
classification and at least one remediation recommendation.

**Acceptance Scenarios**:

1. **Given** a valid JSON error log file exists in the `data/` directory,
   **When** the diagnostic engine is invoked with the file path,
   **Then** a markdown diagnostic report is written to the `output/` directory
   containing a root cause summary and at least one remediation step.

2. **Given** a JSON error log containing a known error pattern (e.g., database
   connection timeout),
   **When** the pipeline completes,
   **Then** the report correctly classifies the error category (e.g., "connectivity",
   "resource exhaustion", "configuration") and does not produce a generic fallback
   message.

3. **Given** the pipeline executes successfully,
   **When** inspecting the execution trace,
   **Then** each named graph node (`parse_log`, `analyze_error`, `format_report`)
   MUST have executed exactly once in the correct order.

---

### User Story 2 - Handle Malformed or Incomplete Log Input Gracefully (Priority: P2)

A developer accidentally points the engine at a truncated or structurally invalid
JSON file. The system MUST not crash silently or produce a misleading report; it
MUST surface a clear, actionable error message.

**Why this priority**: Robust error handling is necessary before the engine is used
against real microservice logs, which are frequently noisy or incomplete.

**Independent Test**: Can be fully tested by providing intentionally malformed JSON
fixtures and asserting the error output message and exit behaviour, with no
dependency on P1 report generation.

**Acceptance Scenarios**:

1. **Given** the input file contains syntactically invalid JSON,
   **When** the engine is invoked,
   **Then** it exits with a non-zero status code and emits a human-readable error
   message identifying the file and the nature of the parse failure.

2. **Given** the input file is valid JSON but missing required fields (e.g., no
   `timestamp` or `service_name`),
   **When** the engine processes it,
   **Then** it emits a warning listing the missing fields and either halts or
   produces a partial report clearly marked as incomplete.

---

### Edge Cases

- What happens when the `data/` directory does not exist or is empty?
  The engine MUST exit with a descriptive error rather than a traceback.
- What happens when the LLM call inside `analyze_error` returns an empty or
  malformed response? The node MUST detect this and propagate a structured error
  through graph state rather than silently writing an empty report.
- What happens when the same log file is processed twice? Idempotent behaviour is
  expected; the second run MUST overwrite the previous report without side effects.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST read a JSON log file from a caller-specified path
  under the `data/` directory.
- **FR-002**: The system MUST implement a LangGraph `StateGraph` with at least
  three distinct, named nodes: `parse_log`, `analyze_error`, and `format_report`.
- **FR-003**: The `parse_log` node MUST extract and validate the following fields
  from the log: `timestamp`, `service_name`, `error_type`, `message`, and
  `stack_trace` (optional).
- **FR-004**: The `analyze_error` node MUST classify the error into a named
  category (connectivity, resource exhaustion, configuration, or application logic)
  and produce a root cause hypothesis with a confidence indicator.
- **FR-005**: The `format_report` node MUST produce a markdown document containing:
  the original error summary, the root cause classification, the confidence level,
  and at least one remediation recommendation.
- **FR-006**: The system MUST write the markdown report to an `output/` directory,
  named after the source log file (e.g., `data/crash-001.json` →
  `output/crash-001-report.md`). The `output/` directory MUST be created if absent.
- **FR-007**: The system MUST return structured errors for missing required fields
  or malformed JSON, without raising unhandled exceptions.
- **FR-008**: Pytest test cases for each node MUST be written and confirmed failing
  before any node implementation is written (constitution Principle III — Test-First).
- **FR-009**: The system MUST run entirely locally with no web server, no Docker,
  and no network dependency beyond the LLM API call inside `analyze_error`.

### Key Entities

- **ErrorLog**: Parsed representation of an incoming JSON log; carries `timestamp`,
  `service_name`, `error_type`, `message`, and optional `stack_trace`.
- **DiagnosticState**: Shared LangGraph graph state passed between nodes; accumulates
  the `ErrorLog`, the analysis result, and the final report text.
- **AnalysisResult**: Output of `analyze_error`; carries `error_category`,
  `root_cause_hypothesis`, `confidence`, and `remediation_steps` (list).
- **DiagnosticReport**: The final markdown string produced by `format_report` and
  written to disk.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Given a valid sample log, the full pipeline (parse → analyze → report)
  completes without error and produces a non-empty markdown report in under 30
  seconds on a developer laptop.
- **SC-002**: The `analyze_error` node correctly classifies the error category for
  all 3 provided sample log fixtures covering distinct error types (100% accuracy
  on known fixtures).
- **SC-003**: All pytest tests are committed before implementation files exist in
  the repository, verifiable by git commit order.
- **SC-004**: The test suite achieves 100% branch coverage of all three graph
  nodes (happy path + error path per node) with zero failures on `main`.
- **SC-005**: A malformed JSON input causes a non-zero exit and a human-readable
  error message, verified by a dedicated automated test case.

## Assumptions

- The LLM used inside `analyze_error` is accessible via an API key stored in an
  environment variable (e.g., `ANTHROPIC_API_KEY`); no key management UI is needed.
- Sample JSON log files representing at least three distinct microservice error
  types will be hand-crafted and placed in `data/` as development fixtures.
- Python 3.10+ and `pip` (or `uv`) are available in the developer's local
  environment; no containerisation or venv bootstrapping script is in scope.
- The diagnostic report format (markdown) is sufficient for Sprint 1; rendering
  or serving the report via a UI is explicitly out of scope.
- LangGraph is available as a standard PyPI package; no custom fork or vendored
  version is required.
