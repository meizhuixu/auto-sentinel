---
description: "Sprint 5 — Real LLM Integration: dependency-ordered task list"
---

# Tasks: Sprint 5 — Real LLM Integration

**Input**: Design documents at `/specs/005-real-llm-integration/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/ (4 files), quickstart.md

**Tests**: REQUIRED. Constitution Principle III (Test-First, NON-NEGOTIABLE) — every implementation task is preceded by a failing-test task with an explicit dependency. 100 % branch coverage required on `autosentinel/llm/`.

**Organization**: Tasks grouped by user story per template, with `[PR-N]` annotations on each task description so reviewers can see PR membership at a glance. PR boundaries follow plan.md Phase 1-6: PR-1 = Setup + Foundational, PR-2 = US1 specialists, PR-3 = US2 routing, PR-4 = US1 cross-process resume + US3 + US4, PR-5 = US5 + Polish.

## Format: `[ID] [P?] [Story?] [PR-N] Description`

- **[P]**: parallelizable (different files, no dependency on incomplete tasks).
- **[Story]**: US1 / US2 / US3 / US4 / US5 — required for User Story phases, omitted for Setup / Foundational / Polish.
- **[PR-N]**: PR membership (PR-1 through PR-5). Embedded in description, not a template-format slot.
- File paths are absolute relative to repo root.

## Path Conventions

Single Python project. Source under `autosentinel/`, tests under `tests/`, infra under `infra/`, scenarios under `benchmarks/scenarios/`, scripts under `scripts/`, configs under `config/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project scaffolding, dependency installation, infra container, config skeletons. All `[PR-1]`.

- [X] T001 [PR-1] Create `autosentinel/llm/` package with `__init__.py` (empty body, the package marker only)
- [X] T002 [P] [PR-1] Create `config/model_routing.yaml` with the full 5-agent + 2-endpoint declaration per `plan.md` Block 4 (agents: diagnosis/supervisor/code_fixer/infra_sre/security_reviewer; endpoints: ark + glm with `api_key_env` ARK_API_KEY / GLM_API_KEY)
- [X] T003 [P] [PR-1] Create `infra/docker-compose.checkpointer.yml` declaring `postgres:16` service `auto-sentinel-checkpointer` on `localhost:5434` with credentials `postgres/postgres` (acknowledge as Phase-4 AWS technical debt in inline comment)
- [X] T004 [P] [PR-1] Create directory structure `benchmarks/scenarios/`, `benchmarks/results/` with `.gitkeep` files
- [X] T005 [P] [PR-1] Add Sprint 5 dependencies to `pyproject.toml`: `openai>=1.40`, `langgraph-checkpoint-postgres`, `psycopg[binary]>=3.1`, `tenacity`, `pydantic-settings`, `pyyaml`, `httpx` (verify `langgraph==1.1.9` already present from Sprint 4)

**Checkpoint**: Setup complete. Run `docker compose -f infra/docker-compose.checkpointer.yml up -d` and `nc -z localhost 5434` succeeds. `uv sync` completes without errors.

---

## Phase 2: Foundational (Blocking Prerequisites — PR-1)

**Purpose**: LLM Client foundation + CostGuard + AgentState extension. NO user-story work begins until this phase is green.

**⚠️ CRITICAL**: T006-T013 (failing tests) MUST be committed before any of T014-T024 (implementations). Constitution III gate.

### Test-First gate (PR-1, all parallel — different test files)

- [X] T006 [P] [PR-1] Write `tests/unit/test_llm_provider_isolation.py` — AST walker over every `*.py` under `autosentinel/`, hard-coded allowlist `{autosentinel/llm/ark_client.py, autosentinel/llm/glm_client.py}`. Fails on any other file containing `import openai` / `from openai`. Trivially passes today (no openai imports yet); will fail when T021 introduces `import openai` if T021 forgets to be inside an allowlisted file.
- [X] T007 [P] [PR-1] Write `tests/unit/test_no_hardcoded_models.py` — grep all files under `autosentinel/agents/` for prohibited literals: `doubao-`, `glm-`, `ark.cn-beijing`, `open.bigmodel.cn`. Any hit fails the test (Constitution VII.4).
- [X] T008 [P] [PR-1] Write `tests/unit/test_llm_protocol.py` — 4 cases per `contracts/llm-client.md`: `LLMRequest` accepts valid 32-char hex `trace_id`; rejects empty string with `ValueError`; rejects malformed (non-hex / wrong length); `LLMResponse` rejects negative `prompt_tokens`/`completion_tokens`/`cost_usd`; `Message` is frozen.
- [X] T009 [P] [PR-1] Write `tests/unit/test_cost_guard.py` — 3 cases per `contracts/cost-guard.md`: over-threshold raises `CostGuardError` with `current_spent_usd`/`attempted_amount_usd`/`budget_limit_usd` attributes; `reset_for_test()` succeeds with `PYTEST_CURRENT_TEST` set, raises `RuntimeError` without; 100-thread `accumulate(0.001)` race results in exact `Decimal("0.100")` total.
- [X] T010 [P] [PR-1] Write `tests/unit/test_model_routing.py` — `ModelRoutingConfig` validation: missing endpoint for declared model raises; missing API key env var at startup raises `ConfigurationError`; valid config back-fills `endpoint_alias` correctly.
- [X] T011 [P] [PR-1] Write `tests/unit/test_mock_client.py` — 3 cases: `with_fixture_response(resp)` returns the response; `with_error(exc)` raises; `call_count` increments per call; `last_request` mirrors the LLMRequest constructed.
- [X] T012 [P] [PR-1] Write `tests/unit/test_ark_client.py` — 3 cases against `httpx.MockTransport`: happy path returns `LLMResponse` with token counts; `httpx.TimeoutException` triggers tenacity retry (3 attempts) then raises `LLMTimeoutError`; HTTP 5xx raises `LLMProviderError`. Verifies tracer is opened with `trace_id` from request.
- [X] T013 [P] [PR-1] Write `tests/unit/test_glm_client.py` — same 3 cases as Ark with GLM `base_url` (`https://open.bigmodel.cn/api/paas/v4`).

