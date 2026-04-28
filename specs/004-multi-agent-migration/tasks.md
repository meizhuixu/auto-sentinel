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

- [ ] T001 Add `AgentState` TypedDict to `autosentinel/models.py` — extend DiagnosticState with 6 new fields: `error_category`, `fix_artifact`, `security_verdict`, `routing_decision`, `agent_trace: Annotated[list[str], operator.add]`, `approval_required`
- [ ] T002 Create `autosentinel/agents/` package: `__init__.py` (empty), `base.py` (BaseAgent ABC with `run(state: AgentState) -> AgentState`), `state.py` (re-exports AgentState from models)
- [ ] T003 Update `tests/conftest.py` — add AgentState initial-value helpers: `build_initial_state()`, `invoke_with_docker_mock()`, `_setup_docker_success()` per quickstart.md fixtures section

**Checkpoint**: `python -c "from autosentinel.models import AgentState; from autosentinel.agents.base import BaseAgent"` succeeds with no errors.

---

## Phase 2: Test-First Gate (NON-NEGOTIABLE — SC-006)

**Purpose**: Write ALL failing tests. Every file below MUST raise `ImportError` or `AssertionError` when run.
**⚠️ CRITICAL**: After completing all T004–T013, run `pytest --no-header -q 2>&1 | grep -E "ERROR|FAILED"` to confirm failures, then make a single git commit whose message contains exactly `"failing — Test-First gate"`. NO implementation may start before this commit exists.

- [ ] T004 [P] ⚠ WRITE FAILING — `tests/unit/test_diagnosis_agent.py`: tests for DiagnosisAgent keyword routing (CODE/INFRA/CONFIG/SECURITY classification, fallback, agent_trace append)
- [ ] T005 [P] ⚠ WRITE FAILING — `tests/unit/test_supervisor_agent.py`: tests for SupervisorAgent routing table (CODE→CodeFixer, INFRA→InfraSRE, CONFIG→InfraSRE, SECURITY→CodeFixer, UNKNOWN→CodeFixer fallback, routing_decision format, agent_trace append)
- [ ] T006 [P] ⚠ WRITE FAILING — `tests/unit/test_code_fixer_agent.py`: tests for CodeFixerAgent mock fix generation (fix_artifact set, TODO comment present, agent_trace append)
- [ ] T007 [P] ⚠ WRITE FAILING — `tests/unit/test_infra_sre_agent.py`: tests for InfraSREAgent mock fix generation (fix_artifact set for INFRA/CONFIG, agent_trace append)
- [ ] T008 [P] ⚠ WRITE FAILING — `tests/unit/test_security_reviewer_agent.py`: tests for SecurityReviewerAgent keyword detection (SAFE for clean scripts, HIGH_RISK for each keyword in _HIGH_RISK_KEYWORDS, agent_trace append)
- [ ] T009 [P] ⚠ WRITE FAILING — `tests/unit/test_verifier_agent.py`: tests for VerifierAgent (produces ExecutionResult, reads fix_artifact, appends to agent_trace; mock Docker success/failure/timeout/unavailable)
- [ ] T010 [P] ⚠ WRITE FAILING — `tests/unit/test_docker_import_boundary.py`: SC-004 AST check — walks all `.py` under `autosentinel/`, asserts only `autosentinel/agents/verifier.py` imports `docker`
- [ ] T011 ⚠ WRITE FAILING — `tests/integration/test_multi_agent_graph.py`: integration tests for routing (4 categories), interrupt/resume (HIGH_RISK), parallel fan-out (both agents in agent_trace), CAUTION pass-through, Docker-unavailable resilience (quickstart.md scenarios 1–8)
- [ ] T012 [P] ⚠ WRITE FAILING — `tests/test_benchmark.py`: assert `output/benchmark-report.json` exists after `run_benchmark()`, contains `scenario_count=5`, `v1_resolution_rate`, `v2_resolution_rate`, `v1_avg_ms`, `v2_avg_ms`
- [ ] T013 [P] ⚠ WRITE FAILING — update `tests/unit/test_format_report.py`: add 3 tests for Security Review section (SAFE no badge, CAUTION badge "⚠ CAUTION", HIGH_RISK approved badge "🚨 HIGH RISK")

