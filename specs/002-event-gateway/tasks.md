# Tasks: Sprint 2 - Cloud-Native Event Gateway & Async Queue

**Input**: Design documents from `specs/002-event-gateway/`  
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/rest-api.md ✅

**Tests**: Test-First is NON-NEGOTIABLE (FR-010, Constitution Principle III). All test tasks must be committed and confirmed failing before their corresponding implementation tasks.

---

## Phase 1: Setup

**Purpose**: Add Sprint 2 dependencies and create the `autosentinel/api/` package skeleton.

- [X] T001 Update pyproject.toml to add `fastapi>=0.110`, `uvicorn[standard]>=0.29`, `httpx>=0.27` under `[project.dependencies]`; run `pip install -e ".[dev]"` to verify install
- [X] T002 Add `data/incoming/` to .gitignore (runtime alert files must not enter VCS)
- [X] T003 [P] Create empty `autosentinel/api/__init__.py` as package marker

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Logging infrastructure and Pydantic request/response models — required by all three user stories before any route or worker can be implemented.

**⚠️ CRITICAL**: Write tests first and confirm they FAIL before writing any implementation.

### Tests (write first — confirm failing)

- [X] T004 Write failing unit tests for `JSONFormatter` in `tests/unit/test_api_logging.py` — assert output is valid JSON, contains all schema fields (`timestamp`, `severity`, `component`, `correlation_id`, `trace_id`, `event`, `event_payload`), and is written to stdout
- [X] T005 [P] Write failing unit tests for Pydantic models in `tests/unit/test_api_models.py` — `AlertPayload` required field validation (422 on missing), `stack_trace` defaults to `None`, extra fields ignored; `AlertJobResponse` all three fields present

### Implementation (after tests confirmed failing)

- [X] T006 Implement `JSONFormatter` subclass and `get_logger(component)` in `autosentinel/api/logging.py` — outputs single-line JSON per log record with all schema fields from Principle IV
- [X] T007 [P] Implement `AlertPayload(BaseModel)` and `AlertJobResponse(BaseModel)` in `autosentinel/api/models.py` per data-model.md schema

**Checkpoint**: `T004`–`T007` complete → foundation ready, all US phases can begin.

---

## Phase 3: User Story 1 - Accept Alert Without Blocking (Priority: P1) 🎯 MVP

**Goal**: `POST /api/v1/alerts` validates the payload, returns `202 Accepted` with a `job_id`, and enqueues the alert — all within 50ms.

**Independent Test**: POST a valid crash-log JSON and assert `202` with a `job_id` in the response body, with no report file needed.

### Tests for US1 (write first — confirm failing)

- [ ] T008 [US1] Extend `tests/conftest.py` with `client` fixture (`TestClient(create_app())` used as context manager) and `mock_pipeline` fixture (patches `autosentinel.api.queue.run_pipeline` with a side-effect that writes a sentinel file and returns its path)
- [ ] T009 [US1] Write 5 failing route tests in `tests/integration/test_api.py`:
  `test_post_alert_returns_202`, `test_post_alert_missing_field_returns_422`,
  `test_post_alert_invalid_json_returns_422`, `test_post_alert_extra_fields_accepted`,
  `test_post_alert_job_ids_are_unique`

### Implementation for US1 (after tests confirmed failing)

- [ ] T010 [US1] Implement `AlertJob` dataclass and `asyncio.Queue` singleton with `get_queue()` in `autosentinel/api/queue.py`
- [ ] T011 [US1] Implement `create_app()` factory with stub `lifespan` context and `POST /api/v1/alerts` handler in `autosentinel/api/main.py`; add module-level `app = create_app()` for uvicorn entry point

**Checkpoint**: US1 complete — server accepts alerts and returns 202 immediately. Independently testable.

---

## Phase 4: User Story 2 - Automatic Background Diagnosis (Priority: P2)

**Goal**: After accepting an alert, the background worker consumes it from the queue, writes the payload to `data/incoming/{job_id}.json`, and runs `run_pipeline()` asynchronously via `asyncio.to_thread`.

**Independent Test**: POST an alert, call `queue.join()` to drain, then assert the diagnostic report file exists on disk.

### Tests for US2 (write first — confirm failing)

- [ ] T012 [US2] Write 3 failing background processing tests in `tests/integration/test_api.py`:
  `test_background_worker_processes_queued_alert` (POST + drain + check output),
  `test_background_worker_handles_pipeline_error` (mock raises exception → no crash),
  `test_multiple_alerts_all_processed` (10 POSTs + drain → 10 reports)

### Implementation for US2 (after tests confirmed failing)