### Implementation (PR-1)

- [X] T014 [PR-1] Implement `Message`, `LLMRequest`, `LLMResponse` Pydantic v2 schemas in `autosentinel/llm/protocol.py` per `data-model.md` §1-3 (frozen, `trace_id` regex validator, `Decimal` cost field)
- [X] T015 [PR-1] Append `LLMClient` Protocol to `autosentinel/llm/protocol.py` with the sync `complete(*, messages, model, trace_id, agent_name, max_tokens, temperature) -> LLMResponse` signature (depends T014)
- [X] T016 [P] [PR-1] Implement exception module in `autosentinel/llm/errors.py`: `CostGuardError(current_spent_usd, attempted_amount_usd, budget_limit_usd)`, `LLMTimeoutError`, `LLMProviderError`, `ConfigurationError` (per `data-model.md` §10)
- [X] T017 [PR-1] Implement `CostGuardState` Pydantic schema + `CostGuard` singleton + `threading.Lock` + `reset_for_test()` PYTEST_CURRENT_TEST gate + `get_cost_guard()` accessor in `autosentinel/llm/cost_guard.py`. Reads `AUTOSENTINEL_BUDGET_LIMIT_USD` env var (default `"20.6"`). Verify T009 turns GREEN. (depends T016)
- [X] T018 [P] [PR-1] Implement `AgentModelConfig`, `EndpointConfig`, `ModelRoutingConfig` Pydantic schemas (with cross-validator back-filling `endpoint_alias`) in `autosentinel/llm/factory.py` per `data-model.md` §4-6
- [X] T019 [PR-1] Implement `build_client_for_agent(agent_name) -> LLMClient` in `autosentinel/llm/factory.py`: loads `config/model_routing.yaml` via `pydantic-settings`, validates env vars present, caches one `OpenAI` SDK instance per endpoint alias, returns the bound concrete client. Verify T010 turns GREEN. (depends T015, T018)
- [X] T020 [P] [PR-1] Implement `MockLLMClient` in `autosentinel/llm/mock_client.py` per `contracts/llm-client.md` (`with_fixture_response`, `with_error`, `call_count`, `last_request`). Verify T011 turns GREEN. (depends T015)
- [X] T021 [PR-1] Implement `ArkLLMClient` in `autosentinel/llm/ark_client.py`: wraps `openai.OpenAI(base_url=...)`; tenacity `@retry(stop_after_attempt(3), wait_exponential(max=8))`; `httpx.Timeout(30.0)`; opens `LLMTracer(trace_id=..., project="auto-sentinel", component=agent_name)` around SDK call; sets tokens + `set_cost_breakdown(input_usd, output_usd)`; calls `cost_guard.accumulate(response.cost_usd)` AFTER response is built. Verify T006 (boundary) and T012 turn GREEN. (depends T015, T017, T020)
- [X] T022 [P] [PR-1] Implement `GlmLLMClient` in `autosentinel/llm/glm_client.py` (same shape as `ArkLLMClient` but with Zhipu `base_url`). Verify T013 turns GREEN. (depends T015, T017, T020)
- [X] T023 [P] [PR-1] Extend `AgentState` TypedDict in `autosentinel/models.py` with Sprint 5 section: `trace_id: NotRequired[str]`, `cost_accumulated_usd: NotRequired[float]` per `data-model.md` §8. **Do not modify** `autosentinel/agents/state.py` (re-export shim stays as-is).
- [X] T024 [PR-1] Update `tests/conftest.py`: add Sprint 5 fields to existing `AgentState` literal fixtures (with `NotRequired` defaults); add `cost_guard_reset` autouse fixture that calls `get_cost_guard().reset_for_test()` between tests. (depends T017, T023)

**Checkpoint**: PR-1 complete. `pytest tests/unit/test_llm_*.py tests/unit/test_cost_guard.py tests/unit/test_model_routing.py tests/unit/test_no_hardcoded_models.py` is green. `pytest --cov=autosentinel.llm --cov-fail-under=100` passes (deferred to Polish T065 for the integration-level coverage check, but unit-level coverage should already be at 100%).

---

## Phase 3: User Story 1 — Real LLM-Backed Diagnosis & Fix Generation (Priority: P1) 🎯 MVP

**Goal**: Diagnosis, CodeFixer, InfraSRE, SecurityReviewer agents reason via real LLM. HIGH_RISK interrupt persists across processes.

