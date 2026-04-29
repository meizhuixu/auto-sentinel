# Tasks: Sprint 4 - Multi-Agent Migration

**Input**: Design documents from `/specs/004-multi-agent-migration/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: TDD is MANDATORY (SC-006, Constitution Principle III — NON-NEGOTIABLE). All test files MUST be committed failing before any implementation file is created.

**Organization**: Tasks follow the 9-phase implementation plan. Phase 2 (Test-First Gate) MUST be committed as a single failing-tests commit before Phase 3 begins.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to
- Tests-first tasks marked with `⚠ WRITE FAILING` — commit before implementation

---

## Phase 1: Setup & State Extension

**Purpose**: Extend models with AgentState, create agents/ package skeleton, update conftest fixtures.
All of Phase 1 MUST complete before Phase 2 begins.

- [X] T001 Add `AgentState` TypedDict to `autosentinel/models.py` — extend DiagnosticState with 6 new fields: `error_category`, `fix_artifact`, `security_verdict`, `routing_decision`, `agent_trace: Annotated[list[str], operator.add]`, `approval_required`
- [X] T002 Create `autosentinel/agents/` package: `__init__.py` (empty), `base.py` (BaseAgent ABC with `run(state: AgentState) -> AgentState`), `state.py` (re-exports AgentState from models)
- [X] T003 Update `tests/conftest.py` — add AgentState initial-value helpers: `build_initial_state()`, `invoke_with_docker_mock()`, `_setup_docker_success()` per quickstart.md fixtures section

**Checkpoint**: `python -c "from autosentinel.models import AgentState; from autosentinel.agents.base import BaseAgent"` succeeds with no errors.

---

## Phase 2: Test-First Gate (NON-NEGOTIABLE — SC-006)

**Purpose**: Write ALL failing tests. Every file below MUST raise `ImportError` or `AssertionError` when run.
**⚠️ CRITICAL**: After completing all T004–T013, run `pytest --no-header -q 2>&1 | grep -E "ERROR|FAILED"` to confirm failures, then make a single git commit whose message contains exactly `"failing — Test-First gate"`. NO implementation may start before this commit exists.

- [X] T004 [P] ⚠ WRITE FAILING — `tests/unit/test_diagnosis_agent.py`: tests for DiagnosisAgent keyword routing (CODE/INFRA/CONFIG/SECURITY classification, fallback, agent_trace append)
- [X] T005 [P] ⚠ WRITE FAILING — `tests/unit/test_supervisor_agent.py`: tests for SupervisorAgent routing table (CODE→CodeFixer, INFRA→InfraSRE, CONFIG→InfraSRE, SECURITY→CodeFixer, UNKNOWN→CodeFixer fallback, routing_decision format, agent_trace append)
- [X] T006 [P] ⚠ WRITE FAILING — `tests/unit/test_code_fixer_agent.py`: tests for CodeFixerAgent mock fix generation (fix_artifact set, TODO comment present, agent_trace append)
- [X] T007 [P] ⚠ WRITE FAILING — `tests/unit/test_infra_sre_agent.py`: tests for InfraSREAgent mock fix generation (fix_artifact set for INFRA/CONFIG, agent_trace append)
- [X] T008 [P] ⚠ WRITE FAILING — `tests/unit/test_security_reviewer_agent.py`: tests for SecurityReviewerAgent keyword detection on `fix_artifact` field (SAFE for clean fix_artifact, HIGH_RISK for each keyword in _HIGH_RISK_KEYWORDS, empty/None fix_artifact → SAFE, agent_trace append)
- [X] T009 [P] ⚠ WRITE FAILING — `tests/unit/test_verifier_agent.py`: tests for VerifierAgent (produces ExecutionResult, reads fix_artifact, appends to agent_trace; mock Docker success/failure/timeout/unavailable)
- [X] T010 [P] ⚠ WRITE FAILING — `tests/unit/test_docker_import_boundary.py`: SC-004 AST check — walks all `.py` under `autosentinel/`, asserts only `autosentinel/agents/verifier.py` imports `docker`
- [X] T011a [P] ⚠ WRITE FAILING — `tests/integration/test_multi_agent_graph_routing.py`: routing tests — 4 category routing (CODE/INFRA/CONFIG/SECURITY), UNKNOWN fallback, routing_decision format, agent_trace order (specialist before SecurityReviewerAgent) (quickstart.md scenarios 1–3, 8)
- [X] T011b [P] ⚠ WRITE FAILING — `tests/integration/test_multi_agent_graph_security.py`: security gate tests — HIGH_RISK interrupt/resume (specialist produces fix_artifact with HIGH_RISK keyword → SecurityReviewer sees it → interrupt fires), CAUTION pass-through, Docker-unavailable resilience; MUST include end-to-end case where fix_artifact contains HIGH_RISK keyword and SC-003 is verifiable (quickstart.md scenarios 4–7)
- [X] T012 [P] ⚠ WRITE FAILING — `tests/test_benchmark.py`: assert `output/benchmark-report.json` exists after `run_benchmark()`, contains `scenario_count=5`, `v1_resolution_rate`, `v2_resolution_rate`, `v1_avg_ms`, `v2_avg_ms`
- [X] T013 [P] ⚠ WRITE FAILING — update `tests/unit/test_format_report.py`: add 3 tests for Security Review section (SAFE no badge, CAUTION badge "⚠ CAUTION", HIGH_RISK approved badge "🚨 HIGH RISK")

**GATE**: Run `pytest tests/unit/test_diagnosis_agent.py tests/unit/test_supervisor_agent.py tests/unit/test_code_fixer_agent.py tests/unit/test_infra_sre_agent.py tests/unit/test_security_reviewer_agent.py tests/unit/test_verifier_agent.py tests/unit/test_docker_import_boundary.py tests/integration/test_multi_agent_graph_routing.py tests/integration/test_multi_agent_graph_security.py tests/test_benchmark.py -q 2>&1 | tail -5` — confirm all ERROR/FAILED, then:

```
git add tests/
git commit -m "tests: add Sprint 4 agent + graph tests — failing — Test-First gate"
```

Commit message MUST contain `"failing — Test-First gate"` (SC-006). No implementation begins before this commit.

---

## Phase 3: User Story 1 — Specialist Agent Routing (Priority: P1) 🎯

**Goal**: DiagnosisAgent classifies errors; SupervisorAgent routes to the correct specialist; routing_decision recorded in state; graph wires parse_log → diagnosis → supervisor → specialist.

**Independent Test**: `pytest tests/unit/test_diagnosis_agent.py tests/unit/test_supervisor_agent.py -v` all green; `pytest tests/integration/test_multi_agent_graph.py -k "routing" -v` all green.

- [X] T014 [US1] Implement `autosentinel/agents/diagnosis.py` — DiagnosisAgent with keyword mock `_mock_classify()` mapping (connectivity/resource_exhaustion → INFRA, configuration → CONFIG, application_logic → CODE), `# TODO(W2): replace with real LLM call`, returns `{error_category, agent_trace: ["DiagnosisAgent"]}`
- [X] T015 [US1] Implement `autosentinel/agents/supervisor.py` — SupervisorAgent routing table (CODE/SECURITY/UNKNOWN → "code_fixer"; INFRA/CONFIG → "infra_sre"), returns `{routing_decision: "CATEGORY → AgentName", agent_trace: ["SupervisorAgent"]}`
- [X] T016 [US1] Create `autosentinel/multi_agent_graph.py` — `build_multi_agent_graph()` sequential stub: parse_log → diagnosis_agent → supervisor_route → (code_fixer_agent OR infra_sre_agent) → security_reviewer → supervisor_merge → security_gate → verifier_agent → format_report → END; compile with `checkpointer=MemorySaver()`

