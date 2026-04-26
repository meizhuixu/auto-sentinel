# Data Model: Sprint 2 - Cloud-Native Event Gateway & Async Queue

## Entities

### AlertPayload (API Request Body)

Represents the JSON body sent by an operator or external system to `POST /api/v1/alerts`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service_name` | `str` | ✅ | Name of the microservice that crashed |
| `error_type` | `str` | ✅ | Error class/type (e.g., `ConnectionTimeout`, `OOMKilled`) |
| `message` | `str` | ✅ | Human-readable error message |
| `timestamp` | `str` | ✅ | ISO 8601 UTC timestamp of the crash event |
| `stack_trace` | `str \| null` | ❌ | Optional stack trace text |

**Validation rules**:
- All required fields must be non-empty strings.
- Extra unknown fields are silently ignored (permissive ingestion).
- `timestamp` format is not strictly validated at the gateway (passed through to Sprint 1 engine).

**Relationship**: Maps directly to `ErrorLog` from Sprint 1 (same field set). When persisted to disk, the file contains this payload serialised as JSON with `stack_trace` defaulting to `null` if absent.

---

### AlertJobResponse (API Response Body — 202 Accepted)

Returned immediately when an alert is accepted.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `str` | UUID v4 uniquely identifying this diagnostic job |
| `status` | `str` | Always `"accepted"` for a 202 response |
| `message` | `str` | Human-readable confirmation (e.g., `"Alert accepted for processing"`) |

---

### AlertJob (Internal Queue Item)

An item held in the `asyncio.Queue` between acceptance and processing. Not exposed via the API.

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | `str` | Same UUID as in `AlertJobResponse` |
| `log_path` | `Path` | Absolute path to the persisted alert JSON file |
| `service_name` | `str` | Copied from payload for logging without re-reading the file |
| `enqueued_at` | `str` | ISO 8601 UTC timestamp when the job was added to the queue |

---

### ProcessingEvent (Structured Log Record)

Emitted to stdout as a JSON log line at each lifecycle transition of an `AlertJob`.

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | `str` | ISO 8601 UTC timestamp of the event |
| `severity` | `str` | `"INFO"` or `"ERROR"` |
| `component` | `str` | `"event_gateway"` |
| `correlation_id` | `str` | Same as `job_id` — enables log tracing |
| `trace_id` | `str` | Same as `job_id` in Sprint 2 (no distributed tracing yet) |
| `event` | `str` | One of: `alert_received`, `alert_queued`, `processing_started`, `processing_completed`, `processing_failed` |
| `event_payload` | `object` | Event-specific data (see below) |

**event_payload schemas by event type**:

| `event` | `event_payload` fields |
|---------|------------------------|
| `alert_received` | `{ service_name, error_type }` |
| `alert_queued` | `{ service_name, queue_depth }` |
| `processing_started` | `{ service_name, log_path }` |
| `processing_completed` | `{ service_name, report_path, duration_ms }` |
| `processing_failed` | `{ service_name, error, duration_ms }` |

---

## State Transitions

```text
HTTP Request
     │
     ▼
[AlertPayload validated]
     │  FR-004/FR-005: 422 on invalid
     ▼
[Persisted to data/incoming/{job_id}.json]
     │
     ▼
[AlertJob enqueued]  ──→  LOG: alert_received + alert_queued
     │
     │  202 Accepted + AlertJobResponse returned to caller
     ▼
[Background Worker picks up AlertJob]
     │  LOG: processing_started
     ▼
[run_pipeline(log_path) called in thread]
     │
     ├─ success ──→ LOG: processing_completed (report_path, duration_ms)
     │
     └─ error ───→ LOG: processing_failed (error, duration_ms)
```

---

## Persistent File Layout (Runtime)

```text
data/
├── crash-connectivity.json    # Sprint 1 fixtures (committed)
├── crash-resource.json
├── crash-config.json
└── incoming/                  # Runtime-only, gitignored
    └── {job_id}.json          # One file per accepted alert

output/                        # gitignored
└── {job_id}-report.md         # One report per successfully processed alert
```