**Independent Test**: Submit two structurally different incidents (CODE + INFRA). Specialist outputs differ between them (not byte-equivalent fixtures). SecurityReviewer's verdict carries classifier identity. A HIGH_RISK interrupt raised in process A is resumable from process B.

### Tests (Test-First, parallel — different files)

- [X] T025 [P] [US1] [PR-2] Update `tests/unit/test_diagnosis_agent.py` (line 38): inject `MockLLMClient` via DI; assert `complete()` called with correct `agent_name="diagnosis"`, `model` from config, `trace_id` from state. Mark FAILING.
- [X] T026 [P] [US1] [PR-2] Update `tests/unit/test_code_fixer_agent.py` (line 34): inject `MockLLMClient`; assert real-LLM call observed for both CODE and SECURITY incident shapes. Mark FAILING.
- [X] T027 [P] [US1] [PR-2] Update `tests/unit/test_infra_sre_agent.py` (line 34): inject `MockLLMClient`. Mark FAILING.
- [X] T028 [P] [US1] [PR-2] Update `tests/unit/test_security_reviewer_agent.py` **all 3 setUp methods** (lines 34, 55, 80): inject `MockLLMClient` with HIGH_RISK / SAFE / CAUTION fixture responses respectively. Mark FAILING.
- [X] T029 [P] [US1] [PR-4] Write `tests/integration/test_postgres_checkpointer.py`: process-A starts pipeline → reaches HIGH_RISK interrupt → process exits → process-B starts (subprocess), connects to same PostgresSaver, calls `Command(resume=...)` with same `thread_id`, asserts pipeline resumes from interrupt point (specialist agents do NOT re-run) and reaches Verifier. Mark FAILING. (Requires `infra/docker-compose.checkpointer.yml` running.) (As-built [D2]: the graph exposes a test-only injection seam `build_multi_agent_graph(*, checkpointer=None, agents=None)` so PR-4 tests inject hermetic test-local LLM clients with **no production-factory change and no real spend**. T029 forces HIGH_RISK via a CodeFixer `"DROP TABLE users"` artifact caught by the SecurityReviewer deny-list. Process-B runs as a real subprocess via `tests/integration/_resume_worker.py`; shared doubles/builders live in `tests/integration/_pr4_helpers.py`. Committed FAILING in `41c8e42`.)

### Implementation — PR-2 (specialist DI + body wiring)

- [X] T030 [US1] [PR-2] **13-construction-site DI refactor (single discrete task — do NOT bundle with body changes)**: add `llm_client: LLMClient` keyword arg to `__init__` of `DiagnosisAgent`, `CodeFixerAgent`, `InfraSREAgent`, `SecurityReviewerAgent`. Update all 13 sites: `autosentinel/multi_agent_graph.py:21-25` (5 sites — pass `build_client_for_agent("<name>")`); `tests/unit/test_diagnosis_agent.py:38`, `test_supervisor_agent.py:32` (preview for US2), `test_code_fixer_agent.py:34`, `test_infra_sre_agent.py:34`, `test_security_reviewer_agent.py:34/55/80` (7 test sites — pass `MockLLMClient()`); `autosentinel/benchmark.py` (1 patch block) — delete `from unittest.mock import patch` (line 28), `from autosentinel.agents.code_fixer import CodeFixerAgent` (line 33), `patch_ctx`/`patch.object(CodeFixerAgent, "_get_fix_for_security", return_value="DROP TABLE users")` block (lines 168-175), and the surrounding `with patch_ctx:` wrapper. After this task, all 13 sites construct cleanly; tests T025-T028 still fail on body content (correct).
- [X] T031 [P] [US1] [PR-2] Replace `DiagnosisAgent.run()` mock body with real LLM call in `autosentinel/agents/diagnosis.py`: build messages from `state["error_log"]`; `self._llm_client.complete(...)` with `trace_id=state["trace_id"]`; parse structured output; populate `state["analysis_result"]`. Verify T025 turns GREEN.
- [X] T032 [P] [US1] [PR-2] Replace `CodeFixerAgent.run()` mock body with real LLM call in `autosentinel/agents/code_fixer.py`. Populates `state["fix_artifact"]`. Verify T026 turns GREEN.
- [X] T033 [P] [US1] [PR-2] Replace `InfraSREAgent.run()` mock body with real LLM call in `autosentinel/agents/infra_sre.py`. Populates `state["fix_artifact"]`. Verify T027 turns GREEN.
- [X] T034 [P] [US1] [PR-2] Replace `SecurityReviewerAgent.run()` mock body with real LLM call (GLM-4.7) in `autosentinel/agents/security_reviewer.py`. Emits binary verdict `SAFE` / `HIGH_RISK` (with optional `CAUTION`); records classifier identity (`model` field) in `state["agent_trace"]`. Verify T028 turns GREEN.

### Implementation — PR-4 (cross-process resume — depends on T035 PostgresSaver swap below)

