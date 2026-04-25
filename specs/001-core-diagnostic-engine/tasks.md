---

description: "Task list for Core Diagnostic AI Engine"
---

# Tasks: Core Diagnostic AI Engine

**Input**: Design documents from `specs/001-core-diagnostic-engine/`
**Prerequisites**: plan.md ✅ | spec.md ✅ | research.md ✅ | data-model.md ✅ | contracts/python-interface.md ✅

**Tests**: Test tasks are **MANDATORY** — FR-008 and constitution Principle III (Test-First,
NON-NEGOTIABLE) require tests to be written and confirmed failing before any node
implementation begins. Verify by git commit order: test commit MUST precede implementation commit.

**Organization**: Tasks grouped by user story. Each story is independently implementable
and testable.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)
- Include exact file paths in all descriptions

## Path Conventions

- Package: `autosentinel/` at repository root
- Tests: `tests/` at repository root
- Data fixtures: `data/` at repository root
- Reports: `output/` at repository root (gitignored)

---

## Phase 1: Setup

**Purpose**: Project initialization and package skeleton

- [x] T001 Create `pyproject.toml` with metadata and dependencies (`langgraph`, `anthropic`, `pytest`, `pytest-cov`)
- [x] T002 Create `autosentinel/` package skeleton: `__init__.py`, `models.py`, `graph.py`, `nodes/__init__.py`, `nodes/parse_log.py`, `nodes/analyze_error.py`, `nodes/format_report.py` (empty files with module docstrings only)
- [x] T003 [P] Create `tests/` skeleton: `__init__.py`, `conftest.py`, `unit/__init__.py`, `unit/test_parse_log.py`, `unit/test_analyze_error.py`, `unit/test_format_report.py`, `integration/__init__.py`, `integration/test_pipeline.py` (empty files)
- [x] T004 [P] Create `data/` directory and add `.gitignore` entry for `output/`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared types, fixtures, and sample data that every user story depends on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Define `ErrorLog`, `AnalysisResult`, and `DiagnosticState` TypedDicts in `autosentinel/models.py` per `contracts/python-interface.md` type aliases section
- [x] T006 [P] Write `tests/conftest.py` with shared pytest fixtures: `connectivity_state`, `resource_state`, `config_state` (pre-populated `DiagnosticState` dicts), and `mock_tool_use_response()` factory that returns a mock `anthropic.types.Message` with a `tool_use` block
- [x] T007 [P] Create sample fixture `data/crash-connectivity.json` — `ConnectionTimeout` on `db.internal:5432` (see data-model.md sample)
- [x] T008 [P] Create sample fixture `data/crash-resource.json` — `OOMKilled`, memory limit exceeded message
- [x] T009 [P] Create sample fixture `data/crash-config.json` — missing required environment variable / bad secret message

**Checkpoint**: Models defined, fixtures in place — user story implementation can begin

---

## Phase 3: User Story 1 — Analyze a Crash Log (Priority: P1) 🎯 MVP

**Goal**: Given a valid JSON log, the full pipeline produces a correct markdown report in `output/`

**Independent Test**: `pytest tests/unit/ tests/integration/test_pipeline.py::test_happy_path` passes with mocked LLM; running `python -m autosentinel data/crash-connectivity.json` produces a non-empty `output/crash-connectivity-report.md`

### ⚠️ Tests for User Story 1 — WRITE FIRST, CONFIRM FAILING before T015

> **GATE: Commit T010–T013 and run `pytest` — ALL four tests MUST fail before proceeding to T014**

- [x] T010 [P] [US1] Write failing test `test_parse_log_happy_path` in `tests/unit/test_parse_log.py`: given `connectivity_state` fixture, assert `result["error_log"]["service_name"] == "payment-service"` and `result["parse_error"] is None`
- [x] T011 [P] [US1] Write failing test `test_analyze_error_happy_path` in `tests/unit/test_analyze_error.py`: patch `anthropic.Anthropic` with `mock_tool_use_response()` fixture returning `error_category="connectivity"`, assert `result["analysis_result"]["error_category"] == "connectivity"` and `result["analysis_error"] is None`
- [x] T012 [P] [US1] Write failing test `test_format_report_happy_path` in `tests/unit/test_format_report.py`: given state with populated `analysis_result`, assert `result["report_path"]` ends with `-report.md` and `result["report_text"]` contains `"## Root Cause Analysis"`
- [x] T013 [US1] Write failing integration test `test_full_pipeline_happy_path` in `tests/integration/test_pipeline.py`: invoke compiled graph with `connectivity_state`, assert all three node output fields populated and `graph.stream()` output visits nodes in order `["parse_log", "analyze_error", "format_report"]`