**GATE**: Run `pytest tests/unit/test_diagnosis_agent.py tests/unit/test_supervisor_agent.py tests/unit/test_code_fixer_agent.py tests/unit/test_infra_sre_agent.py tests/unit/test_security_reviewer_agent.py tests/unit/test_verifier_agent.py tests/unit/test_docker_import_boundary.py tests/integration/test_multi_agent_graph.py tests/test_benchmark.py -q 2>&1 | tail -5` — confirm all ERROR/FAILED, then:

```
git add tests/
git commit -m "tests: add Sprint 4 agent + graph tests — failing — Test-First gate"
```

Commit message MUST contain `"failing — Test-First gate"` (SC-006). No implementation begins before this commit.

---

## Phase 3: User Story 1 — Specialist Agent Routing (Priority: P1) 🎯

**Goal**: DiagnosisAgent classifies errors; SupervisorAgent routes to the correct specialist; routing_decision recorded in state; graph wires parse_log → diagnosis → supervisor → specialist.

**Independent Test**: `pytest tests/unit/test_diagnosis_agent.py tests/unit/test_supervisor_agent.py -v` all green; `pytest tests/integration/test_multi_agent_graph.py -k "routing" -v` all green.

- [ ] T014 [US1] Implement `autosentinel/agents/diagnosis.py` — DiagnosisAgent with keyword mock `_mock_classify()` mapping (connectivity/resource_exhaustion → INFRA, configuration → CONFIG, application_logic → CODE), `# TODO(W2): replace with real LLM call`, returns `{error_category, agent_trace: ["DiagnosisAgent"]}`
- [ ] T015 [US1] Implement `autosentinel/agents/supervisor.py` — SupervisorAgent routing table (CODE/SECURITY/UNKNOWN → "code_fixer"; INFRA/CONFIG → "infra_sre"), returns `{routing_decision: "CATEGORY → AgentName", agent_trace: ["SupervisorAgent"]}`
- [ ] T016 [US1] Create `autosentinel/multi_agent_graph.py` — `build_multi_agent_graph()` sequential stub: parse_log → diagnosis_agent → supervisor_route → (code_fixer_agent OR infra_sre_agent) → security_reviewer → supervisor_merge → security_gate → verifier_agent → format_report → END; compile with `checkpointer=MemorySaver()`

**Checkpoint**: `pytest tests/unit/test_diagnosis_agent.py tests/unit/test_supervisor_agent.py -v` → all PASSED.

---

## Phase 4: User Story 2 — Security Review Gate (Priority: P1)

**Goal**: SecurityReviewerAgent classifies fix_script with keyword mock; security_gate suspends pipeline on HIGH_RISK via interrupt(); human_approval_required log event emitted; CAUTION passes through.

**Independent Test**: `pytest tests/unit/test_security_reviewer_agent.py -v` all green; `pytest tests/integration/test_multi_agent_graph.py -k "high_risk or interrupt or caution" -v` all green.

- [ ] T017 [US2] Implement `autosentinel/agents/security_reviewer.py` — SecurityReviewerAgent with `_HIGH_RISK_KEYWORDS` list, keyword-scans `state.get("fix_script") or ""`, returns `{security_verdict: "SAFE"|"HIGH_RISK", agent_trace: ["SecurityReviewerAgent"]}`, `# TODO(W2): replace with real LLM call`
- [ ] T018 [US2] Implement `security_gate` node in `autosentinel/multi_agent_graph.py` — reads `security_verdict`; for HIGH_RISK: logs `human_approval_required` (soft guarantee — log failure must NOT block interrupt), calls `interrupt({reason, fix_artifact})`; always returns `{approval_required: verdict=="HIGH_RISK"}`

**Checkpoint**: `pytest tests/unit/test_security_reviewer_agent.py tests/integration/test_multi_agent_graph.py -k "security or interrupt or caution" -v` → all PASSED.

---

## Phase 5: User Story 4 — Verifier Agent as Sole Docker Executor (Priority: P1)

**Goal**: VerifierAgent wraps Sprint 3 execute_fix logic, reads fix_artifact; CodeFixerAgent and InfraSREAgent provide mock fix generation; Docker import boundary check passes.

**Independent Test**: `pytest tests/unit/test_verifier_agent.py tests/unit/test_docker_import_boundary.py tests/unit/test_code_fixer_agent.py tests/unit/test_infra_sre_agent.py -v` all green.

