# Tasks: Sprint 3 - Secure Docker Sandbox Execution

**Input**: Design documents from `/specs/003-docker-sandbox/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/ ✅ | quickstart.md ✅

**Tests**: REQUIRED — FR-009 (Constitution Principle III NON-NEGOTIABLE): all `execute_fix` and
updated `format_report` tests MUST be committed failing before any implementation is written.

---

## Phase 1: Setup — State Extension & Fixtures

**Purpose**: Add `ExecutionResult` TypedDict and the three new `DiagnosticState` fields.
All downstream phases depend on this.

- [X] T001 Add `ExecutionResult` TypedDict and extend `DiagnosticState` with `fix_script`, `execution_result`, `execution_error` in `autosentinel/models.py`
- [X] T002 Update `tests/conftest.py` fixture(s) to include `fix_script=None`, `execution_result=None`, `execution_error=None` in all `DiagnosticState` dict constructors

**Checkpoint**: `python -m pytest tests/ -x` still passes with 100% coverage before any new tests.

---

## Phase 2: Test-First Gate (NON-NEGOTIABLE — FR-009 / SC-005)

**Purpose**: Write all tests for Sprint 3 and commit them **failing** before writing any implementation.

**⚠️ CRITICAL**: No Phase 3+ tasks may begin until these tests exist and fail. Commit message MUST state tests are failing.

- [X] T003 Write `tests/unit/test_execute_fix.py` — 5 scenarios using `patch("autosentinel.nodes.execute_fix.docker")`: success (exit 0), failure (exit 1), timeout (`ReadTimeout`), Docker unavailable (`DockerException`), skipped (`fix_script=None`)
- [X] T004 [P] Add 3 sandbox-section tests to `tests/unit/test_format_report.py`: successful execution result, `execution_error` path, skipped status
- [X] T005 [P] Update `tests/integration/test_pipeline.py` — add end-to-end test with Docker mocked that asserts `## Sandbox Execution` section appears in the written report file

**Checkpoint**: `python -m pytest tests/unit/test_execute_fix.py tests/unit/test_format_report.py tests/integration/test_pipeline.py` — **all new tests must FAIL**. Commit with message "test: add Sprint 3 tests (failing — Test-First gate)".

---

## Phase 3: User Story 1 — Safe Remediation Script Execution (Priority: P1) 🎯 MVP

**Goal**: `execute_fix` node runs `fix_script` in an isolated Docker container, captures output, and always cleans up the container.

**Independent Test**: `tests/unit/test_execute_fix.py` passes all 5 scenarios with Docker mocked.

- [X] T006 Add `_MOCK_FIX_SCRIPTS` dict (one `print(...)` one-liner per error category) to `autosentinel/nodes/analyze_error.py` and include `"fix_script": _MOCK_FIX_SCRIPTS[result["error_category"]]` in the return dict
- [X] T007 Create `autosentinel/nodes/execute_fix.py` — LangGraph node using `docker.from_env()`, `client.containers.run("python:3.10-alpine", ["python", "-c", fix_script], detach=True, mem_limit="64m", network_mode="none")`, `container.wait(timeout=5)`, logs capture, timeout/error handling, `finally: container.remove(force=True)`
- [X] T008 Update `autosentinel/graph.py` — change `_route_after_analyze` to return `"execute_fix"` instead of `"format_report"`; add `execute_fix` node; add unconditional `builder.add_edge("execute_fix", "format_report")`

**Checkpoint**: `python -m pytest tests/unit/test_execute_fix.py -v` — all 5 scenarios pass.

---

## Phase 4: User Story 2 — Execution Results in Diagnostic Report (Priority: P2)

**Goal**: The markdown report always contains a "Sandbox Execution" section with status, return code, stdout, stderr, or error reason.

**Independent Test**: `tests/unit/test_format_report.py` new sandbox tests pass; report file contains `## Sandbox Execution` section.

- [X] T009 [US2] Update `autosentinel/nodes/format_report.py` — read `execution_result` and `execution_error` from state; append the Sandbox Execution section after "Remediation Steps" (three templates: normal result, error path, skipped status per data-model.md)

**Checkpoint**: `python -m pytest tests/unit/test_format_report.py tests/integration/test_pipeline.py -v` — all tests pass; report file contains the sandbox section.

---

## Phase 5: User Story 3 — Graceful Docker Unavailability (Priority: P3)

**Goal**: Docker daemon unavailability captures the error in state and the pipeline continues to produce a report.

**Independent Test**: `test_execute_fix.py` Docker-unavailable scenario passes; pipeline integration test produces a valid report with `execution_error` noted.

- [X] T010 [US3] Verify `execute_fix.py` catches `docker.errors.DockerException` (and any `Exception` fallback) at the `docker.from_env()` call, sets `execution_error` string, sets `execution_result=None`, and returns without raising — confirmed by the Docker-unavailable test scenario passing

**Checkpoint**: `python -m pytest tests/ -v` — all Sprint 3 tests pass including Docker-unavailable scenario.

---

## Phase 6: Polish & Coverage

**Purpose**: Full test suite validation and 100% coverage confirmation.

- [X] T011 Run `python -m pytest --cov=autosentinel --cov-report=term-missing` and confirm 100% coverage across all modules; fix any uncovered branches

**Checkpoint**: Coverage report shows 100%. `python -m pytest tests/ -v` exits 0.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Test-First Gate)**: Depends on Phase 1 (models must exist to import in tests)
- **Phase 3 (US1)**: MUST NOT start until Phase 2 tests are committed failing
- **Phase 4 (US2)**: Depends on Phase 3 (format_report reads `execution_result` set by `execute_fix`)
- **Phase 5 (US3)**: Covered by Phase 2 tests + Phase 3 implementation — verification only
- **Phase 6 (Polish)**: Depends on Phases 3–5 completion

### Within Phase 2

- T003 must complete before T004 and T005 (T004/T005 can then run in parallel [P])

### Within Phase 3

- T006 and T007 can run in parallel [P] (different files)
- T008 depends on T007 (graph wiring imports `execute_fix` node)

---

## Parallel Opportunities

```bash
# Phase 2 — after T003 (test_execute_fix written):
Task T004: "Add sandbox tests to tests/unit/test_format_report.py"
Task T005: "Update tests/integration/test_pipeline.py"

# Phase 3 — simultaneously:
Task T006: "Add _MOCK_FIX_SCRIPTS to analyze_error.py"
Task T007: "Create autosentinel/nodes/execute_fix.py"
# Then sequentially:
Task T008: "Update graph.py wiring"
```

---

## Implementation Strategy

### MVP: User Story 1 Only

1. Phase 1: Setup (T001–T002)
2. Phase 2: Test-First Gate (T003–T005) — commit failing
3. Phase 3: US1 core execution (T006–T008) — tests go green
4. **STOP and VALIDATE**: All 5 `test_execute_fix.py` scenarios pass with Docker mocked

### Full Sprint 3 Delivery

1. Complete Phases 1–3 (MVP above)
2. Phase 4: US2 report integration (T009) — `test_format_report.py` sandbox tests go green
3. Phase 5: US3 verification (T010) — Docker-unavailable scenario confirmed
4. Phase 6: Polish (T011) — 100% coverage confirmed