### Implementation for User Story 1

- [x] T014 [P] [US1] Implement `parse_log` happy path in `autosentinel/nodes/parse_log.py`: open `state["log_path"]`, parse JSON, extract required fields (`timestamp`, `service_name`, `error_type`, `message`) and optional `stack_trace`, return `{"error_log": ErrorLog, "parse_error": None}`
- [x] T015 [P] [US1] Implement `analyze_error` in `autosentinel/nodes/analyze_error.py`: define `DIAGNOSE_PROMPT` constant and `DIAGNOSE_TOOL` schema (per `contracts/python-interface.md`), call `anthropic.Anthropic().messages.create()` with `claude-haiku-4-5-20251001`, extract `tool_use` block, return `{"analysis_result": AnalysisResult, "analysis_error": None}`
- [x] T016 [P] [US1] Implement `format_report` in `autosentinel/nodes/format_report.py`: build markdown from `state["analysis_result"]` and `state["error_log"]` per DiagnosticReport structure in `data-model.md`, create `output/` with `Path.mkdir(exist_ok=True)`, write file, return `{"report_text": str, "report_path": str}`
- [x] T017 [US1] Implement `build_graph()` in `autosentinel/graph.py`: wire `StateGraph(DiagnosticState)` with `parse_log → analyze_error → format_report`, add conditional edges routing to `END` when `parse_error` or `analysis_error` is set (depends on T014, T015, T016)
- [x] T018 [US1] Implement `run_pipeline()` in `autosentinel/__init__.py` and CLI entry `autosentinel/__main__.py`: call `build_graph().invoke(initial_state)`, raise `DiagnosticError` if any error field set, return `Path(report_path)` on success; CLI: `argparse` for `log_path`, exit code 0/1/2 per `contracts/python-interface.md` (depends on T017)

**Checkpoint**: Run `python -m autosentinel data/crash-connectivity.json` — should produce `output/crash-connectivity-report.md` with classified root cause and remediation steps. User Story 1 fully functional and independently testable.

---

## Phase 4: User Story 2 — Handle Malformed Input Gracefully (Priority: P2)

**Goal**: Invalid or incomplete log input produces a clear, structured error — no silent failures, no tracebacks

**Independent Test**: `pytest tests/unit/test_parse_log.py -k "error"` passes without any P1 dependency; running `python -m autosentinel /nonexistent.json` exits with code 1 and a human-readable message on stderr

### ⚠️ Tests for User Story 2 — WRITE FIRST, CONFIRM FAILING before T023

> **GATE: Commit T019–T022 and run `pytest` on new tests only — ALL MUST fail before proceeding to T023**

- [x] T019 [P] [US2] Add failing test `test_parse_log_invalid_json` to `tests/unit/test_parse_log.py`: call `parse_log` with a state whose `log_path` points to a fixture containing `"not valid json {"`, assert `result["parse_error"]` is non-empty string containing the filename and `result["error_log"] is None`
- [x] T020 [P] [US2] Add failing test `test_parse_log_missing_required_fields` to `tests/unit/test_parse_log.py`: call `parse_log` with valid JSON missing `service_name`, assert `result["parse_error"]` mentions `"service_name"` and `result["error_log"] is None`
- [x] T021 [P] [US2] Add failing test `test_analyze_error_api_failure` to `tests/unit/test_analyze_error.py`: patch `anthropic.Anthropic` to raise `anthropic.APIConnectionError`, assert `result["analysis_error"]` is non-empty and `result["analysis_result"] is None`
- [x] T022 [US2] Add failing integration test `test_pipeline_routes_to_end_on_parse_error` to `tests/integration/test_pipeline.py`: invoke graph with a malformed-JSON log path, assert final state has `parse_error` set, `analysis_result is None`, `report_text is None`

### Implementation for User Story 2

- [x] T023 [US2] Add error-path handling to `autosentinel/nodes/parse_log.py`: catch `FileNotFoundError` (missing `data/` dir), `json.JSONDecodeError`, and missing/null required-field validation — populate `parse_error` with human-readable message for each case (depends on T019, T020)
- [x] T024 [US2] Add error-path handling to `autosentinel/nodes/analyze_error.py`: wrap Anthropic call in try/except for `anthropic.APIError` and missing `tool_use` block — populate `analysis_error` (depends on T021)
- [x] T025 [US2] Update `run_pipeline()` in `autosentinel/__init__.py` and `autosentinel/__main__.py` to raise/print `DiagnosticError` with `parse_error` or `analysis_error` message and exit with code 1 (depends on T023, T024)

