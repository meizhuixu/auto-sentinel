# Implementation Plan: Sprint 2 - Cloud-Native Event Gateway & Async Queue

**Branch**: `002-event-gateway` | **Date**: 2026-04-25 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/002-event-gateway/spec.md`

## Summary

Extend the AutoSentinel package with a FastAPI-based HTTP gateway that exposes
`POST /api/v1/alerts`, immediately returns `202 Accepted`, enqueues the alert
into an `asyncio.Queue`, and processes it asynchronously via the Sprint 1
`run_pipeline()` function offloaded to a thread with `asyncio.to_thread`. A
long-running worker coroutine is managed by FastAPI's `lifespan` context manager.
Structured JSON logs are emitted at every lifecycle event (received → queued →
processing_started → completed/failed). All tests are written and confirmed
failing before any implementation (Constitution Principle III — NON-NEGOTIABLE).

## Technical Context

**Language/Version**: Python 3.10+  
**Primary Dependencies**: `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `httpx>=0.27` (new); `langgraph>=0.2`, `anthropic>=0.40` (Sprint 1, unchanged)  
**Storage**: Local filesystem — alert payloads in `data/incoming/` (gitignored), reports in `output/` (gitignored)  
**Testing**: `pytest`, `pytest-cov` (branch coverage), `starlette.testclient.TestClient` (sync ASGI test client)  
**Target Platform**: Developer laptop (macOS / Linux); single-process server; no Docker in Sprint 2  
**Project Type**: REST microservice (`uvicorn autosentinel.api.main:app`) + existing CLI  
**Performance Goals**: `POST /api/v1/alerts` responds in < 50ms (SC-001); 50 concurrent submissions without loss (SC-004)  
**Constraints**: In-memory queue only; no persistence across restarts; no auth; no distributed tracing (deferred to Sprint 3); Sprint 1 code MUST NOT be modified

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. AI Agent Sandboxing | ⚠️ EXCEPTION | Sprint 2 is an API gateway layer, not the AI agent itself. `run_pipeline()` (the agent component) still runs locally without Docker. Same exception as Sprint 1 — Docker isolation deferred to Sprint 3. Documented in Complexity Tracking. |
| II. Self-Healing First (MTTR) | ✅ | The gateway enables programmatic, automated alert ingestion — a prerequisite for closed-loop MTTR reduction pipelines in Sprint 3+. |
| III. Test-First (NON-NEGOTIABLE) | ✅ | FR-010 + SC-005 mandate tests written and confirmed failing before implementation. Enforced by git commit order. |
| IV. Observability & Distributed Tracing | ✅ | Structured JSON logs emitted at every lifecycle event with `correlation_id`, `trace_id`, `component`, `severity`, and `event_payload` — matching the schema in Constitution Principle IV. W3C Trace Context propagation deferred to Sprint 3 (no inter-service calls yet). |
| V. LLM Reasoning Reliability | ✅ | Passes through to Sprint 1 mock engine unchanged. No new LLM calls introduced. |

**Post-design re-check**: All ✅ gates hold after Phase 1 design. Principle I exception documented in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002-event-gateway/
├── plan.md              # This file
├── research.md          # Phase 0 — technical decisions
├── data-model.md        # Phase 1 — AlertPayload, AlertJob, ProcessingEvent
├── quickstart.md        # Phase 1 — server start, curl examples, troubleshooting
├── contracts/
│   └── rest-api.md      # Phase 1 — POST /api/v1/alerts contract + module interfaces
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
autosentinel/
├── __init__.py          # run_pipeline() — UNCHANGED from Sprint 1
├── __main__.py          # CLI — UNCHANGED from Sprint 1
├── models.py            # TypedDicts — UNCHANGED from Sprint 1
├── graph.py             # LangGraph graph — UNCHANGED from Sprint 1
├── nodes/               # parse_log, analyze_error, format_report — UNCHANGED
└── api/                 # NEW in Sprint 2
    ├── __init__.py
    ├── main.py          # FastAPI app factory, lifespan, POST /api/v1/alerts router
    ├── models.py        # AlertPayload (Pydantic), AlertJobResponse (Pydantic)
    ├── queue.py         # asyncio.Queue singleton, AlertJob dataclass, worker coroutine
    └── logging.py       # JSONFormatter, get_logger(component)

data/
├── crash-connectivity.json    # Sprint 1 fixtures (committed)
├── crash-resource.json
├── crash-config.json
└── incoming/                  # Runtime-only alert files (added to .gitignore)

output/                        # Generated reports (already gitignored)

