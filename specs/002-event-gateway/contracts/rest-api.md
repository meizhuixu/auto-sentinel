# REST API Contract: Event Gateway

**Component**: `autosentinel.api`  
**Base URL**: `http://localhost:8000` (development)  
**API Version**: `v1`

---

## POST /api/v1/alerts

Submit a crash-log alert for asynchronous diagnostic processing.

### Request

**Headers**:
```
Content-Type: application/json
```

**Body** (`AlertPayload`):
```json
{
  "service_name": "payment-service",
  "error_type": "ConnectionTimeout",
  "message": "Database connection timed out after 30s waiting for host db.internal:5432",
  "timestamp": "2026-04-24T10:15:00Z",
  "stack_trace": null
}
```

**Required fields**: `service_name`, `error_type`, `message`, `timestamp`  
**Optional fields**: `stack_trace` (defaults to `null` if omitted)  
**Extra fields**: Silently ignored

---

### Response: 202 Accepted

Returned immediately when the alert has been validated and enqueued.

```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "accepted",
  "message": "Alert accepted for processing"
}
```

**Timing guarantee**: Must respond in < 50ms regardless of queue depth (SC-001).

---

### Response: 422 Unprocessable Entity

Returned when the request body fails schema validation.

```json
{
  "detail": [
    {
      "loc": ["body", "service_name"],
      "msg": "Field required",
      "type": "missing"
    }
  ]
}
```

This is FastAPI/Pydantic's standard validation error format — no custom handling required.

---

## Module Interface Contract

### `autosentinel.api.main`

```python
from fastapi import FastAPI

def create_app() -> FastAPI:
    """
    Factory function that constructs and returns the FastAPI application instance.
    Registers the lifespan context manager (worker start/stop) and mounts all routers.
    Used by tests to create isolated app instances.
    """
```

### `autosentinel.api.queue`

```python
import asyncio
from pathlib import Path

async def get_queue() -> asyncio.Queue:
    """
    Returns the module-level asyncio.Queue singleton.
    Tests may replace this with a fresh queue instance for isolation.
    """

async def worker(queue: asyncio.Queue) -> None:
    """
    Long-running coroutine that consumes AlertJob items from the queue and
    calls run_pipeline() via asyncio.to_thread for each item.
    Emits structured log events at processing_started, processing_completed,
    and processing_failed transitions.
    Runs until cancelled (CancelledError is caught and loop exits cleanly).
    """
```

### `autosentinel.api.logging`

```python
import logging

def get_logger(component: str) -> logging.Logger:
    """
    Returns a Logger configured with JSONFormatter.
    Each call to logger.info/error should pass a dict as the `extra` keyword:
      logger.info("event", extra={
          "correlation_id": job_id,
          "trace_id": job_id,
          "event": "alert_received",
          "event_payload": {...}
      })
    Output is a single-line JSON string to stdout.
    """
```

---

## Test Contract

All tests MUST be written before implementation (Constitution Principle III).

### Route Tests (`tests/integration/test_api.py`)

| Test | Method | Input | Expected |
|------|--------|-------|----------|
| `test_post_alert_returns_202` | POST | valid payload | 202 + `job_id` in body |
| `test_post_alert_missing_field_returns_422` | POST | payload missing `service_name` | 422 |
| `test_post_alert_invalid_json_returns_422` | POST | `"not json"` | 422 |
| `test_post_alert_extra_fields_ignored` | POST | valid payload + extra fields | 202 |
| `test_post_alert_job_id_is_unique` | POST (×2) | two valid payloads | two distinct `job_id` values |

### Background Processing Tests (`tests/integration/test_api.py`)

| Test | Mechanism | Expected |
|------|-----------|----------|
| `test_background_worker_processes_queued_alert` | POST alert; `queue.join()`; check output dir | Report file exists |
| `test_background_worker_logs_lifecycle_events` | POST alert; `queue.join()`; inspect log output | 3+ structured JSON log lines with matching `job_id` |
| `test_background_worker_handles_pipeline_error` | POST alert with invalid body; `queue.join()` | `processing_failed` log emitted; no unhandled exception |