**Checkpoint**: `pytest tests/unit/test_diagnosis_agent.py tests/unit/test_supervisor_agent.py -v` → all PASSED.

---

## Phase 4: User Story 2 — Security Review Gate (Priority: P1)

**Goal**: SecurityReviewerAgent classifies `fix_artifact` with keyword mock; security_gate suspends pipeline on HIGH_RISK via interrupt(); human_approval_required log event emitted; CAUTION passes through.

**Independent Test**: `pytest tests/unit/test_security_reviewer_agent.py -v` all green; `pytest tests/integration/test_multi_agent_graph_security.py -k "high_risk or interrupt or caution" -v` all green.

- [X] T017 [US2] Implement `autosentinel/agents/security_reviewer.py` — SecurityReviewerAgent with `_HIGH_RISK_KEYWORDS` list, keyword-scans `state.get("fix_artifact") or ""`, returns `{security_verdict: "SAFE"|"HIGH_RISK", agent_trace: ["SecurityReviewerAgent"]}`, `# TODO(W2): replace with real LLM call`
- [X] T018 [US2] Implement `security_gate` node in `autosentinel/multi_agent_graph.py` — reads `security_verdict`; for HIGH_RISK: logs `human_approval_required` with `_logger.exception` fallback (soft guarantee — log failure must NOT block interrupt), calls `interrupt({reason, fix_artifact})`; always returns `{approval_required: verdict=="HIGH_RISK"}`

