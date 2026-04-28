# Feature Specification: Sprint 4 - Multi-Agent Migration

**Feature Branch**: `004-multi-agent-migration`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: "Sprint 4 - Multi-Agent Architecture: evolve AutoSentinel from single-agent to 5-agent + 1-supervisor collaborative architecture"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Specialist Agent Routing by Error Category (Priority: P1)

When an error log arrives, the system automatically routes it to the most appropriate specialist agent based on error category, rather than applying a single generic diagnosis-and-fix flow. An operator can see in the structured logs which agent handled the incident and why.

**Why this priority**: Routing is the prerequisite for all other multi-agent behaviour. Without correct routing, the specialist agents are unreachable, making every subsequent user story impossible.

**Independent Test**: Inject four error logs (one per category: CODE / INFRA / SECURITY / CONFIG). Assert that each is handled by its correct specialist agent and that the Supervisor's routing decision is recorded in the LangGraph state.

**Acceptance Scenarios**:

1. **Given** an error log whose Diagnosis Agent output is `CODE`, **When** the Supervisor routes, **Then** the Code Fixer Agent is invoked and neither the Infra/SRE Agent nor the Security Reviewer Agent generates a fix.
2. **Given** an error log whose Diagnosis Agent output is `INFRA`, **When** the Supervisor routes, **Then** the Infra/SRE Agent is invoked.
3. **Given** an error log whose Diagnosis Agent output is `CONFIG`, **When** the Supervisor routes, **Then** the Config Agent path is taken.
4. **Given** the Supervisor receives contradictory recommendations from two active agents, **When** it arbitrates, **Then** it selects the lower-blast-radius action and records its reasoning in state.

---

### User Story 2 - Security Review Gate Before Execution (Priority: P1)

Every fix artifact produced by a specialist agent is reviewed by the Security Reviewer Agent before it reaches the Verifier Agent. Fixes classified as `HIGH_RISK` (production config changes, database writes, secrets access) are blocked from auto-execution and require explicit human approval.

**Why this priority**: Co-equal with routing — without the security gate, the system cannot safely accept user story 3 or 4. Defined as P1 because it directly fulfils Constitution Principle VI and protects production environments from LLM-hallucinated dangerous commands.

**Independent Test**: Submit a fix that contains a destructive shell command (e.g., `DROP TABLE`) and assert: (a) Security Reviewer classifies it `HIGH_RISK`, (b) a `LangGraph interrupt()` is triggered, (c) the Verifier Agent is NOT invoked before approval, (d) the `human_approval_required` event appears in the structured log.

**Acceptance Scenarios**:

1. **Given** a fix classified `SAFE` by Security Reviewer, **When** the pipeline continues, **Then** the Verifier Agent is invoked immediately with no interrupt.
2. **Given** a fix classified `HIGH_RISK`, **When** Security Reviewer returns its verdict, **Then** the pipeline suspends via `interrupt()` and the human-approval log event is emitted before any container is started.
3. **Given** a fix classified `CAUTION`, **When** the pipeline continues, **Then** the Verifier Agent is invoked and a `caution_flag` field is set in the report.
4. **Given** a `HIGH_RISK` fix receives explicit human approval via pipeline resume, **When** the pipeline resumes, **Then** the Verifier Agent proceeds normally.

---

### User Story 3 - Parallel Execution of Code Fixer and Security Reviewer (Priority: P2)

After Diagnosis completes, the Code Fixer Agent and the Security Reviewer Agent run in parallel on the same error context. The pipeline does not wait for Code Fixer to finish before starting Security Review. Operators observe reduced end-to-end latency compared to the sequential v1 pipeline.

**Why this priority**: Parallelism is a latency optimisation that builds on P1 (routing and security gate must exist first). Delivers the MTTR improvement that justifies the migration.

**Independent Test**: Record wall-clock timestamps for Code Fixer start, Security Reviewer start, and their respective completions. Assert that Security Reviewer start time < Code Fixer completion time (i.e., they overlapped).

**Acceptance Scenarios**:

1. **Given** the Diagnosis Agent completes, **When** the graph executes the next step, **Then** Code Fixer and Security Reviewer nodes are dispatched concurrently via LangGraph's parallel fan-out.
2. **Given** both parallel agents complete, **When** the Supervisor collects results, **Then** it merges their outputs before passing to the Verifier Agent.
3. **Given** one parallel agent fails (mock exception), **When** the other completes, **Then** the pipeline still produces a partial result rather than crashing.

---

### User Story 4 - Verifier Agent as Sole Docker Executor (Priority: P1)

The Verifier Agent is the only component in the system that may call the Docker SDK. All other agents are prohibited from starting containers. The Verifier runs the approved fix script, captures the result, and updates the pipeline state with pass/fail evidence.

