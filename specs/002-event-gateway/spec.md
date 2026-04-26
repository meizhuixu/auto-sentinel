# Feature Specification: Sprint 2 - Cloud-Native Event Gateway & Async Queue

**Feature Branch**: `002-event-gateway`  
**Created**: 2026-04-25  
**Status**: Draft  
**Input**: User description: "Sprint 2 - Cloud-Native Event Gateway & Async Queue"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Accept Alert Without Blocking (Priority: P1)

An operator or external monitoring system sends a crash-log payload to the service's alert endpoint. The service immediately acknowledges receipt and returns an acceptance confirmation — without waiting for the full diagnostic pipeline to finish. The operator can continue sending more alerts without waiting.

**Why this priority**: Non-blocking ingestion is the fundamental contract of an async event gateway. All other stories depend on this behavior. If the endpoint blocks, the system cannot scale.

**Independent Test**: Can be fully tested by POSTing a valid crash-log JSON to the alerts endpoint and verifying the response arrives immediately with the correct acceptance status and a job identifier — without any diagnostic output needing to exist.

**Acceptance Scenarios**:

1. **Given** the service is running, **When** an operator POSTs a valid crash-log JSON to `/api/v1/alerts`, **Then** the service responds with `202 Accepted` within 50ms and a response body containing a unique job ID.
2. **Given** the service is running, **When** an operator POSTs a payload missing required fields (e.g., `service_name`), **Then** the service responds with `422 Unprocessable Entity` and a human-readable error describing the missing field.
3. **Given** the service is running, **When** an operator sends a malformed JSON body, **Then** the service responds with `422 Unprocessable Entity`.

---

### User Story 2 - Automatic Background Diagnosis (Priority: P2)

After an alert is accepted, the system automatically processes it through the Sprint 1 diagnostic pipeline in the background, producing a diagnostic report on disk — without any further action from the operator.

**Why this priority**: Background processing is the core value proposition of the async architecture. Without it, the 202 response is meaningless — the alert would be accepted but never diagnosed.

**Independent Test**: Can be tested by POSTing an alert, waiting a short period, and then confirming that a diagnostic report has been written to disk for that alert — all without the operator doing anything after the initial POST.

**Acceptance Scenarios**:

1. **Given** a valid alert has been accepted (202), **When** sufficient time has passed for processing, **Then** a diagnostic report file exists on disk for that alert.
2. **Given** a valid alert has been accepted, **When** the pipeline produces a diagnosis, **Then** the report accurately reflects the error category and remediation steps from the Sprint 1 engine.
3. **Given** 10 alerts are submitted in rapid succession, **When** all are accepted, **Then** all 10 reports are eventually written with zero loss.

---

### User Story 3 - Structured Observability Trace (Priority: P3)

An operator monitoring the service can observe structured log events at each meaningful stage of an alert's lifecycle — when it is received, when it enters the queue, and when processing completes or fails — using standard log tooling.

**Why this priority**: Required by Constitution Principle IV (Observability). Enables operators to trace alerts, diagnose stuck jobs, and confirm the system is healthy. Builds on US1 and US2.

**Independent Test**: Can be tested by capturing the service's log output while submitting an alert and confirming that exactly three structured log events are emitted — one at receipt, one at enqueue, and one at pipeline completion — each containing the job ID and relevant metadata.

**Acceptance Scenarios**:

1. **Given** an alert is submitted, **When** the full lifecycle completes, **Then** structured log entries for "alert_received", "alert_queued", and "processing_completed" are emitted, each containing the job ID.
2. **Given** the pipeline fails to process an alert (e.g., bad log data), **When** the error occurs, **Then** a "processing_failed" structured log entry is emitted with the error reason and job ID.

---

### Edge Cases

- What happens when the service receives an alert while a previous alert is still being processed? (Queue must buffer without blocking.)
- What happens when the diagnostic pipeline raises an unhandled exception for one alert? (Other queued alerts must not be affected.)
- What happens when the alert payload contains extra unknown fields? (Service should accept the payload, ignoring unknown fields.)
- What happens when the service is shut down with items still in the queue? (In-memory queue; items in flight may be lost — acceptable for Sprint 2.)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST expose a `POST /api/v1/alerts` endpoint that accepts a JSON crash-log payload.
- **FR-002**: The endpoint MUST return `202 Accepted` immediately without blocking on pipeline execution.
- **FR-003**: The response body MUST include a unique `job_id` for the accepted alert.
- **FR-004**: The endpoint MUST validate that the payload contains all required fields: `service_name`, `error_type`, `message`, `timestamp`.
- **FR-005**: The endpoint MUST return `422 Unprocessable Entity` for malformed or schema-invalid payloads.
- **FR-006**: System MUST enqueue each accepted alert payload for asynchronous background processing.
- **FR-007**: System MUST process queued alerts using the Sprint 1 diagnostic engine asynchronously, without blocking the API server.
- **FR-008**: System MUST emit a structured log event when an alert is received, when it is queued, and when processing completes or fails.
- **FR-009**: Each structured log event MUST include the `job_id`, `service_name`, and a `status` field.
- **FR-010**: Tests for all API routes and background processing behavior MUST be written before any implementation (Test-First gate — Constitution Principle III NON-NEGOTIABLE).

### Key Entities

- **AlertPayload**: The JSON body submitted to the alerts endpoint. Contains `service_name`, `error_type`, `message`, `timestamp`, and optional `stack_trace`.
- **AlertJob**: A unit of work that has been accepted and is pending or in-progress in the background queue. Carries a `job_id`, the original `AlertPayload`, and its `status`.
- **ProcessingEvent**: A structured log record emitted at each lifecycle transition of an `AlertJob` (received → queued → processing_completed / processing_failed).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The alert ingestion endpoint responds with `202 Accepted` in under 50ms for any valid payload, regardless of queue depth.
- **SC-002**: Every accepted alert is eventually processed and produces a diagnostic report on disk, with zero message loss during normal operation within a single server lifetime.
- **SC-003**: Each alert lifecycle emits at minimum 3 structured log events (received, queued, completed/failed), each containing a traceable job identifier.
- **SC-004**: The service handles 50 concurrent alert submissions without dropping or misprocessing any alert.
- **SC-005**: Test-First gate: all route and background-processing tests committed and confirmed failing before any implementation is committed.

## Assumptions

- The background queue is in-memory only; alert durability across service restarts is out of scope for Sprint 2.
- The API server runs as a single process; multi-process or distributed queue (Redis, Kafka) is deferred to a future sprint.
- Authentication and authorization for the alert endpoint are out of scope for Sprint 2.
- The Sprint 1 diagnostic pipeline is available, stable, and correct; Sprint 2 does not modify it.
- Alert payloads represent individual crash-log events (one alert = one diagnostic job); batch ingestion is out of scope.
- The `stack_trace` field in the alert payload is optional, consistent with the Sprint 1 error log schema.