**Checkpoint**: `pytest tests/unit/test_security_reviewer_agent.py tests/integration/test_multi_agent_graph_security.py -v` → all PASSED.

---

## Phase 5: User Story 4 — Verifier Agent as Sole Docker Executor (Priority: P1)

**Goal**: VerifierAgent wraps Sprint 3 execute_fix logic, reads fix_artifact; CodeFixerAgent and InfraSREAgent provide mock fix generation; Docker import boundary check passes.

**Independent Test**: `pytest tests/unit/test_verifier_agent.py tests/unit/test_docker_import_boundary.py tests/unit/test_code_fixer_agent.py tests/unit/test_infra_sre_agent.py -v` all green.

- [X] T019 [P] [US4] Implement `autosentinel/agents/code_fixer.py` — CodeFixerAgent with `_MOCK_FIXES` dict (CODE/SECURITY categories), `# TODO(W2)`, returns `{fix_artifact, agent_trace: ["CodeFixerAgent"]}`
- [X] T020 [P] [US4] Implement `autosentinel/agents/infra_sre.py` — InfraSREAgent with `_MOCK_FIXES` dict (INFRA/CONFIG categories), `# TODO(W2)`, returns `{fix_artifact, agent_trace: ["InfraSREAgent"]}`
- [X] T021 [US4] Implement `autosentinel/agents/verifier.py` — VerifierAgent: ONLY agent that imports `docker`; reads `fix_artifact`, proxies to extracted `_execute_fix_logic()` from `nodes/execute_fix.py`, returns `{execution_result, execution_error, agent_trace: ["VerifierAgent"]}`

**Checkpoint**: `pytest tests/unit/test_verifier_agent.py tests/unit/test_docker_import_boundary.py tests/unit/test_code_fixer_agent.py tests/unit/test_infra_sre_agent.py -v` → all PASSED (Docker mocked).

---

## Phase 6: User Story 3 — Sequential Security Gate Enforcement (Priority: P2)

**Goal**: Wire specialist → security_reviewer sequential edges; remove supervisor_merge no-op node; verify SecurityReviewerAgent reads fix_artifact and agent_trace order is specialist-before-reviewer.

**Independent Test**: `pytest tests/integration/test_multi_agent_graph_routing.py -v` all green; agent_trace order shows specialist before SecurityReviewerAgent.

- [X] T022 [US3] Wire sequential edges in `autosentinel/multi_agent_graph.py` — add `add_edge("code_fixer_agent", "security_reviewer")` and `add_edge("infra_sre_agent", "security_reviewer")`; add `add_edge("security_reviewer", "security_gate")`; remove `supervisor_merge` node and its edges; verify T016 graph stub is updated to this topology

**Checkpoint**: `pytest tests/integration/test_multi_agent_graph_routing.py tests/integration/test_multi_agent_graph_security.py -v` → all PASSED; agent_trace in CODE scenario is `["DiagnosisAgent", "SupervisorAgent", "CodeFixerAgent", "SecurityReviewerAgent", "VerifierAgent"]`.

---

## Phase 7: Report Integration — Security Review Section (US2/US3)

**Goal**: format_report reads security_verdict, routing_decision, agent_trace and appends a "## Security Review" section with SAFE/CAUTION/HIGH_RISK badges.

**Independent Test**: `pytest tests/unit/test_format_report.py -v` all green (including 3 new security-verdict tests from T013).

- [X] T023 Update `autosentinel/nodes/format_report.py` — append `## Security Review` section after "## Sandbox Execution": reads `state.get("security_verdict")`, `state.get("routing_decision")`, `state.get("agent_trace", [])`; renders CAUTION badge (`⚠ CAUTION`) when verdict=="CAUTION"; renders HIGH_RISK badge (`🚨 HIGH RISK — executed after human approval`) when `approval_required==True`