- [ ] T019 [P] [US4] Implement `autosentinel/agents/code_fixer.py` — CodeFixerAgent with `_MOCK_FIXES` dict (CODE/SECURITY categories), `# TODO(W2)`, returns `{fix_artifact, agent_trace: ["CodeFixerAgent"]}`
- [ ] T020 [P] [US4] Implement `autosentinel/agents/infra_sre.py` — InfraSREAgent with `_MOCK_FIXES` dict (INFRA/CONFIG categories), `# TODO(W2)`, returns `{fix_artifact, agent_trace: ["InfraSREAgent"]}`
- [ ] T021 [US4] Implement `autosentinel/agents/verifier.py` — VerifierAgent: ONLY agent that imports `docker`; reads `fix_artifact`, proxies to extracted `_execute_fix_logic()` from `nodes/execute_fix.py`, returns `{execution_result, execution_error, agent_trace: ["VerifierAgent"]}`

**Checkpoint**: `pytest tests/unit/test_verifier_agent.py tests/unit/test_docker_import_boundary.py tests/unit/test_code_fixer_agent.py tests/unit/test_infra_sre_agent.py -v` → all PASSED (Docker mocked).

---

## Phase 6: User Story 3 — Parallel Fan-Out (Priority: P2)

**Goal**: After supervisor_route, specialist agent AND security_reviewer run in parallel via LangGraph fan-out edges; both appear in agent_trace; `Annotated[list[str], operator.add]` reducer prevents InvalidUpdateError.

**Independent Test**: `pytest tests/integration/test_multi_agent_graph.py -k "parallel" -v` all green; agent_trace contains both specialist and SecurityReviewerAgent.

- [ ] T022 [US3] Wire parallel fan-out in `autosentinel/multi_agent_graph.py` — replace sequential specialist→security_reviewer with fan-out: `add_conditional_edges("supervisor_route", _route_to_specialist, {"code_fixer": "code_fixer_agent", "infra_sre": "infra_sre_agent"})` + `add_edge("supervisor_route", "security_reviewer")`; fan-in: both specialist edges + security_reviewer edge → supervisor_merge; verify AgentState.agent_trace uses `Annotated[list[str], operator.add]` (already set in T001)

**Checkpoint**: `pytest tests/integration/test_multi_agent_graph.py -v` → all PASSED; run one scenario and confirm both specialist + SecurityReviewerAgent in agent_trace.

---

## Phase 7: Report Integration — Security Review Section (US2/US3)

**Goal**: format_report reads security_verdict, routing_decision, agent_trace and appends a "## Security Review" section with SAFE/CAUTION/HIGH_RISK badges.

**Independent Test**: `pytest tests/unit/test_format_report.py -v` all green (including 3 new security-verdict tests from T013).

- [ ] T023 Update `autosentinel/nodes/format_report.py` — append `## Security Review` section after "## Sandbox Execution": reads `state.get("security_verdict")`, `state.get("routing_decision")`, `state.get("agent_trace", [])`; renders CAUTION badge (`⚠ CAUTION`) when verdict=="CAUTION"; renders HIGH_RISK badge (`🚨 HIGH RISK — executed after human approval`) when `approval_required==True`

**Checkpoint**: `pytest tests/unit/test_format_report.py -v` → all PASSED including security section tests.

---

## Phase 8: User Story 5 — v1 vs v2 Smoke Benchmark (Priority: P3)

**Goal**: `autosentinel/benchmark.py` runs 5 predefined smoke scenarios through both pipelines (Docker mocked), writes `output/benchmark-report.json` with v1/v2 resolution rates and timing.

**Independent Test**: `pytest tests/test_benchmark.py -v` all green; output file parseable by json.loads().

- [ ] T024 [US5] Implement `autosentinel/benchmark.py` — define `SCENARIOS: list[dict]` with 5 entries (s01=CODE, s02=INFRA, s03=CONFIG, s04=SECURITY, s05=UNKNOWN/fallback); implement `run_benchmark() -> dict`; `if __name__ == "__main__"` CLI entry; writes `output/benchmark-report.json` with fields: `scenario_count`, `v1_resolution_rate`, `v2_resolution_rate`, `v1_avg_ms`, `v2_avg_ms`

**Checkpoint**: `pytest tests/test_benchmark.py -v` → all PASSED; `python -m autosentinel.benchmark` exits 0.

---

## Phase 9: Polish & Coverage

**Purpose**: Wire feature flag, update run_pipeline(), verify full suite at 100% coverage.