**Checkpoint**: Both user stories fully functional and independently testable. Run `pytest` — all tests pass.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Coverage verification, commit order audit, and end-to-end validation

- [x] T026 [P] Add `pytest-cov` coverage configuration to `pyproject.toml` (`[tool.pytest.ini_options]` and `[tool.coverage.run]`); run `pytest --cov=autosentinel --cov-branch --cov-report=term-missing` and confirm 100% branch coverage on `autosentinel/nodes/`
- [x] T027 [P] Verify git commit order satisfies SC-003: run `git log --oneline` and confirm all `test_*.py` files appear in commits that precede the corresponding `nodes/*.py` implementation commits
- [x] T028 Run full quickstart.md validation: execute all steps sequentially (`pip install`, set env var, run all 3 fixtures, check 3 report files in `output/`) — confirm SC-001 (< 30s), SC-002 (correct category for all 3 fixtures), SC-005 (malformed input exits with code 1)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Phase 2 — no dependency on US2
- **User Story 2 (Phase 4)**: Depends on Phase 2 — no dependency on US1 (adds error paths to same files)
- **Polish (Phase 5)**: Depends on Phases 3 and 4 both complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational — no dependency on US2
- **US2 (P2)**: Can start after Foundational — adds error-path branches to the same node files as US1; can technically run in parallel with US1 by different developers, but conflict risk on `parse_log.py` and `__init__.py` makes sequential safer

### Within Each User Story

- Tests MUST be written and committed before implementation begins (Test-First gate)
- Models (`models.py`) before nodes
- Nodes (`parse_log`, `analyze_error`, `format_report`) before graph wiring (`graph.py`)
- Graph (`graph.py`) before pipeline runner (`__init__.py`)

### Parallel Opportunities

- T002, T003, T004: different targets, all parallel
- T006, T007, T008, T009: different files, all parallel
- T010, T011, T012, T013: different test files, all parallel
- T014, T015, T016: different node files, all parallel (after tests pass/fail check)
- T019, T020, T021: different test methods/files, all parallel
- T026, T027: independent validation steps, parallel

---

## Parallel Example: User Story 1

```bash
# Launch all US1 test writing tasks together (must fail before implementation):
Task: "Write failing test test_parse_log_happy_path in tests/unit/test_parse_log.py"      # T010
Task: "Write failing test test_analyze_error_happy_path in tests/unit/test_analyze_error.py"  # T011
Task: "Write failing test test_format_report_happy_path in tests/unit/test_format_report.py" # T012
Task: "Write failing integration test test_full_pipeline_happy_path"                        # T013

# Confirm ALL fail: pytest tests/unit/ tests/integration/test_pipeline.py::test_full_pipeline_happy_path

# Then launch all node implementations together:
Task: "Implement parse_log happy path in autosentinel/nodes/parse_log.py"       # T014
Task: "Implement analyze_error in autosentinel/nodes/analyze_error.py"           # T015
Task: "Implement format_report in autosentinel/nodes/format_report.py"           # T016
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Write and commit T010–T013 (tests); confirm failing
4. Complete Phase 3: User Story 1 (T014–T018)
5. **STOP and VALIDATE**: `pytest tests/unit/ tests/integration/` all pass; `python -m autosentinel data/crash-connectivity.json` produces report
6. Demo if ready

### Incremental Delivery

1. Setup + Foundational → skeleton ready
2. US1 tests → US1 implementation → end-to-end pipeline ✅ (MVP!)
3. US2 tests → US2 error handling → robust engine ✅
4. Polish phase → 100% coverage, commit order audit, quickstart validation ✅

### Single Developer Sequence

1. T001 → T002 → T003 → T004 (setup)
2. T005 → T006 → T007 → T008 → T009 (foundation)
3. T010 → T011 → T012 → T013 (US1 tests — commit here, confirm fail)
4. T014 → T015 → T016 → T017 → T018 (US1 impl — commit after each passing)
5. T019 → T020 → T021 → T022 (US2 tests — commit here, confirm fail)
6. T023 → T024 → T025 (US2 impl)
7. T026 → T027 → T028 (polish)

---

## Notes

- `[P]` tasks have no dependency on incomplete sibling tasks and operate on different files
- `[US1]`/`[US2]` labels trace tasks back to their user story for review and rollback
- Test-First gate (T010–T013 commit before T014–T018; T019–T022 commit before T023–T025) is a constitution compliance requirement, not just a recommendation
- `output/` directory MUST be in `.gitignore` — reports are build artefacts, not source
- `ANTHROPIC_API_KEY` env var must be set for integration tests that hit the real API; unit tests use mocked Anthropic client and require no key