**Checkpoint**: `pytest tests/unit/test_format_report.py -v` → all PASSED including security section tests.

---

## Phase 8: User Story 5 — v1 vs v2 Smoke Benchmark (Priority: P3)

**Goal**: `autosentinel/benchmark.py` runs 5 predefined smoke scenarios through both pipelines (Docker mocked), writes `output/benchmark-report.json` with v1/v2 resolution rates and timing.

**Independent Test**: `pytest tests/test_benchmark.py -v` all green; output file parseable by json.loads().

- [X] T024 [US5] Implement `autosentinel/benchmark.py` — define `SCENARIOS: list[dict]` with 5 entries (s01=CODE, s02=INFRA, s03=CONFIG, s04=SECURITY, s05=UNKNOWN/fallback); **s04 SECURITY mock specialist output MUST include a `_HIGH_RISK_KEYWORDS` entry** (e.g., `"DROP TABLE users"`) so the HIGH_RISK path is exercised in at least one benchmark scenario; implement `run_benchmark() -> dict`; `if __name__ == "__main__"` CLI entry; writes `output/benchmark-report.json` with fields: `scenario_count`, `v1_resolution_rate`, `v2_resolution_rate`, `v1_avg_ms`, `v2_avg_ms`

**Checkpoint**: `pytest tests/test_benchmark.py -v` → all PASSED; `python -m autosentinel.benchmark` exits 0.

---

## Phase 9: Polish & Coverage

**Purpose**: Wire feature flag, update run_pipeline(), verify full suite at 100% coverage.

- [X] T025 Update `autosentinel/__init__.py` — add `AUTOSENTINEL_MULTI_AGENT` feature flag to `run_pipeline()`: `use_multi_agent = os.getenv("AUTOSENTINEL_MULTI_AGENT", "0") == "1"`; call `build_multi_agent_graph()` when set, else `build_graph()`; initial_state MUST include all AgentState fields (fix Sprint 3 gap: `fix_script=None, execution_result=None, execution_error=None`)
- [X] T026 Update `tests/integration/test_pipeline.py` — update `test_pipeline_node_execution_order` to assert v1 order `["parse_log", "analyze_error", "execute_fix", "format_report"]` still passes; add test for v2 pipeline invocation via feature flag
- [X] T027 Run full test suite and confirm 100% branch coverage: `pytest --cov=autosentinel --cov-branch --cov-report=term-missing -q`; fix any gaps

**Final Checkpoint**: `pytest --cov=autosentinel --cov-branch -q` → all PASSED, 100% coverage, no regressions on Sprint 1–3 tests.

---

---

## Phase 10: Canonical Benchmark Generation

**Purpose**: Generate and commit a real benchmark report as the authoritative metric source. Proves SC-003 fires under actual LangGraph execution, not only in unit-test mocks.

- [ ] T028 [POLISH] Generate and commit canonical benchmark report
  - `mkdir -p output`
  - `python -m autosentinel.benchmark`
  - Verify `output/benchmark-report.json` exists
  - Verify `scenario_count == 5`
  - Verify s04 (SECURITY) scenario agent_trace contains `SecurityReviewerAgent` and `security_verdict == "HIGH_RISK"` (proves SC-003 path triggered under real LangGraph execution, not only in unit-test mocks)
  - Confirm `.gitignore` does not exclude `output/benchmark-report.json` (negation rule required if `output/` is blanket-excluded)
  - `git add output/benchmark-report.json`
  - `git commit -m "chore: generate canonical Sprint 4 benchmark report"`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Test-First Gate)**: Depends on Phase 1 — write all tests, commit "failing — Test-First gate" before Phase 3
- **Phase 3 (US1 Routing)**: Depends on Phase 2 commit — P1
- **Phase 4 (US2 Security Gate)**: T017 (security_reviewer.py) depends only on Phase 2 commit; T018 (security_gate in graph) depends on T016 (graph stub) — P1
- **Phase 5 (US4 Verifier)**: T019/T020/T021 are standalone new files — depend only on Phase 2 commit; can run in parallel with Phase 4 T017 (different files) — P1
- **Phase 6 (US3 Sequential Wiring)**: Depends on T016 + T018 + T017 + T021 complete — P2
- **Phase 7 (Report)**: Depends on Phase 4 (needs security_verdict in state); can run after T018 — P1-adjacent
- **Phase 8 (US5 Benchmark)**: Depends on all P1 phases complete — P3
- **Phase 9 (Polish)**: Depends on all prior phases

