# Feature Specification: Sprint 3 - Secure Docker Sandbox Execution

**Feature Branch**: `003-docker-sandbox`  
**Created**: 2026-04-26  
**Status**: Draft  
**Input**: User description: "Sprint 3 - Secure Docker Sandbox Execution"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safe Remediation Script Execution (Priority: P1)

After an error is diagnosed, the system automatically generates a remediation script and executes it inside an isolated, temporary container. The operator receives both the diagnostic report and the script's execution outcome — including its output and whether it succeeded — without the script ever touching the host system or other services.

**Why this priority**: Safe, sandboxed execution is the core value of Sprint 3. It directly fulfills Constitution Principle I (AI Agent Sandboxing) and is the prerequisite for all self-healing automation. Without it, generated remediation scripts cannot be trusted to run anywhere.

**Independent Test**: Can be fully tested by providing a diagnosis result with a remediation script, then confirming the system returns an execution record containing the script output, return code, and a "container destroyed" confirmation — without any changes to the host filesystem or processes.

**Acceptance Scenarios**:

1. **Given** a diagnosis with a remediation script, **When** the pipeline reaches the execution stage, **Then** the script runs inside an isolated container and its stdout/stderr and return code are captured.
2. **Given** the script completes (success or failure), **When** the container finishes, **Then** the container is forcefully destroyed — no dangling containers remain on the host.
3. **Given** the script exceeds the execution time limit, **When** the timeout triggers, **Then** the container is killed and destroyed, and a timeout error is recorded in the execution result.

---

### User Story 2 - Execution Results Included in Diagnostic Report (Priority: P2)

The markdown diagnostic report produced at the end of the pipeline includes a dedicated section showing whether the remediation script ran successfully, the captured output, and the return code — giving operators a single document covering both the diagnosis and the remediation attempt.

**Why this priority**: Operators need a single artifact to understand both what went wrong and what was attempted. Builds directly on US1.

**Independent Test**: Can be tested by running the full pipeline end-to-end and asserting that the generated report file contains a "Sandbox Execution" section with output and return code fields.

**Acceptance Scenarios**:

1. **Given** a completed execution, **When** the report is generated, **Then** it contains a "Sandbox Execution" section with `return_code`, `stdout`, and `stderr` values.
2. **Given** a timeout or container error during execution, **When** the report is generated, **Then** the report clearly states that the execution failed and includes the error reason.

---

### User Story 3 - Graceful Handling of Docker Unavailability (Priority: P3)

If the Docker daemon is unavailable or the container fails to start, the pipeline continues and produces a diagnostic report — noting the execution failure — rather than crashing the entire pipeline.

**Why this priority**: The diagnostic value of Sprint 1 and 2 must not be lost if Docker is unavailable in an environment. Resilience preserves the core value of the system.

**Independent Test**: Can be tested by simulating a Docker connection failure and asserting that the pipeline completes, the report is written, and the execution error is recorded — with no unhandled exception.

**Acceptance Scenarios**:

1. **Given** the Docker daemon is unreachable, **When** the pipeline runs, **Then** the `execute_fix` node captures the connection error, sets an `execution_error` field, and the pipeline continues to `format_report`.
2. **Given** the container fails to start, **When** the error is encountered, **Then** the execution result records the failure and no dangling container is left behind.

---

### Edge Cases

- What happens if the remediation script itself crashes the container process? (Return code is non-zero; container is still destroyed; error is recorded.)
- What happens if the script produces no output? (Empty stdout/stderr is recorded; execution is considered complete.)
- What happens if the container image is not available locally? (Docker pulls it automatically; if pull fails, the error is treated as a container-start failure.)
- What happens if `analyze_error` produces no remediation script? (The `execute_fix` node skips execution and sets `execution_skipped` status.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The diagnostic pipeline MUST include a new `execute_fix` node that runs after `analyze_error`.
- **FR-002**: The `analyze_error` node MUST add a `fix_script` field to the pipeline state containing a generated remediation script string.
- **FR-003**: The `execute_fix` node MUST spin up a temporary, lightweight container to execute the `fix_script`.
- **FR-004**: Container execution MUST be subject to a strict timeout (default: 5 seconds); the container MUST be killed if the timeout is exceeded.
- **FR-005**: The container MUST be forcefully destroyed after execution completes, regardless of success, failure, or timeout.
- **FR-006**: The `execute_fix` node MUST capture the script's stdout, stderr, and return code and store them in the pipeline state.
- **FR-007**: If the Docker daemon is unavailable or the container fails to start, the pipeline MUST NOT crash — the error MUST be captured in an `execution_error` state field and the pipeline MUST continue to `format_report`.
- **FR-008**: The `format_report` node MUST include a "Sandbox Execution" section in the markdown report with the execution outcome (return code, stdout, stderr, or error reason).
- **FR-009**: Tests for the `execute_fix` node MUST mock the Docker SDK client and MUST be written before any implementation (Test-First gate — Constitution Principle III NON-NEGOTIABLE).

### Key Entities

- **FixScript**: A string containing the remediation script generated by `analyze_error`. Stored in `DiagnosticState`.
- **ExecutionResult**: The outcome of running the fix script in the container. Contains `return_code`, `stdout`, `stderr`, `duration_ms`, and `status` (`success`, `timeout`, `error`, `skipped`).
- **DiagnosticState** (extended): Gains two new fields — `fix_script: Optional[str]` and `execution_result: Optional[ExecutionResult]`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every successful execution run leaves zero dangling containers on the host after pipeline completion.
- **SC-002**: Scripts that exceed the 5-second timeout are terminated and their containers destroyed within 1 second of the timeout triggering.
- **SC-003**: The diagnostic report always contains a "Sandbox Execution" section when the `execute_fix` node runs — regardless of whether execution succeeded, failed, or timed out.
- **SC-004**: If Docker is unavailable, the pipeline completes and produces a valid diagnostic report with the execution error noted — no unhandled exception is raised.
- **SC-005**: Test-First gate: all `execute_fix` and updated `format_report` tests committed and confirmed failing before any implementation is committed.

## Assumptions

- Docker Desktop (or Docker Engine) is installed and running on the developer's machine for integration testing; unit tests mock the Docker SDK.
- The container image (`python:3.10-alpine`) may need to be pulled on first use; pull time is not counted against the execution timeout.
- The remediation script is a single Python script string; multi-file execution and dependency installation are out of scope for Sprint 3.
- The `fix_script` is generated deterministically by the mock `analyze_error` node; LLM-based script generation is deferred to a future sprint.
- Container resource limits (CPU, memory, network) are applied as Docker run options; exact limit values are defined at implementation time.
- The `execute_fix` node runs synchronously within the LangGraph pipeline (no async); `asyncio.to_thread` is out of scope for this node in Sprint 3.