- [ ] T025 Update `autosentinel/__init__.py` — add `AUTOSENTINEL_MULTI_AGENT` feature flag to `run_pipeline()`: `use_multi_agent = os.getenv("AUTOSENTINEL_MULTI_AGENT", "0") == "1"`; call `build_multi_agent_graph()` when set, else `build_graph()`; initial_state MUST include all AgentState fields (fix Sprint 3 gap: `fix_script=None, execution_result=None, execution_error=None`)
- [ ] T026 Update `tests/integration/test_pipeline.py` — update `test_pipeline_node_execution_order` to assert v1 order `["parse_log", "analyze_error", "execute_fix", "format_report"]` still passes; add test for v2 pipeline invocation via feature flag
- [ ] T027 Run full test suite and confirm 100% branch coverage: `pytest --cov=autosentinel --cov-branch --cov-report=term-missing -q`; fix any gaps

**Final Checkpoint**: `pytest --cov=autosentinel --cov-branch -q` → all PASSED, 100% coverage, no regressions on Sprint 1–3 tests.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Test-First Gate)**: Depends on Phase 1 — write all tests, commit "failing — Test-First gate" before Phase 3
- **Phase 3 (US1 Routing)**: Depends on Phase 2 commit — P1
- **Phase 4 (US2 Security Gate)**: Depends on Phase 3 (needs graph stub) — P1
- **Phase 5 (US4 Verifier)**: Depends on Phase 2 commit (can run after Phase 3/4 or in parallel with Phase 4 for different files) — P1
- **Phase 6 (US3 Fan-Out)**: Depends on Phase 3 + Phase 4 + Phase 5 complete — P2
- **Phase 7 (Report)**: Depends on Phase 6 (needs security_verdict in state) — can run after Phase 4
- **Phase 8 (US5 Benchmark)**: Depends on all P1 phases complete — P3
- **Phase 9 (Polish)**: Depends on all prior phases

### Critical Path

```
T001 → T002 → T003
             ↓
      T004–T013 (parallel, all Phase 2)
             ↓
      COMMIT "failing — Test-First gate"
             ↓
      T014 → T015 → T016      (US1, sequential)
             ↓
      T017 → T018              (US2, sequential)
      T019 ─┐                  (US4, parallel)
      T020 ─┤ → T021           (US4)
             ↓
      T022                     (US3 fan-out, depends on US1+US2+US4)
             ↓
      T023                     (Report, depends on fan-out)
             ↓
      T024                     (US5 Benchmark)
             ↓
      T025 → T026 → T027       (Polish)
```

### Within Each Phase

- Phase 2 tasks (T004–T013) MUST all fail before implementation starts
- Phase 5 tasks T019 and T020 (CodeFixerAgent, InfraSREAgent) can run in parallel (different files)
- Phase 9 tasks must run sequentially (T025 updates __init__.py, T026 references it, T027 validates all)

---

## Parallel Opportunities

### Phase 2: All test files can be written in parallel
```
T004 test_diagnosis_agent.py    ─┐
T005 test_supervisor_agent.py   ─┤
T006 test_code_fixer_agent.py   ─┤ all in parallel
T007 test_infra_sre_agent.py    ─┤ (different files)
T008 test_security_reviewer.py  ─┤
T009 test_verifier_agent.py     ─┤
T010 test_docker_boundary.py    ─┤
T012 test_benchmark.py          ─┤
T013 test_format_report.py      ─┘
T011 test_multi_agent_graph.py  (slightly more complex — write last)
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

1. MVP above → then Phase 6 (US3 Fan-Out, T022)
2. Phase 7 (Report integration, T023)
3. Phase 8 (US5 Benchmark, T024)
4. Phase 9 (Polish, T025–T027)

---

## Notes

- [P] tasks = different files, no blocking dependencies between them
- **Phase 2 is a hard gate** — no implementation PR is valid without the "failing — Test-First gate" commit preceding it on the branch (SC-006)
- All mock `run()` methods MUST include `# TODO(W2): replace with real LLM call` (FR-010)
- Docker is NEVER imported outside `autosentinel/agents/verifier.py` (FR-008 / SC-004)
- `agent_trace: Annotated[list[str], operator.add]` is the only field requiring a reducer; `fix_artifact` and `security_verdict` are written by exactly one branch each (research.md Decision 1)
- `build_multi_agent_graph()` MUST compile with `checkpointer=MemorySaver()` for interrupt() to work (research.md Decision 2)
- Task count: 27 tasks total (3 setup + 10 test-first + 14 implementation)