### Critical Path

```
T001 → T002 → T003
                  ↓
T004─┐
T005─┤
T006─┤
T007─┤ (all parallel, Phase 2)
T008─┤
T009─┤
T010─┤
T011a┤
T011b┤
T012─┤
T013─┘
      ↓
COMMIT "failing — Test-First gate"
      │
      ├── Stream A: T014 → T015 → T016      (US1 agents → graph stub)
      │                             │
      ├── Stream B: T017 ────────────────→ T018  (US2: reviewer file → security_gate in graph)
      │                                     │
      ├── Stream C: T019 ─┐                 │
      │             T020 ─┘→ T021 ──────────┘
      │             (US4: specialist files → verifier)
      │
      └── All streams converge → T022 (sequential wiring, needs T016+T017+T018+T021)
                                   ↓
                                 T023 (Report)
                                   ↓
                                 T024 (Benchmark)
                                   ↓
                          T025 → T026 → T027 (Polish)
```

### Within Each Phase

- Phase 2 tasks (T004–T013) MUST all fail before implementation starts
- Phase 5 tasks T019 and T020 (CodeFixerAgent, InfraSREAgent) can run in parallel (different files)
- Phase 9 tasks must run sequentially (T025 updates __init__.py, T026 references it, T027 validates all)

---

## Parallel Opportunities

### Phase 2: All test files can be written in parallel
```
T004 test_diagnosis_agent.py        ─┐
T005 test_supervisor_agent.py       ─┤
T006 test_code_fixer_agent.py       ─┤ all in parallel
T007 test_infra_sre_agent.py        ─┤ (different files)
T008 test_security_reviewer.py      ─┤
T009 test_verifier_agent.py         ─┤
T010 test_docker_boundary.py        ─┤
T011a test_multi_agent_graph_routing ─┤
T011b test_multi_agent_graph_security─┤
T012 test_benchmark.py              ─┤
T013 test_format_report.py          ─┘
```

### Phase 5: Agent stubs can be written in parallel
```
T019 code_fixer.py   ─┐
T020 infra_sre.py    ─┘ parallel (different files)
T021 verifier.py       (after T019/T020 to avoid merge confusion in graph)
```

---

## Implementation Strategy

### MVP: P1 Stories Only (US1 + US2 + US4)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Test-First Gate (T004–T013 + commit)
3. Complete Phase 3: US1 Routing (T014–T016)
4. Complete Phase 4: US2 Security Gate (T017–T018)
5. Complete Phase 5: US4 Verifier Isolation (T019–T021)
6. **STOP and VALIDATE**: `pytest tests/unit/ tests/integration/test_multi_agent_graph.py -v`

### Full Sprint 4 Delivery

1. MVP above → then Phase 6 (US3 Sequential Wiring, T022)
2. Phase 7 (Report integration, T023)
3. Phase 8 (US5 Benchmark, T024)
4. Phase 9 (Polish, T025–T027)

---

## Notes

- [P] tasks = different files, no blocking dependencies between them
- **Phase 2 is a hard gate** — no implementation PR is valid without the "failing — Test-First gate" commit preceding it on the branch (SC-006)
- All mock `run()` methods MUST include `# TODO(W2): replace with real LLM call` (FR-010)
- Docker is NEVER imported outside `autosentinel/agents/verifier.py` (FR-008 / SC-004)
- SecurityReviewerAgent reads `state["fix_artifact"]` (v2 field set by specialist); NOT `state["fix_script"]` — sequential wiring is what makes SC-003 testable (plan.md Decision 3)
- `agent_trace: Annotated[list[str], operator.add]` reducer is retained for Sprint 5 fan-out compatibility; Sprint 4 is sequential so reducer is never triggered (data-model.md agent_trace note)
- `build_multi_agent_graph()` MUST compile with `checkpointer=MemorySaver()` for interrupt() to work (research.md Decision 2)
- Task count: 28 tasks total (3 setup + 11 test-first + 14 implementation)