- [ ] T013 [US2] Implement `worker(queue)` coroutine in `autosentinel/api/queue.py` — per item: create `data/incoming/{job_id}.json`, call `await asyncio.to_thread(run_pipeline, path)`, call `queue.task_done()`; handle `CancelledError` to exit cleanly
- [ ] T014 [US2] Replace stub `lifespan` in `autosentinel/api/main.py` with real worker task — `asyncio.create_task(worker(queue))` on enter, `task.cancel()` + `await task` on exit; ensure `data/incoming/` dir exists on startup

**Checkpoint**: US2 complete — all accepted alerts are eventually diagnosed. Reports appear on disk. Independently testable.

---

## Phase 5: User Story 3 - Structured Observability Trace (Priority: P3)

**Goal**: Every lifecycle transition emits a structured JSON log event with `job_id` as `correlation_id` and `trace_id` — covering `alert_received`, `alert_queued`, `processing_started`, `processing_completed`, and `processing_failed`.

**Independent Test**: Capture stdout, POST an alert, drain queue, parse log lines as JSON, assert at least 3 events with matching `job_id` and required schema fields.

### Tests for US3 (write first — confirm failing)

- [ ] T015 [US3] Write 3 failing log-capture tests in `tests/integration/test_api.py`:
  `test_post_alert_emits_alert_received_log` (assert log line has correct schema + job_id),
  `test_post_alert_emits_alert_queued_log_with_depth`,
  `test_worker_emits_processing_completed_log_with_duration_ms`

### Implementation for US3 (after tests confirmed failing)

- [ ] T016 [US3] Wire `get_logger("event_gateway")` calls into `POST /api/v1/alerts` handler in `autosentinel/api/main.py` — emit `alert_received` (service_name, error_type) and `alert_queued` (service_name, queue_depth)
- [ ] T017 [US3] Wire log emissions into `worker()` in `autosentinel/api/queue.py` — emit `processing_started` (service_name, log_path), `processing_completed` (service_name, report_path, duration_ms), and `processing_failed` (service_name, error, duration_ms) on exception

**Checkpoint**: All 3 user stories complete. Full lifecycle observable via structured logs.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T018 Run `pytest --cov=autosentinel --cov-branch --cov-fail-under=100` and resolve any coverage gaps in `autosentinel/api/`
- [ ] T019 [P] Add SC-001 timing assertion to `tests/integration/test_api.py` — verify `POST /api/v1/alerts` round-trip (measured with `time.perf_counter`) completes in under 50ms
- [ ] T020 [P] Run Sprint 1 tests in isolation (`pytest tests/unit tests/integration/test_pipeline.py`) to confirm zero regressions

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **BLOCKS** all user story phases
- **US1 (Phase 3)**: Depends on Phase 2 completion
- **US2 (Phase 4)**: Depends on Phase 3 (US1 must be complete — worker needs the queue from T010)
- **US3 (Phase 5)**: Depends on Phase 4 (logging hooks into US2 worker)
- **Polish (Phase 6)**: Depends on all user story phases

### Within Each Phase

- Test tasks MUST be committed and confirmed failing before implementation tasks in the same phase
- [P] tasks touch different files and have no mutual dependency — run together

### Parallel Opportunities

```bash
# Phase 2 — parallel after T003:
T004  # test_api_logging.py
T005  # test_api_models.py
# (confirm both fail, then):
T006  # logging.py
T007  # api/models.py

# Phase 3 — parallel:
T008  # conftest.py
T009  # test_api.py (route tests)
# (confirm T009 fails, then):
T010  # queue.py (AlertJob + Queue)
T011  # main.py (app factory + route handler)

# Phase 6 — all parallel:
T018  # coverage run
T019  # SC-001 timing test
T020  # Sprint 1 regression check
```

---

## Implementation Strategy

### MVP (US1 only)

1. Phase 1: Setup
2. Phase 2: Foundational
3. Phase 3: US1 — service accepts alerts and returns 202
4. **STOP**: Validate US1 independently with `curl` and `TestClient`

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 → non-blocking alert acceptance (MVP demo-able)
3. US2 → reports appear on disk after POST
4. US3 → full lifecycle observable in logs
5. Polish → 100% coverage + timing assertion + no regressions

---

## Notes

- [P] = different files, no mutual dependency — safe to parallelize
- [USX] = maps task to user story for traceability
- Sprint 1 files (`autosentinel/__init__.py`, `graph.py`, `nodes/`, `models.py`) MUST NOT be modified
- `data/incoming/` directory is created at server startup (not committed to VCS)
- `queue.join()` in tests provides a deterministic drain point — no `asyncio.sleep` polling