**Why this priority**: Elevated to P1 because Constitution Principle VI makes this a mandatory architectural constraint from day one — implementing other agents before the Docker isolation boundary is established would produce code that violates the constitution and then requires a breaking rewrite. Building the boundary first prevents that pattern.

**Independent Test**: After replacing the existing `execute_fix` node with the Verifier Agent, verify: (a) no other agent module imports the Docker SDK, (b) Verifier produces the same `ExecutionResult` structure as the Sprint 3 node, (c) the full pipeline still achieves 100% coverage with Docker mocked.

**Acceptance Scenarios**:

1. **Given** a `SAFE`-classified fix, **When** the Verifier Agent runs, **Then** it executes the script in a `python:3.10-alpine` container with `mem_limit=64m` and `network_mode=none`.
2. **Given** a successful container run, **When** the Verifier collects output, **Then** `ExecutionResult` is populated with stdout, stderr, return code, and duration.
3. **Given** a timeout, **When** the container exceeds 5 seconds, **Then** the container is killed, removed, and `ExecutionResult.status = "timeout"` is recorded.

---

### User Story 5 - v1 vs v2 Smoke Benchmark (5-Scenario Suite) (Priority: P3)

A smoke benchmark harness runs 5 synthetic error scenarios (one per major category plus one edge case) through both the v1 (single-agent) and v2 (multi-agent) pipelines, comparing resolution rate and average processing time. Results are written to a benchmark report file. The full 50-scenario suite is deferred to Sprint 5.

**Why this priority**: Validates that the migration does not regress correctness on the most representative cases, without crowding out Sprint 4's implementation time. P3 because it requires all other stories to be complete first. The 5-scenario scope is intentionally minimal — sufficient for CI gating, not for statistical conclusions.

**Independent Test**: Run `python -m autosentinel.benchmark` and assert the output file exists and contains fields `v1_resolution_rate`, `v2_resolution_rate`, `v1_avg_ms`, `v2_avg_ms`, `scenario_count`.

**Acceptance Scenarios**:

1. **Given** 5 pre-defined smoke scenarios (1 CODE, 1 INFRA, 1 SECURITY, 1 CONFIG, 1 unknown/fallback), **When** the benchmark runs both pipelines with Docker mocked, **Then** both complete without unhandled exceptions.
2. **Given** the benchmark completes, **When** results are written, **Then** `v2_resolution_rate` is reported alongside `v1_resolution_rate` and neither is `null`.
3. **Given** the benchmark report is written, **Then** it is a valid JSON file parseable by `json.loads()` and contains `scenario_count: 5`.

**Sprint 5 extension**: The 5 scenarios are designed to be extended to 50 (12 CODE, 15 INFRA, 8 SECURITY, 15 CONFIG) in Sprint 5 without changing the benchmark module's interface.

---

### Edge Cases