- [X] T035 [US1] [PR-4] Make the checkpointer **injectable + env-gated** at `build_multi_agent_graph(*, checkpointer=None, ...)` (`autosentinel/multi_agent_graph.py`): when `checkpointer is None`, read `AUTOSENTINEL_CHECKPOINTER_DSN` — if set, use `PostgresSaver.from_conn_string(<dsn>)` and call `.setup()` once; if unset, fall back to `MemorySaver()`. Local-dev DSN default `postgresql://postgres:postgres@localhost:5434/postgres`. (As-built [D1]: the original "swap `MemorySaver()`→`PostgresSaver` at line 80 + `PostgresSaver.setup()` **at module import**" is NOT viable — `multi_agent_graph` constructs its graph and agent singletons at import time, so an import-time Postgres connection + `setup()` would break the entire hermetic suite at collection (CI has no container). The env-gated injectable form keeps the default test/dev path in-memory and zero-dependency, while T029 opts into Postgres by setting the DSN. **Not** a one-line compile-site change.)
- [X] T036 [US1] [PR-4] Add `POST /incidents/{incident_id}/resume` endpoint in `autosentinel/api/main.py`: body `{"decision": "approve"|"reject", "reviewer_notes": str}`; internally `graph.invoke(Command(resume=body), config={"configurable": {"thread_id": incident_id}})` on a graph bound to the same env-gated checkpointer (T035). Returns 200 with the post-resume state summary. **Test-First** (paired failing test — was missing from the original task list): write `tests/integration/test_resume_endpoint.py`, marked FAILING first — pre-seed a HIGH_RISK interrupt checkpoint at `thread_id == incident_id` via a PostgresSaver graph built with the D2 `agents=` seam (CodeFixer `"DROP TABLE users"` → SecurityReviewer deny-list → HIGH_RISK), then POST `/incidents/{incident_id}/resume` (Verifier's `docker` mocked for success) and assert (a) HTTP 200, (b) the post-resume summary shows the pipeline completed past the gate (Verifier ran; `approval_required` reflects the `approve` decision), (c) `trace_id` is preserved across the resume. Requires `infra/docker-compose.checkpointer.yml` on :5434. Verify it turns GREEN. (As-built [D2]: the endpoint builds the production graph, but on resume LangGraph replays the already-completed specialist nodes from the checkpoint, so **no real provider call is re-issued** — only post-interrupt nodes run; Verifier is `docker`-mocked.)
- [X] T037 [US1] [PR-4] Verify T029 turns GREEN: run process-A → process-B subprocess test against the live PostgresSaver container; assert agent_trace ordering shows specialists ran exactly once and Verifier ran in process-B.

**Checkpoint**: US1 fully functional. Real reasoning on 4 specialists; HIGH_RISK interrupt durable across processes. Sprint 4 SC-001..SC-005 still pass with `MockLLMClient` injected (verified later in T067).

---

## Phase 4: User Story 2 — Routing Intelligence via LLM Supervision (Priority: P1)

**Goal**: SupervisorAgent uses real LLM to interpret Diagnosis output and pick the correct specialist. Routing rationale captured in `state["routing_decision"]`.

**Independent Test**: Inject 4 incidents whose ground-truth category is non-obvious from surface keywords. Supervisor routes each to the correct specialist; rationale references Diagnosis output, not a hard-coded mapping.

- [X] T038 [US2] [PR-3] Update `tests/unit/test_supervisor_agent.py` (line 32, already DI-injected by T030): add fixture-based held-out routing test set of ≥ 20 incidents (categories CODE/INFRA/SECURITY/CONFIG, each with non-obvious surface text). Assert routing accuracy ≥ 70 %. Assert `state["routing_decision"]` references `state["analysis_result"]`. Mark FAILING. (As-built: the real-LLM held-out set landed as `data/routing-eval/held_out_v1.yaml` driven by `scripts/run_holdout_eval.py`; the in-suite mock fixture set lives in `tests/unit/test_supervisor_agent.py` per the original task.)
- [X] T039 [US2] [PR-3] Replace `SupervisorAgent.run()` mock body with real LLM routing call (doubao-1.5-lite-32k) in `autosentinel/agents/supervisor.py`: structured-output schema returns `{specialist: "code_fixer"|"infra_sre", rationale: str}` (`_VALID_SPECIALISTS = {"code_fixer","infra_sre"}`; SECURITY incidents are routed to `code_fixer` by the system prompt, mirroring the Sprint-4 2-way `get_specialist_key` fallback); persist rationale verbatim into `state["routing_decision"]`. Verify T038 turns GREEN. (depends T030)
- [X] T040 [US2] [PR-3] Run held-out routing test set manually one extra time outside CI to confirm ≥ 70 % accuracy is stable across two runs (LLM nondeterminism check); record both runs in PR-3 commit message. (As-built: run via `scripts/run_holdout_eval.py` against `data/routing-eval/held_out_v1.yaml`; both runs recorded in commit `13e44e3` — 95.0 % and 90.0 %.)

**Checkpoint**: US2 functional. Supervisor selects specialists from Diagnosis output via real LLM with rationale logged.

---

## Phase 5: User Story 3 — Cost & Budget Governance (Priority: P1)

**Goal**: All LLM calls funnel through `CostGuard`. Budget exhaustion aborts the pipeline cleanly with a typed error; user's partial fix is preserved.

**Independent Test**: With budget configured to a low test floor, run a known-budget-exceeding pipeline. Assert typed `CostGuardError`; no LLM call after the trip; `state["agent_trace"][-1] == "cost_guard_triggered"`.

- [X] T041 [US3] [PR-4] Write `tests/integration/test_cost_guard_pipeline.py` (FAILING): set `AUTOSENTINEL_BUDGET_LIMIT_USD=0.001`; inject `MockLLMClient` returning `cost_usd=Decimal("0.0005")` per call; run the multi-agent graph end-to-end; assert (a) `CostGuardError` propagates; (b) Verifier `run()` is NOT called; (c) `state["agent_trace"][-1] == "cost_guard_triggered"`; (d) `state["cost_accumulated_usd"]` matches the cumulative `Decimal` snapshot; (e) `summary.json.total_cost_usd == sum(per_call.cost_usd)` (drift check).
- [X] T042 [US3] [PR-4] Add `cost_exhausted_node` function in `autosentinel/multi_agent_graph.py`: writes `state["cost_accumulated_usd"] = float(cost_guard_state.total_spent_usd)`; appends `"cost_guard_triggered"` to `state["agent_trace"]`; returns `state` to END. Wire as the routing target whenever any node raises `CostGuardError`.
- [X] T043 [US3] [PR-4] Wire `CostGuardError` exception interception in graph execution: wrap each agent invocation in a thin catcher that, on `CostGuardError`, routes to `cost_exhausted_node` rather than propagating to the LangGraph error handler. Verify T041 turns GREEN.

**Checkpoint**: US3 functional. Budget ceiling enforced; partial fix preserved on abort.

---

## Phase 6: User Story 4 — Cross-Project Trace Correlation (Priority: P2)

**Goal**: One `trace_id` per incident, generated at FastAPI ingest, threaded through `AgentState`, surfaced as one parent trace + N child spans in Langfuse.

**Independent Test**: Run one incident through the full pipeline. Inspect Langfuse: exactly one parent trace; parent ID == `state["trace_id"]`; ≥ 1 child span per LLM-call agent; all spans tagged `project=auto-sentinel`, `component=<agent_name>`.

- [X] T044 [US4] [PR-4] Write `tests/integration/test_trace_propagation.py` (3 cases per `contracts/trace-propagation.md`): (a) `test_trace_id_end_to_end_consistency` — same `trace_id` observed on all 5 LLM-call agents; (b) `test_llmtracer_rejects_missing_trace_id` — `complete(trace_id="")` raises `ValueError`; (c) `test_state_serialization_preserves_trace_id` — round-trip through PostgresSaver preserves the field. Mark FAILING.
- [X] T045 [US4] [PR-4] In `autosentinel/api/main.py::ingest_alert`, generate the incident id via `secrets.token_hex(16)` (32-char lowercase hex) and **use it as both `job_id` and `trace_id`** — they are the same value (decision: `trace_id == job_id`). Carry it on the `AlertJob` and include `trace_id` in the 202 response body so callers can correlate. (As-built note: the prior `job_id = str(uuid.uuid4())` produced a 36-char hyphenated id that fails `LLMRequest`'s `^[0-9a-f]{32}$` trace_id regex; switching `job_id` to `token_hex(16)` makes the single id valid as a trace_id with no separate generation. Full-repo scan found no test asserting `job_id` length/format, so the change is safe.)
- [X] T046 [US4] [PR-4] Thread `trace_id` end-to-end into the graph: add a `trace_id` field to the `AlertJob` dataclass (`autosentinel/api/queue.py`), pass it from the worker into `run_pipeline(log_path, trace_id=...)` (new keyword param, `autosentinel/__init__.py`), and set `initial_state["trace_id"] = trace_id` before `graph.invoke(...)`. Verify T044 cases (a) and (c) turn GREEN. (As-built [D3]: the original wording — "`initial_state["trace_id"] = payload["trace_id"]` before `graph.invoke(...)` **in `queue.py`**" — does not match the architecture: `queue.py` has no `payload` dict and no `graph.invoke` (that lives in `run_pipeline`); the queue carries an `AlertJob` dataclass. Intent unchanged: the ingest-stamped trace_id flows `AlertJob` → `run_pipeline` → `initial_state`, unregenerated, per `contracts/trace-propagation.md` boundary 3.)
- [X] T047 [US4] [PR-4] Add explicit ValueError-surfacing path in `ArkLLMClient` / `GlmLLMClient` so that an empty `trace_id` from `LLMRequest` validation surfaces upward unwrapped. Verify T044 case (b) turns GREEN.

**Checkpoint**: US4 functional. Full incident traces correlate end-to-end in Langfuse.

---

## Phase 7: User Story 5 — Statistically Meaningful Benchmark (Priority: P2)

**Goal**: 50 human-labelled scenarios (12 CODE / 15 INFRA / 8 SECURITY / 15 CONFIG) drive a real-data benchmark; CI runs a 5-scenario smoke subset for free; full run is manual and budget-gated.

**Independent Test**: `benchmarks/results/{run_id}/summary.json` exists; `scenario_count == 50`; category distribution matches; v1/v2 metric triplets present; SC-013 `security_subset.v2_false_negative_count == 0`.

### Schema + migration

- [X] T048 [US5] [PR-5] Implement `BenchmarkScenario` and `BenchmarkResult` Pydantic v2 schemas at the top of `autosentinel/benchmark.py` per `data-model.md` §9 (frozen, `scenario_id` regex, all numeric fields ≥ 0, `cost_usd: Decimal`). Lands in the same file that T050 rewrites (no new file added; PR-5 reshapes `benchmark.py` to carry both schemas and the runner).
- [ ] T049 [US5] [PR-5] Migrate Sprint 4 `SCENARIOS[0..4]` to per-file yamls per `contracts/benchmark-scenario.md` Migration map: `001_code_null_user_context.yaml` (s01), `002_infra_db_connection_refused.yaml` (s02), `003_config_jwt_secret_missing.yaml` (s03), `004_security_sql_injection_attempt.yaml` (s04), `005_code_weird_exception.yaml` (s05 reclassified). Each yaml references the existing `data/benchmark/benchmark-{code,infra,config,security,unknown}.json` fixture path. `005_code_weird_exception.yaml` includes an inline comment noting the historical "unknown" prefix on its fixture filename. Each yaml carries `human_labeled_by: meizhuixu`, `labeled_at: 2026-05-09`, and `ground_truth_notes`. Commit message includes `Scenario-Authored-By: meizhuixu` trailer.
- [ ] T050 [US5] [PR-5] Delete inline `SCENARIOS: list[dict]` from `autosentinel/benchmark.py`; rewrite the runner body to glob `benchmarks/scenarios/*.yaml` via `BenchmarkScenario` loader. Drop `SPRINT4_MOCK_APPROVAL` constant (no longer needed once real CostGuard preserves partial state). FR-516 fulfilled.

### New scenarios (45 total, batched ≤ 5 per task to stay within 2-3 hour budget per task)

> **Authorship gate reminder**: every commit adding scenarios MUST include `Scenario-Authored-By: meizhuixu` trailer. Each yaml's `human_labeled_by` field MUST equal the trailer name. CI gate (T063) enforces this.

- [ ] T051 [P] [US5] [PR-5] Author 5 new CODE scenarios at `benchmarks/scenarios/006_code_*.yaml` … `010_code_*.yaml` (filenames + slugs decided at authoring time; human-curated; one fixture JSON per scenario at `benchmarks/scenarios/fixtures/<id>.json`)
- [ ] T052 [P] [US5] [PR-5] Author 5 more CODE scenarios at `benchmarks/scenarios/011_code_*.yaml` … `015_code_*.yaml` (final CODE batch — 12 total: 2 migrated + 10 new ✓)
- [ ] T053 [P] [US5] [PR-5] Author 5 INFRA scenarios at `benchmarks/scenarios/016_infra_*.yaml` … `020_infra_*.yaml`
- [ ] T054 [P] [US5] [PR-5] Author 5 INFRA scenarios at `benchmarks/scenarios/021_infra_*.yaml` … `025_infra_*.yaml`
- [ ] T055 [P] [US5] [PR-5] Author 4 INFRA scenarios at `benchmarks/scenarios/026_infra_*.yaml` … `029_infra_*.yaml` (final INFRA batch — 15 total: 1 migrated + 14 new ✓)
- [ ] T056 [P] [US5] [PR-5] Author 7 SECURITY scenarios at `benchmarks/scenarios/030_security_*.yaml` … `036_security_*.yaml` (8 total: 1 migrated + 7 new ✓; required for SC-013 false-negative measurement)
- [ ] T057 [P] [US5] [PR-5] Author 5 CONFIG scenarios at `benchmarks/scenarios/037_config_*.yaml` … `041_config_*.yaml`
- [ ] T058 [P] [US5] [PR-5] Author 5 CONFIG scenarios at `benchmarks/scenarios/042_config_*.yaml` … `046_config_*.yaml`
- [ ] T059 [P] [US5] [PR-5] Author 4 CONFIG scenarios at `benchmarks/scenarios/047_config_*.yaml` … `050_config_*.yaml` (final CONFIG batch — 15 total: 1 migrated + 14 new ✓; total 50 ✓)

### Runner + smoke + authorship gate

- [ ] T060 [US5] [PR-5] Implement `scripts/run_benchmark.py`: argparse with `--scenarios <dir>`, `--budget <usd>`, `--use-mock`; reads all yamls; runs each through both v1 and v2 pipelines; writes `benchmarks/results/{YYYYMMDD-HHMMSS-{git_short_sha}}/results.jsonl` (one `BenchmarkResult` per line) + `summary.json` per `contracts/benchmark-scenario.md` "Output schema". `total_cost_usd` is JSON-serialised as `str(Decimal)`.
- [ ] T061 [US5] [PR-5] Implement `tests/benchmark_smoke/test_smoke_benchmark.py`: hard-coded `SMOKE_SCENARIO_IDS = ["001_code_null_user_context", "002_infra_db_connection_refused", "003_config_jwt_secret_missing", "004_security_sql_injection_attempt", "005_code_weird_exception"]` (the 5 migrated scenarios, all categories covered after reclassification); uses `MockLLMClient` with deterministic per-scenario fixture responses; runs in CI; asserts `summary.json` schema compliance + budget never tripped at zero cost.
- [ ] T062 [P] [US5] [PR-5] Add scenario-authorship checkbox section to `.github/pull_request_template.md` per `contracts/benchmark-scenario.md` "Tier 1 — PR template". (Verify file exists in repo first; create if absent.)
- [ ] T063 [US5] [PR-5] Implement `scripts/check_scenario_authorship.py`: `git diff --name-only --diff-filter=A <merge_base>...HEAD`; for each new `benchmarks/scenarios/*.yaml`, run `git log --diff-filter=A -- <path>` and grep the resulting commit message for `Scenario-Authored-By:`; non-zero exit + clear error message naming offending file/commit on miss.
- [ ] T064 [US5] [PR-5] Add `.github/workflows/scenario-authorship.yml` invoking `scripts/check_scenario_authorship.py` on PRs whose paths match `benchmarks/scenarios/**` (workflow `paths:` filter for fast no-op on unrelated PRs).

**Checkpoint**: US5 functional. CI smoke runs on every PR for free; full benchmark runnable manually under budget.

---

## Phase 8: Polish & Cross-Cutting Concerns (PR-5 tail — merged into the same PR per plan.md)

- [ ] T065 [P] [PR-5] Run full test suite + verify 100 % branch coverage on `autosentinel/llm/`: `pytest tests/ --cov=autosentinel.llm --cov-fail-under=100`. Constitution III gate.
- [ ] T066 [PR-5] Run full 50-scenario benchmark **manually** (real LLM cost ~$4-7): `python scripts/run_benchmark.py --scenarios benchmarks/scenarios/ --budget 20.6`. Open `benchmarks/results/{run_id}/summary.json`; assert `v2.latency_ms.p95 ≤ 90000` (SC-008), `v2.resolution_rate ≥ 0.70` (SC-009), `security_subset.v2_false_negative_count == 0` (SC-013, non-negotiable). Attach full summary.json to PR-5 description.
- [ ] T067 [P] [PR-5] Re-run Sprint 4 acceptance scenarios SC-001..SC-005 for non-regression (SC-015): `pytest tests/integration/test_multi_agent_graph.py tests/test_benchmark.py` with `MockLLMClient` injected so no real cost incurred. All Sprint 4 SCs MUST still pass.
- [ ] T068 [PR-5] Run `quickstart.md` end-to-end against a clean checkout: `docker compose up`, `uvicorn autosentinel.api.main:app`, `curl /alerts`, verify `trace_id` lands in Langfuse UI as one parent trace with child spans per LLM-call agent.

---

## Dependencies & Execution Order

### Phase Dependencies

| Phase | Depends on | Blocks |
|---|---|---|
| 1 Setup | (none) | 2, 3-7 |
| 2 Foundational (PR-1) | 1 | 3-7 (all stories) |
| 3 US1 (PR-2 + PR-4 partial) | 2 | T037 (US1 GREEN) is checkpoint for PR-2 ship; T035-T037 share infra with US3+US4 |
| 4 US2 (PR-3) | T030 (DI refactor done) — minimum from Phase 3 | (none for US2; can ship PR-3 once T040 verified) |
| 5 US3 (PR-4 partial) | 2 + T035 (PostgresSaver swap) | (none) |
| 6 US4 (PR-4 partial) | 2 + T035 + T045 (trace_id at ingest) | (none) |
| 7 US5 (PR-5) | 2 + 3 (US1 specialists must be real-LLM-capable for benchmark to mean anything) | Polish |
| 8 Polish (PR-5 tail) | All of 3-7 | (final) |

### Critical paths within US1

```
T025-T028 (failing tests, parallel) ──┐
T029 (failing cross-process test)  ───┤
                                       ▼
T030 (13-site DI refactor — gates everything below)
                                       │
                  ┌────────────────────┼────────────────────┐
                  ▼                    ▼                    ▼
              T031 (Diag)          T032 (CodeFix)       T033 (InfraSRE)   T034 (SecRev)
              (parallel — different files)
                  │
                  ▼
              T025-T028 GREEN ──> PR-2 ready to ship
                  │
                  ▼
              T035 (PostgresSaver swap)
                  │
                  ▼
              T036 (resume endpoint)
                  │
                  ▼
              T037 (T029 GREEN) ──> US1 fully delivered
```

### Critical path within PR-4 (US1 cross-process + US3 + US4 share PostgresSaver swap)

```
T035 (PostgresSaver swap) ──┬──> T036, T037     (US1 cross-process)
                             ├──> T042, T043     (US3 cost_exhausted_node)
                             └──> T046, T047     (US4 trace propagation)

T041 (US3 failing test) before T042-T043
T044 (US4 failing tests) before T045-T047
T029 (US1 failing test) before T035-T037
```

### Parallel Opportunities

- **Setup**: T002, T003, T004, T005 all `[P]` after T001.
- **Foundational tests**: T006-T013 all `[P]` (8 different test files).
- **Foundational impl**: T014→T015 (same file, sequential); T016, T018, T020, T022, T023 each `[P]` once their respective test exists.
- **US1 tests**: T025-T029 all `[P]`.
- **US1 specialist body replacements**: T031-T034 all `[P]` (4 different agent files) once T030 lands.
- **US5 scenario authoring**: T051-T059 all `[P]` (different yaml files; no cross-dependency).
- **Across stories**: once T030 (DI refactor) merges, US2/US3/US4/US5 streams can run in parallel by separate developers if staffed.

---

## Parallel Example: Phase 3 (US1) test-first kickoff

```bash
# After T024 (PR-1 checkpoint) is green, launch all 5 US1 failing tests in parallel:
Task: "Update tests/unit/test_diagnosis_agent.py with MockLLMClient DI"
Task: "Update tests/unit/test_code_fixer_agent.py with MockLLMClient DI"
Task: "Update tests/unit/test_infra_sre_agent.py with MockLLMClient DI"
Task: "Update tests/unit/test_security_reviewer_agent.py (3 setUp methods)"
Task: "Write tests/integration/test_postgres_checkpointer.py (cross-process resume)"

# After T030 lands, parallel agent body replacements:
Task: "Replace DiagnosisAgent.run() with real LLM call"
Task: "Replace CodeFixerAgent.run() with real LLM call"
Task: "Replace InfraSREAgent.run() with real LLM call"
Task: "Replace SecurityReviewerAgent.run() with real LLM call (GLM-4.7)"
```

---

## Implementation Strategy

### MVP scope (US1 only)

1. Phase 1 Setup (T001-T005)
2. Phase 2 Foundational (T006-T024) — **gates everything**
3. Phase 3 US1 PR-2 slice (T025-T028, T030-T034) — real reasoning shipped; cross-process resume deferred
4. **Validate**: real LLM-backed pipeline answers two structurally different incidents differently (acceptance from spec US1)
5. Optionally extend to T029, T035-T037 (PR-4 cross-process resume) if process-restart durability is operationally needed at MVP

### Incremental delivery (recommended)

| PR | Tasks | Acceptance |
|---|---|---|
| **PR-1** | T001-T024 | Foundation green; AST boundary check passes; CostGuard 100% branch coverage |
| **PR-2** | T025-T028, T030-T034 | 4 specialists answer real incidents via injected LLM client; Sprint 4 tests still pass with MockLLMClient |
| **PR-3** | T038-T040 | Routing accuracy ≥ 70 % on held-out 20-incident set |
| **PR-4** | T029, T035-T037, T041-T047 | Cross-process resume works; CostGuard aborts pipeline cleanly; trace_id end-to-end correlated in Langfuse |
| **PR-5** | T048-T068 | 50-scenario benchmark passes SC-008/SC-009/SC-012/SC-013/SC-015; CI smoke green for free |

### Parallel team strategy (if multi-developer)

Once PR-1 ships and T030 lands in PR-2:
- Dev A: PR-3 (US2, lightest scope)
- Dev B: PR-4 (US3 + US4 + US1 cross-process — heaviest)
- Dev C: PR-5 scenario authoring (T051-T059, 9 parallelizable yaml-batch tasks)

---

## Per-PR task counts

| PR | Phases covered | Tasks | Sub-counts |
|---|---|---|---|
| PR-1 | 1, 2 | 24 | Setup (5), Foundational tests (8), Foundational impl (11) |
| PR-2 | 3 (US1, specialist DI) | 9 | Tests (4), 13-site refactor (1), specialist body (4) |
| PR-3 | 4 (US2) | 3 | Test (1), impl (1), verify (1) |
| PR-4 | 3 (US1 cross-process) + 5 (US3) + 6 (US4) | 11 | US1 cross-process (1 test + 3 impl), US3 (1 test + 2 impl), US4 (1 test + 3 impl) |
| PR-5 | 7 (US5) + 8 (Polish) | 21 | Schema/migration (3), scenarios (9), runner/CI (5), Polish (4) |
| **Total** | | **68** | |

---

## Notes

- **Test-First gate**: every implementation task lists "Verify T<test_id> turns GREEN" as its acceptance signal where applicable. Constitution III non-negotiable.
- **13-construction-site refactor (T030)** is intentionally a single discrete task per `plan.md` Phase 2 "Construction-site impact" sub-bullet — it touches 13 separate sites in one atomic change to keep the test suite green throughout PR-2.
- **AST boundary check (T006) lands before any `import openai` (T021)**: T021 inserts the SDK import inside an allowlisted file; T006's allowlist already contains `ark_client.py` and `glm_client.py` from the start, so the test goes green naturally on T021 commit. If T021 forgets to be inside an allowlisted file, the test fails — that's the standard TDD feedback for boundary tests.
- **The checkpointer (T035) is shared infrastructure for US1 cross-process + US3 (cost_exhausted node persists state) + US4 (trace_id round-trip)** — that's why PR-4 is the heaviest PR. (As-built [D1]: not a one-line compile-site swap — it became an injectable, env-gated `build_multi_agent_graph(*, checkpointer=None, ...)` selecting PostgresSaver vs MemorySaver on `AUTOSENTINEL_CHECKPOINTER_DSN`, to avoid an import-time Postgres connection that would break the hermetic suite.)
- **Scenario authoring (T051-T059) is human-only** — `Scenario-Authored-By:` trailer enforced by CI gate T063+T064. No AI-generated drafts.
- **Polish task T066 costs real money** (~$4-7) — manual run, not in CI.
- **Out of scope per spec**: interrupt-timeout policy (deferred to Sprint 6), human-approval UI (separate workstream), parallel agent execution (Sprint 4 deferred), multi-annotator labelling (Sprint 5 single-annotator decision in research.md §10).