tests/
├── __init__.py
├── conftest.py                # Extended with API fixtures (TestClient, mock queue)
├── unit/
│   ├── test_parse_log.py      # UNCHANGED
│   ├── test_analyze_error.py  # UNCHANGED
│   ├── test_format_report.py  # UNCHANGED
│   └── test_run_pipeline.py   # UNCHANGED
└── integration/
    ├── test_pipeline.py       # UNCHANGED
    └── test_api.py            # NEW: route tests + background processing tests

pyproject.toml                 # Updated: fastapi, uvicorn[standard], httpx added
```

**Structure Decision**: Single-project layout. Sprint 2 adds `autosentinel/api/` as a sub-package of the existing `autosentinel` package. All new source files live under `api/`; Sprint 1 files are untouched.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|--------------------------------------|
| Principle I: No Docker isolation for `run_pipeline()` agent | Sprint 2 scope is the API gateway layer; containerising the agent is Sprint 3 work | Docker would be correct for production; deferred, not dropped. Sprint 2 establishes the async ingestion pattern first. |

## Phase 0: Research Findings

All technical unknowns resolved. See [research.md](research.md) for full rationale. Summary of key decisions:

- **Queue**: `asyncio.Queue` (not `BackgroundTasks`) — explicit consumer, testable via `queue.join()`
- **Blocking offload**: `asyncio.to_thread(run_pipeline, path)` — non-blocking, Python 3.10+ compatible
- **Alert persistence**: Write payload to `data/incoming/{job_id}.json` → pass path to `run_pipeline()` unchanged
- **Structured logging**: stdlib `logging` + custom `JSONFormatter` — zero new dependency for log formatting
- **Testing**: `TestClient` (sync) + `queue.join()` for deterministic background drain
- **Lifecycle**: FastAPI `lifespan` async context manager (modern; `@app.on_event` is deprecated)
- **New deps**: `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `httpx>=0.27`

## Phase 1: Design Artefacts

All Phase 1 artefacts are complete:

- **Data model**: [data-model.md](data-model.md) — defines `AlertPayload`, `AlertJobResponse`, `AlertJob`, `ProcessingEvent` schema, state transitions, and persistent file layout
- **Contracts**: [contracts/rest-api.md](contracts/rest-api.md) — `POST /api/v1/alerts` request/response spec, module interface signatures, and complete test contract table
- **Quickstart**: [quickstart.md](quickstart.md) — install, server start, curl examples, structured log output examples, troubleshooting

### Module Implementation Notes

**`autosentinel/api/logging.py`**:
- `JSONFormatter` subclasses `logging.Formatter`; overrides `format()` to produce a single-line JSON string
- Schema: `{"timestamp", "severity", "component", "correlation_id", "trace_id", "event", "event_payload"}`
- `get_logger(component)` returns a `logging.Logger` with the formatter attached to a `StreamHandler(sys.stdout)`

**`autosentinel/api/models.py`**:
- `AlertPayload(BaseModel)`: five fields matching `ErrorLog`; `stack_trace` is `Optional[str] = None`
- `AlertJobResponse(BaseModel)`: `job_id: str`, `status: str`, `message: str`

**`autosentinel/api/queue.py`**:
- `AlertJob` is a `dataclass` with `job_id`, `log_path`, `service_name`, `enqueued_at`
- Module-level `_queue: asyncio.Queue = asyncio.Queue()`
- `get_queue()` returns `_queue` (for dependency injection in tests)
- `worker(queue)` loop: `item = await queue.get()` → `asyncio.to_thread(run_pipeline, item.log_path)` → `queue.task_done()` → log events. Handles `asyncio.CancelledError` to exit cleanly.

**`autosentinel/api/main.py`**:
- `create_app()` factory: creates `FastAPI(lifespan=lifespan)`
- `lifespan` async context: creates worker task on enter, cancels + awaits on exit
- `POST /api/v1/alerts` handler:
  1. Generate `job_id = str(uuid.uuid4())`
  2. Write `payload.model_dump()` to `data/incoming/{job_id}.json` (create dir if absent)
  3. Log `alert_received`
  4. Enqueue `AlertJob`
  5. Log `alert_queued` (with `queue.qsize()`)
  6. Return `AlertJobResponse(job_id, "accepted", "Alert accepted for processing")` with `status_code=202`
- Module-level `app = create_app()` for uvicorn entry point

**`tests/integration/test_api.py`**:
- Fixtures: `client` (`TestClient(app)` used as context manager to exercise lifespan); `mock_pipeline` (patches `autosentinel.api.queue.run_pipeline` to write a sentinel file and return its path)
- All 8 tests from the contract table (5 route + 3 background)
- `queue.join()` after POST to drain before assertions