- What if the Diagnosis Agent cannot classify the error? (Supervisor falls back to `application_logic` category, routes to Code Fixer as default, sets low-confidence flag in state.)
- What if both Code Fixer and Security Reviewer are still running when a timeout fires? (LangGraph's parallel branch timeout cancels both; partial results are preserved in state.)
- What if the human approval for a `HIGH_RISK` fix is never received? (Pipeline remains suspended; a timeout policy cancels and records `approval_timeout` in state — out of scope for Sprint 4, documented as assumption.)
- What if the Verifier Agent's Docker container image is not available? (Same behavior as Sprint 3 `execute_fix`: error captured in `execution_error`, pipeline continues to report generation.)

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST replace the existing linear LangGraph pipeline with a 6-node agent graph: Supervisor, Diagnosis, Code Fixer, Infra/SRE, Security Reviewer, Verifier.
- **FR-002**: Each agent MUST implement a `BaseAgent` interface with a single `run(state: AgentState) -> AgentState` method, where `AgentState` is a Pydantic V2 model or a `TypedDict` compatible with LangGraph's state channel reducer. Returning a bare `dict` is prohibited. Agents MUST NOT expose other public methods for inter-agent invocation.
- **FR-003**: Agent communication MUST flow exclusively through LangGraph state channels (TypedDict fields); direct Python method calls between agent instances are prohibited.
- **FR-004**: The Supervisor Agent MUST route based on the Diagnosis Agent's `error_category` output and MUST arbitrate conflicts by selecting the lower-blast-radius action.
- **FR-005**: The Security Reviewer Agent MUST classify every fix as `SAFE`, `CAUTION`, or `HIGH_RISK` before it reaches the Verifier Agent.
- **FR-006**: Fixes classified `HIGH_RISK` MUST trigger `LangGraph interrupt()` and emit a `human_approval_required` structured log event before any Docker container is started.
- **FR-007**: After Diagnosis completes, Code Fixer and Security Reviewer MUST execute as parallel LangGraph nodes (fan-out).
- **FR-008**: The Verifier Agent MUST be the only agent that imports or invokes the Docker SDK; all other agent modules MUST NOT import `docker`.
- **FR-009**: The existing FastAPI gateway, `asyncio.Queue`, and `run_pipeline()` entry point MUST remain unchanged in interface; the multi-agent graph is a drop-in replacement for the existing `build_graph()` call.
- **FR-010**: All agent implementations in Sprint 4 MUST use mock `run()` methods that return deterministic state; real LLM API calls are deferred to Sprint 5. Every mock MUST include a `# TODO(W2): replace with real LLM call` comment.
- **FR-011**: A benchmark module `autosentinel/benchmark.py` MUST run 5 smoke scenarios through v1 and v2 pipelines and write results to `output/benchmark-report.json`. The scenario list MUST be defined in a separate data structure (not inline) so Sprint 5 can extend it to 50 without modifying the runner logic.
- **FR-012**: CI MUST remain green (all existing tests pass, 100% coverage maintained) after every committed increment.

### Key Entities

- **BaseAgent**: Abstract class with a single abstract method `run(state: AgentState) -> AgentState`, where `AgentState` is a Pydantic V2 model or a LangGraph-compatible `TypedDict`. Returning a bare `dict` is prohibited. All six agent classes inherit from it.
- **AgentState**: Extended `DiagnosticState` TypedDict with new fields: `error_category` (str), `fix_artifact` (Optional[str]), `security_verdict` (str: SAFE/CAUTION/HIGH_RISK), `routing_decision` (str), `agent_trace` (list[str]), `approval_required` (bool).
- **SupervisorAgent**: Routes, arbitrates. No LLM call.
- **DiagnosisAgent**: Classifies error into CODE / INFRA / SECURITY / CONFIG. Mock in Sprint 4.
- **CodeFixerAgent**: Generates fix for CODE errors. Mock in Sprint 4.
- **InfraSREAgent**: Generates fix for INFRA errors. Mock in Sprint 4.
- **SecurityReviewerAgent**: Classifies fix artifact into SAFE / CAUTION / HIGH_RISK. Mock in Sprint 4.
- **VerifierAgent**: Wraps Sprint 3's `execute_fix` logic. Only Docker-capable agent.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 5 smoke benchmark scenarios complete without unhandled exceptions in both v1 and v2 pipelines.
- **SC-002**: `v2_resolution_rate` is reported in `benchmark-report.json` and is ≥ `v1_resolution_rate` across the 5 smoke scenarios.
- **SC-003**: `HIGH_RISK` classified fixes never reach the Verifier Agent without a recorded `human_approval_required` log event — verified in CI by a dedicated test that inspects the captured log stream.
- **SC-004**: No agent module other than `VerifierAgent` imports the `docker` package — verified by an automated CI check (ruff custom rule, import-linter, or equivalent AST-level tool; grep is insufficient).
- **SC-005**: The full test suite (including all Sprint 1–3 tests) passes at 100% branch coverage after the migration.
- **SC-006**: Test-First gate (Constitution Principle III — NON-NEGOTIABLE): for each of the six agent classes and the multi-agent graph, a corresponding test file MUST exist and all new tests MUST be confirmed failing (ImportError or AssertionError) in a dedicated commit before any agent implementation file is created. The commit message for that commit MUST contain the string "failing — Test-First gate". No implementation commit may be merged unless the immediately preceding commit on the same branch contains that string.
- **SC-007**: `v2_avg_ms` for a CODE-category smoke scenario is written to `benchmark-report.json` (value may be any non-null integer; no performance regression target is imposed in Sprint 4).

---

## Assumptions

- Sprint 4 uses mock agent implementations only; real LLM integration is deferred to Sprint 5 ("W2" work). Every mock `run()` method MUST include a `# TODO(W2): replace with real LLM call` comment.
- The smoke benchmark contains 5 synthetic scenarios hard-coded in `autosentinel/benchmark.py`; expansion to 50 is Sprint 5 scope. Scenario definitions are stored in a separate data structure to make that extension non-breaking.
- Human approval for `HIGH_RISK` fixes is simulated in tests by directly resuming the LangGraph checkpoint; no external approval UI is built in Sprint 4.
- The existing `asyncio.Queue` + FastAPI gateway remains unchanged; the multi-agent graph is a drop-in replacement for `build_graph()` and is only invoked via `run_pipeline()`.
- LangGraph's built-in parallel node execution (Send API or fan-out edges) is the assumed mechanism for the Code Fixer / Security Reviewer parallel step; this MUST be confirmed and recorded in research.md during `/speckit.plan`.
- `interrupt()` approval timeout policy (what happens if approval never arrives) is out of scope for Sprint 4; it is documented as a known gap and MUST be addressed in Sprint 5.
- US3 (parallel execution) is P2, depending on US1 (routing), US2 (security gate), and US4 (Verifier isolation) all being P1 and implemented first.
