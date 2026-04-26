# Research: Sprint 2 - Cloud-Native Event Gateway & Async Queue

## Decision 1: asyncio.Queue vs FastAPI BackgroundTasks

**Decision**: Use `asyncio.Queue` with a long-running worker coroutine started via FastAPI's `lifespan` context manager.

**Rationale**: `BackgroundTasks` runs each task independently with no queue semantics — there is no queue depth, no backpressure, and no way to drain/await the queue in tests. `asyncio.Queue` provides explicit producer-consumer decoupling, observable depth, and a worker that can be awaited in tests by calling `queue.join()` after submitting items.

**Alternatives considered**:
- `BackgroundTasks` (FastAPI built-in): Simpler but untestable at queue level; no backpressure or depth visibility.
- Celery + Redis: Persistent, distributed; massively over-engineered for a single-process Sprint 2 MVP.
- `concurrent.futures.ThreadPoolExecutor`: Thread-based; no async integration; harder to test.

---

## Decision 2: Running Blocking run_pipeline() from Async Context

**Decision**: Use `asyncio.to_thread(run_pipeline, path)` inside the worker coroutine.

**Rationale**: `run_pipeline()` is synchronous (blocking file I/O + CPU work). Calling it directly in a coroutine would block the event loop and prevent the server from accepting new requests during processing. `asyncio.to_thread` offloads the call to a thread-pool executor without blocking the loop. Available in Python 3.9+, matching the project's `>=3.10` requirement.

**Alternatives considered**:
- `loop.run_in_executor(None, ...)`: Equivalent, but more verbose; `asyncio.to_thread` is the idiomatic modern form.
- Making `run_pipeline()` async: Would require refactoring all of Sprint 1 — violates the no-Sprint-1-modification constraint.

---

## Decision 3: Alert Payload Persistence

**Decision**: Write each incoming alert JSON to `data/incoming/{job_id}.json` before queuing, and pass the file path to `run_pipeline()`.

**Rationale**: `run_pipeline()` accepts a `Path` to a JSON file — it cannot accept a raw dict. The simplest adapter is to materialise the alert as a file. `data/incoming/` is added to `.gitignore` to prevent runtime files from entering VCS. This preserves Sprint 1's file-based contract without modification.

**Alternatives considered**:
- Extend `run_pipeline()` to accept a dict: Modifies Sprint 1 code — out of scope.
- Write to a system temp dir (`tempfile.mkstemp`): Platform-specific paths; harder to inspect during development.
- Pass alert as a stdin pipe: Would require rewriting the CLI layer.

---

## Decision 4: Structured Logging Implementation

**Decision**: Use Python's stdlib `logging` module with a custom `JSONFormatter` subclass that serialises log records to JSON.

**Rationale**: Zero additional dependency. The formatter extracts `timestamp`, `severity`, `component`, `correlation_id` (job_id), and `event_payload` from the `LogRecord` extra dict — matching the schema required by Constitution Principle IV. All log output goes to stdout so container runtimes and log aggregators can capture it.

**Alternatives considered**:
- `python-json-logger` (third-party): Well-known but adds a dependency for functionality achievable in ~20 lines of stdlib code.
- `structlog`: Feature-rich but heavyweight; out of scope for Sprint 2.
- Plain f-string logs: Non-machine-readable; violates Constitution Principle IV.

---

## Decision 5: Testing Strategy for Async Background Processing

**Decision**: Use `starlette.testclient.TestClient` (synchronous) for route tests; mock `run_pipeline` with a side-effect that writes a sentinel file; call `queue.join()` to block until all items are consumed before asserting.

**Rationale**: `TestClient` runs the ASGI app in a thread, handles the event loop, and makes sync assertions straightforward. The `lifespan` context (including queue worker startup/shutdown) is fully exercised by `TestClient`. `queue.join()` gives a deterministic drain point — no `asyncio.sleep` polling needed.

**Alternatives considered**:
- `httpx.AsyncClient` + `pytest-asyncio`: Requires async test functions and adds `pytest-asyncio` dependency; the sync `TestClient` is sufficient.
- Polling `output/` directory: Non-deterministic timing; flaky under load.
- Mocking `asyncio.Queue`: Would test the mock, not the behaviour.

---

## Decision 6: FastAPI Application Lifecycle

**Decision**: Use the `lifespan` async context manager (FastAPI 0.93+) to start and cancel the worker coroutine.

**Rationale**: The `@app.on_event("startup"/"shutdown")` pattern is deprecated in modern FastAPI. `lifespan` is the current idiomatic approach: it starts the queue worker as an `asyncio.Task` on startup and cancels it cleanly on shutdown. `TestClient` automatically invokes the lifespan context when used as a context manager (`with TestClient(app) as client: ...`).

**Alternatives considered**:
- `@app.on_event`: Deprecated; avoid introducing deprecated patterns in new code.
- Starting the worker outside lifespan (module level): Cannot be stopped cleanly; breaks test isolation.

---

## Decision 7: New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | `>=0.110` | REST framework + Pydantic v2 built-in |
| `uvicorn[standard]` | `>=0.29` | ASGI server for running the app |
| `httpx` | `>=0.27` | Required by `starlette.testclient.TestClient` for async transport |

No other new runtime dependencies. `pytest` and `pytest-cov` already present from Sprint 1.
