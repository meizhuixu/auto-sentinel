# Implementation Plan: Sprint 5 — Real LLM Integration

**Branch**: `005-real-llm-integration` | **Date**: 2026-05-08 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-real-llm-integration/spec.md`

## Summary

Replace the deterministic Sprint 4 mocks on five of the six agents (Diagnosis,
Supervisor, CodeFixer, InfraSRE, SecurityReviewer) with real LLM-backed reasoning
behind a single provider-agnostic abstraction at `autosentinel/llm/`. The Verifier
remains deterministic by design (path (a) decision in spec). Cost is governed by
a singleton `CostGuard` with a hard `$20.6` per-run ceiling (≈ ¥150 at 7.3 ¥/USD);
trace propagation flows from the FastAPI ingest endpoint through `AgentState`
into the existing project-4 `LLMTracer` (sync context manager). Cross-process
interrupt durability is delivered by swapping `MemorySaver` for `PostgresSaver`
on a dedicated `localhost:5433` Postgres container. The Sprint 4 5-scenario
inline benchmark migrates to a yaml-per-file layout under `benchmarks/scenarios/`
and grows to 50 human-labelled scenarios.

The whole stack stays **sync** at and below the agent layer. The async/sync
boundary is the existing `asyncio.Queue` worker between FastAPI ingest and
LangGraph dispatch — async does not push down into agents, the LLM client, or
the LLMTracer (which is itself sync).

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: `langgraph==1.1.9`, `langgraph-checkpoint-postgres`, `psycopg[binary]>=3.1` (sync driver), `openai>=1.40` (only inside `autosentinel/llm/`), `httpx`, `tenacity`, `pydantic>=2`, `pydantic-settings`, `pyyaml`
**External services**: Volcano-Engine Ark (`doubao-1.5-lite-32k`, `doubao-seed-2.0-pro`) and Zhipu BigModel (`glm-4.7`); project-4 `LLMTracer` → Langfuse
**Storage**: PostgreSQL 16 in dedicated container `auto-sentinel-checkpointer` (port `5433`); benchmark scenarios as yaml files under `benchmarks/scenarios/`; existing `data/benchmark/*.json` log fixtures retained and referenced (not copied)
**Testing**: `pytest`, `pytest-cov`, dependency-injected `MockLLMClient` (no `patch.object`)
**Target Platform**: macOS/Linux developer machine + CI (CI runs smoke benchmark with mock client; full 50-scenario run is manual)
**Project Type**: Multi-agent LangGraph pipeline + FastAPI ingest
**Performance Goals**: end-to-end p95 latency ≤ 90 s on 50-scenario run; resolution rate ≥ 70 %; SECURITY-subset false-negative count = 0 (SC-013, non-negotiable)
**Constraints**: per-run LLM budget hard-capped at $20.6 USD (CostGuard); provider SDK imports confined to `autosentinel/llm/` (Constitution VII.1, AST-enforced); no hard-coded model names or endpoint URLs in agent code (VII.4); `trace_id` mandatory on every LLM call (VII.3)
**Scale/Scope**: 5 LLM-backed agents + 1 deterministic Verifier; 50 benchmark scenarios distributed 12 CODE / 15 INFRA / 8 SECURITY / 15 CONFIG; single-process pipeline today (Redis/cross-process state out of scope per FR-513)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. AI Agent Sandboxing | **SATISFIED** | Verifier remains sole Docker importer; LLM API calls execute in host process (Principle I LLM-execution boundary, v2.2.0). No new module added to Docker import allowlist. |
| II. Self-Healing First (MTTR) | **SATISFIED** | Real reasoning + 50-scenario benchmark produce operationally-meaningful MTTR triplets (latency / cost / resolution rate) for the first time. |
| III. Test-First (NON-NEGOTIABLE) | **GATE** | All new modules (`llm/*`, `cost_guard`, `model_routing`, scenario loader, AST boundary check) ship with failing tests committed before implementation; `MockLLMClient` injection keeps unit suite hermetic. |
| IV. Observability | **SATISFIED** | `trace_id` generated at FastAPI ingest, threaded through `AgentState`, forwarded to `LLMTracer` at every LLM call; project/component tags applied per-agent. |
| V. LLM Reasoning Reliability | **GATE** | SecurityReviewer maintains coverage / interrupt-obligation / auditability invariants; SC-013 strict false-negative = 0 verified on SECURITY subset. Closes `TODO(SPRINT5_KEYWORD_REMOVAL)`. |
| VI. Multi-Agent Governance | **SATISFIED** | Inter-agent flow remains LangGraph state-channel-only; agent `run()` signature unchanged (sync, returns `AgentState`). LLM client is injected into agent constructors, not exposed as a public agent method. |
| VII. LLM Provider Boundary & Cost | **GATE** | VII.1 AST CI check `tests/unit/test_llm_provider_isolation.py`; VII.2 `CostGuard` is the only path to provider SDK; VII.3 trace propagation contract tested end-to-end; VII.4 model assignment in `config/model_routing.yaml`, no agent-side string literals. |

No deviations to record under Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/005-real-llm-integration/
├── plan.md              ← this file
├── spec.md
├── research.md          ← 10 decisions (Decision / Rationale / Alternatives / Consequences)
├── data-model.md        ← 9 Pydantic v2 schemas + AgentState extension + CostGuardError
├── quickstart.md
└── contracts/
    ├── llm-client.md
    ├── cost-guard.md
    ├── trace-propagation.md
    └── benchmark-scenario.md
```

### Source Code Changes

```text
autosentinel/
├── llm/                                  ← NEW: provider isolation boundary (Constitution VII.1)
│   ├── __init__.py
│   ├── protocol.py                       ← LLMClient Protocol, Message, LLMRequest, LLMResponse
│   ├── ark_client.py                     ← ArkLLMClient (OpenAI SDK + Ark base_url)
│   ├── glm_client.py                     ← GlmLLMClient (OpenAI SDK + Zhipu base_url)
│   ├── mock_client.py                    ← MockLLMClient (DI for tests + smoke benchmark)
│   ├── factory.py                        ← build_client_for_agent() reads model_routing.yaml
│   ├── cost_guard.py                     ← CostGuard singleton + threading.Lock + CostGuardError
│   └── errors.py                         ← LLMTimeoutError / LLMProviderError / ConfigurationError
├── models.py                             ← UPDATE: extend AgentState TypedDict (Sprint 5 section)
├── multi_agent_graph.py                  ← UPDATE: MemorySaver → PostgresSaver one-liner; add cost_exhausted_node
├── api/
│   └── main.py                           ← UPDATE: trace_id generation at ingest + /incidents/{id}/resume
├── agents/                               ← UPDATE: each agent __init__ takes llm_client: LLMClient
│   ├── diagnosis.py                      ← UPDATE: real LLM via injected client
│   ├── supervisor.py                     ← UPDATE: real LLM routing
│   ├── code_fixer.py                     ← UPDATE: real LLM
│   ├── infra_sre.py                      ← UPDATE: real LLM
│   ├── security_reviewer.py              ← UPDATE: real LLM (GLM-4.7), keep keyword path as defense-in-depth optional
│   └── verifier.py                       ← UNCHANGED: deterministic, no LLM (path (a) decision)
└── benchmark.py                          ← UPDATE: drop inline SCENARIOS, add BenchmarkScenario/BenchmarkResult Pydantic, change runner to read yamls (multi-purpose file in PR-5)

config/
└── model_routing.yaml                    ← NEW: per-agent model + per-endpoint base_url + api_key_env

infra/
└── docker-compose.checkpointer.yml       ← NEW: postgres:16 on localhost:5433

benchmarks/
├── scenarios/                            ← NEW: yaml-per-file (50 files: 001-050)
│   ├── 001_*.yaml … 005_*.yaml           ← migrated from autosentinel/benchmark.py SCENARIOS[0..4]
│   │                                       (full slug list in contracts/benchmark-scenario.md "Migration map")
│   └── 006_*.yaml … 050_*.yaml           ← 45 new human-labelled scenarios
└── results/{run_id}/                     ← NEW: results.jsonl + summary.json (run_id = YYYYMMDD-HHMMSS-{git_short_sha})

scripts/
├── run_benchmark.py                      ← NEW: CLI runner for full 50-scenario benchmark
└── check_scenario_authorship.py          ← NEW: CI gate enforcing Scenario-Authored-By trailer

tests/
├── unit/
│   ├── test_llm_provider_isolation.py    ← NEW: AST CI check (mirrors test_docker_import_boundary.py pattern)
│   ├── test_llm_protocol.py              ← NEW: LLMClient Protocol contract tests
│   ├── test_ark_client.py                ← NEW
│   ├── test_glm_client.py                ← NEW
│   ├── test_mock_client.py               ← NEW
│   ├── test_cost_guard.py                ← NEW: 3 cases — over-threshold, reset_for_test, threading.Lock
│   ├── test_model_routing.py             ← NEW: pydantic-settings validation (missing model / endpoint / env)
│   ├── test_no_hardcoded_models.py       ← NEW: agent files must not contain "doubao-" / "glm-" / "ark.cn-beijing"
│   └── test_*_agent.py                   ← UPDATE: inject MockLLMClient via DI (no patch.object)
├── integration/
│   ├── test_trace_propagation.py         ← NEW: 3 cases — end-to-end consistency, LLMTracer rejects empty trace_id, state-serialization round-trip
│   ├── test_cost_guard_pipeline.py       ← NEW: typed CostGuardError aborts pipeline before Verifier
│   ├── test_postgres_checkpointer.py     ← NEW: cross-process interrupt resume (process A → process B)
│   └── test_multi_agent_graph.py         ← UPDATE: SC-015 non-regression
├── benchmark_smoke/                      ← NEW: CI smoke subset, MockLLMClient, 5 scenarios
│   └── test_smoke_benchmark.py
└── conftest.py                           ← UPDATE: AgentState gains trace_id + cost_accumulated_usd; CostGuard reset_for_test fixture

.github/
└── pull_request_template.md              ← UPDATE: scenario-authored-by checkbox
```

**Structure Decision**: New `autosentinel/llm/` package is the **single legal location** for provider SDK imports. Every agent receives an `LLMClient` instance via constructor injection (no module-level imports of `openai` from agent files). The `MemorySaver` → `PostgresSaver` swap is intentionally a one-line change at the compile site (`multi_agent_graph.py:80`); persistence-layer concerns are confined to that one line + the dedicated compose file. Scenario yamls reference the existing `data/benchmark/*.json` log fixtures by path — no fixture content is copied.

## Key Design Decisions

The six blocks below are the load-bearing design decisions for Sprint 5. Each is
fixed; alternatives evaluated are recorded in `research.md`.

### Block 1 — LLM Client Architecture

**Class layout** (`autosentinel/llm/`):

| File | Type | Purpose |
|---|---|---|
| `protocol.py` | `LLMClient(Protocol)` | Provider-agnostic surface; defines `complete(...)` |
| `ark_client.py` | `ArkLLMClient(LLMClient)` | OpenAI SDK pointed at `https://ark.cn-beijing.volces.com/api/v3` (doubao series) |
| `glm_client.py` | `GlmLLMClient(LLMClient)` | OpenAI SDK pointed at `https://open.bigmodel.cn/api/paas/v4` (glm-4.7) |
| `mock_client.py` | `MockLLMClient(LLMClient)` | Test double; `with_fixture_response(resp)` / `with_error(exc)` / `call_count` |
| `factory.py` | function | `build_client_for_agent(agent_name) -> LLMClient` reads `config/model_routing.yaml` and returns the bound client + agent-specific config |

**Sync `complete()` signature** (final, not subject to plan-level revision):

```python
def complete(
    self,
    *,
    messages: list[Message],
    model: str,
    trace_id: str,
    agent_name: str,
    max_tokens: int,
    temperature: float,
) -> LLMResponse: ...
```

**Resilience** (hard-coded values, not configurable):

- `tenacity.retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=8))`
- `httpx.Timeout(30.0)`

**AST boundary check**: `tests/unit/test_llm_provider_isolation.py` mirrors
Sprint 4's `test_docker_import_boundary.py` pattern. It walks every `*.py`
under `autosentinel/`, fails if any file outside `autosentinel/llm/` contains
`import openai` or `from openai`. Allowlist is hard-coded inside the test, not
configurable.

**Mock substitution path**: **dependency injection only**. Each agent
`__init__(..., llm_client: LLMClient)` accepts the client; tests pass
`MockLLMClient`. The `unittest.mock.patch.object(CodeFixerAgent, ...)` block in
`autosentinel/benchmark.py` (Sprint 4 mock-approve technical debt) is removed
in the same PR that wires real LLMs.

### Block 2 — CostGuard

**File**: `autosentinel/llm/cost_guard.py`. **State**: module-level singleton +
`threading.Lock` (sync stack, no `asyncio.Lock` needed).

| Aspect | Decision |
|---|---|
| Trigger point | **After** `complete()` returns: accumulate using actual `LLMResponse.cost_usd` (Ark + GLM both return token usage; we trust the provider over a pre-call estimate). |
| Threshold semantics | `if current_total + new_call.cost_usd > BUDGET_LIMIT_USD: raise CostGuardError` — strict `>`, no buffer. The successful response is still returned to the caller; the **next** outbound call is what trips the guard. |
| Budget value | `BUDGET_LIMIT_USD = 20.6` (≈ ¥150 @ 7.3 ¥/USD), sourced from env var `AUTOSENTINEL_BUDGET_LIMIT_USD` with this as default. |
| Granularity | Global (single accumulator). **No per-agent quota** — over-engineered for a 5-LLM-agent pipeline. |
| Persistence | **In-process only.** Restarts clear the counter. Documented as deliberate trade-off: Sprint 5 is single-process; Redis/Postgres CostGuard state would be over-engineering. Benchmark runner is a single-process batch — no cross-process budget view needed. |
| Error path | `CostGuardError` raised from inside agent `run()` → LangGraph routes to `cost_exhausted_node` → END. `state.cost_accumulated_usd` and any partial `fix_artifact` are persisted; `agent_trace` appends `"cost_guard_triggered"`. **The user's partial fix is NOT lost mid-pipeline.** |
| Test reset | `reset_for_test()` is callable **only** when `os.environ.get("PYTEST_CURRENT_TEST")` is set; otherwise raises `RuntimeError`. |

### Block 3 — Trace Propagation

**Single generation point**: FastAPI `ingest_alert` endpoint
(`autosentinel/api/main.py:39`) generates the `trace_id` via
`secrets.token_hex(16)` (32-char lowercase hex, regex `^[0-9a-f]{32}$` —
matches the project-4 `LLMTracer` validator at `tracer.py:51`).

**Propagation chain** (sync below the queue):

```text
POST /alerts (async)
  └→ ingest_alert: trace_id = secrets.token_hex(16)
        └→ asyncio.Queue (alert dict carries trace_id)
              └→ async worker dequeues
                    └→ sync dispatch into LangGraph (state["trace_id"] set here)
                          └→ each agent.run() reads state["trace_id"]
                                └→ LLMClient.complete(trace_id=..., agent_name=...)
                                      └→ LLMTracer(trace_id=..., project="auto-sentinel",
                                                   component=agent_name, model=...)
                                              ├→ raises ValueError if trace_id missing/malformed
                                              └→ ships SpanRecord on __exit__
```

A Mermaid sequence diagram covering the same chain lives in
`contracts/trace-propagation.md`.

**Agent boundary contract**: dropping or regenerating `trace_id` between
agents is a Constitution VII.3 violation. Verified by:

- `test_trace_id_end_to_end_consistency` — same `trace_id` observed on 5 distinct LLM calls of one incident.
- `test_llmtracer_rejects_missing_trace_id` — `LLMClient.complete(trace_id="")` causes the underlying `LLMTracer(trace_id="")` constructor to raise `ValueError`; client surfaces it.
- `test_state_serialization_preserves_trace_id` — round-trip through PostgresSaver checkpoint preserves the field.

### Block 4 — Declarative Model Routing

**Configuration file**: `config/model_routing.yaml` (yaml chosen over `.env` —
per-agent fields are too many for env vars to remain readable).

**API keys never live in the file** — only env-var **names**. Loader uses
`pydantic-settings`; on startup, missing keys / unregistered models / unset
env vars cause **fail-fast** startup.

```yaml
agents:
  diagnosis:
    model: doubao-seed-2.0-pro
    temperature: 0.2
    max_tokens: 2048
  supervisor:
    model: doubao-1.5-lite-32k
    temperature: 0.0
    max_tokens: 512
  code_fixer:
    model: doubao-seed-2.0-pro
    temperature: 0.3
    max_tokens: 4096
  infra_sre:
    model: doubao-seed-2.0-pro
    temperature: 0.3
    max_tokens: 4096
  security_reviewer:
    model: glm-4.7
    temperature: 0.0
    max_tokens: 2048
  # verifier deliberately absent — deterministic, no LLM.

endpoints:
  ark:
    base_url: https://ark.cn-beijing.volces.com/api/v3
    api_key_env: ARK_API_KEY
    models: [doubao-1.5-lite-32k, doubao-seed-2.0-pro]
  glm:
    base_url: https://open.bigmodel.cn/api/paas/v4
    api_key_env: GLM_API_KEY
    models: [glm-4.7]
```

**Anti-hardcoding test** (`tests/unit/test_no_hardcoded_models.py`): grep all
files under `autosentinel/agents/` for the substrings `doubao-`, `glm-`,
`ark.cn-beijing`, `open.bigmodel.cn`; any hit is a Constitution VII.4 violation.

### Block 5 — PostgresSaver Deployment

| Aspect | Decision |
|---|---|
| Library | `langgraph.checkpoint.postgres.PostgresSaver` (LangGraph official). No bespoke wrapper. |
| Driver | `psycopg[binary]` v3 sync API (matches the sync stack). |
| Container | `postgres:16` named `auto-sentinel-checkpointer`, port `localhost:5433` (5432 reserved for project-4 Langfuse Postgres — avoiding collision). |
| Compose file | `infra/docker-compose.checkpointer.yml` (separate file, not merged into a root compose, for clean service-boundary semantics). |
| Credentials (Sprint 5) | hard-coded `postgres / postgres` for local dev. **Marked as Phase 4 / AWS technical debt to be replaced with Secrets Manager**. |
| Schema setup | `PostgresSaver.setup()` is idempotent; called at startup. |
| Compile-site change | Single line at `autosentinel/multi_agent_graph.py:80`: `MemorySaver()` → `PostgresSaver.from_conn_string(...)`. |
| Resume API | `POST /incidents/{incident_id}/resume` body `{"decision": "approve"\|"reject", "reviewer_notes": "..."}`. Internally: `graph.invoke(Command(resume={"decision": ..., "notes": ...}), config={"configurable": {"thread_id": incident_id}})`. |
| Interrupt timeout | **Not implemented in Sprint 5** (spec Out-of-Scope, deferred to Sprint 6+). |

### Block 6 — Benchmark Format & Execution

| Aspect | Decision |
|---|---|
| Storage | `benchmarks/scenarios/<NNN>_<category>_<short_slug>.yaml` — **one file per scenario**, 50 total. |
| Distribution | 12 CODE / 15 INFRA / 8 SECURITY / 15 CONFIG (spec FR-516). |
| Migration of existing 5 | files `001_*.yaml` … `005_*.yaml` are direct migrations of `autosentinel/benchmark.py` `SCENARIOS[0..4]`. yaml `error_log_path` field references existing `data/benchmark/benchmark-{code,config,infra,security,unknown}.json` fixtures — content is **not** copied. |
| Inline SCENARIOS removal | Same PR that introduces yamls deletes the inline `SCENARIOS: list[dict]` from `autosentinel/benchmark.py` — fulfils FR-516 "MUST live in a structured data file, not inline in benchmark runner code". |
| Schema | `BenchmarkScenario` Pydantic v2 model (see `data-model.md`). |
| Runner | `scripts/run_benchmark.py --scenarios <dir> --budget <usd> --use-mock`. |
| CI smoke vs full | **CI runs smoke only** — `pytest tests/benchmark_smoke/` runs the 5 migrated scenarios (`001_*` through `005_*`, which after s05 reclassification cover all 4 categories: 2 CODE + 1 INFRA + 1 CONFIG + 1 SECURITY) using `MockLLMClient`, costs $0. Full 50-scenario run is manual: `python scripts/run_benchmark.py …`, costs ~$4-7 per run. Single source of truth for smoke composition is `contracts/benchmark-scenario.md`. |
| Output | `benchmarks/results/{run_id}/results.jsonl` + `summary.json`; `run_id = YYYYMMDD-HHMMSS-{git_short_sha}`. |
| Summary fields | per-category latency p50/p95, total cost USD, resolution rate, **SECURITY false-negative count** (SC-013 verification). |
| Anti-AI-authoring gate (3-tier) | (1) PR template checkbox `[ ] All new benchmark scenarios were human-authored before commit`; (2) commit adding scenarios MUST include `Scenario-Authored-By: <human>` trailer in message; (3) `scripts/check_scenario_authorship.py` runs in CI on PR diffs touching `benchmarks/scenarios/*.yaml`, fails the build if the trailer is absent. |

## Implementation Phases

### Phase 1 — LLM Client Foundation (PR-1, blocking prerequisite)

- Create `autosentinel/llm/` package skeleton with `LLMClient` Protocol, `Message` / `LLMRequest` / `LLMResponse` schemas, `errors.py`, `MockLLMClient`.
- Implement `CostGuard` singleton + `CostGuardError`.
- Implement `factory.build_client_for_agent()` reading `config/model_routing.yaml` via `pydantic-settings`.
- Implement `ArkLLMClient`, `GlmLLMClient` (real provider clients).
- Test-First: `test_llm_provider_isolation.py` (AST), `test_no_hardcoded_models.py`, `test_llm_protocol.py`, `test_cost_guard.py`, `test_model_routing.py`. All MUST be committed failing before any implementation in this phase.

### Phase 2 — Wire Real LLMs into Specialist Agents (PR-2, US1 P1)

- Update `DiagnosisAgent`, `CodeFixerAgent`, `InfraSREAgent`, `SecurityReviewerAgent` constructors to accept `llm_client: LLMClient`.
- Replace `# TODO(W2)` mock bodies with real LLM calls via injected client.
- Extend `AgentState` TypedDict in `autosentinel/models.py` (Sprint 5 section: `trace_id`, `cost_accumulated_usd`).
- Remove `unittest.mock.patch.object(CodeFixerAgent, ...)` from `autosentinel/benchmark.py`.
- Test-First: each `test_*_agent.py` updated to inject `MockLLMClient`.

**Construction-site impact** (audit of all bare `AgentClass()` calls in the
codebase as of 2026-05-08; PR-2 must update all of them in lockstep with the
constructor signature change):

| File:line | Current call | PR-2 change |
|---|---|---|
| `autosentinel/multi_agent_graph.py:21` | `_diagnosis_agent = DiagnosisAgent()` | `DiagnosisAgent(llm_client=build_client_for_agent("diagnosis"))` |
| `autosentinel/multi_agent_graph.py:22` | `_supervisor_agent = SupervisorAgent()` | `SupervisorAgent(llm_client=build_client_for_agent("supervisor"))` |
| `autosentinel/multi_agent_graph.py:23` | `_code_fixer_agent = CodeFixerAgent()` | `CodeFixerAgent(llm_client=build_client_for_agent("code_fixer"))` |
| `autosentinel/multi_agent_graph.py:24` | `_infra_sre_agent = InfraSREAgent()` | `InfraSREAgent(llm_client=build_client_for_agent("infra_sre"))` |
| `autosentinel/multi_agent_graph.py:25` | `_security_reviewer_agent = SecurityReviewerAgent()` | `SecurityReviewerAgent(llm_client=build_client_for_agent("security_reviewer"))` |
| `tests/unit/test_diagnosis_agent.py:38` | `self.agent = DiagnosisAgent()` | `self.agent = DiagnosisAgent(llm_client=MockLLMClient())` |
| `tests/unit/test_supervisor_agent.py:32` | `self.agent = SupervisorAgent()` | `self.agent = SupervisorAgent(llm_client=MockLLMClient())` |
| `tests/unit/test_code_fixer_agent.py:34` | `self.agent = CodeFixerAgent()` | `self.agent = CodeFixerAgent(llm_client=MockLLMClient())` |
| `tests/unit/test_infra_sre_agent.py:34` | `self.agent = InfraSREAgent()` | `self.agent = InfraSREAgent(llm_client=MockLLMClient())` |
| `tests/unit/test_security_reviewer_agent.py:34` | `self.agent = SecurityReviewerAgent()` (setUp #1) | `self.agent = SecurityReviewerAgent(llm_client=MockLLMClient())` |
| `tests/unit/test_security_reviewer_agent.py:55` | `self.agent = SecurityReviewerAgent()` (setUp #2) | same |
| `tests/unit/test_security_reviewer_agent.py:80` | `self.agent = SecurityReviewerAgent()` (setUp #3) | same |
| `autosentinel/benchmark.py:28, 33, 168-175` | `from unittest.mock import patch` + `from autosentinel.agents.code_fixer import CodeFixerAgent` + `patch.object(CodeFixerAgent, "_get_fix_for_security", return_value="DROP TABLE users")` block scoped to `s04` | Delete the imports + the `patch_ctx`/`patch.object` block. Real GLM-4.7 SecurityReviewer produces HIGH_RISK on the SQL-injection scenario from semantic reasoning, not from a string-injection workaround. (Also closes the Sprint 4 `# Sprint 5 cleanup:` TODO at the top of `benchmark.py`.) |

**Total impacted call sites**: 13 (5 production + 7 test + 1 benchmark patch
block). All updates land in the same PR-2 commit so the test suite stays
green; no backward-compat default is added (a `llm_client = None` default
would silently let a forgetting caller construct an agent that crashes on the
first `complete()` call — a required keyword arg fails fast at construction).
The `BaseAgent` ABC at `autosentinel/agents/base.py:10` does **not** need a
constructor change — it's an interface for `run()`, not for `__init__`.
**`VerifierAgent`** is **not** in this list — Verifier remains deterministic
(Decision 3) and its constructor stays unchanged.

### Phase 3 — Routing Intelligence (PR-3, US2 P1)

- Update `SupervisorAgent.run()` to use real LLM for routing.
- Add `routing_decision` rationale capture (already in `AgentState` from Sprint 4).
- Verify: held-out routing test set ≥ 70 % accuracy.

### Phase 4 — Trace Propagation + PostgresSaver (PR-4, US3 P1 + US4 P2)

- Generate `trace_id` in `autosentinel/api/main.py` ingest endpoint.
- Thread `trace_id` through asyncio.Queue payload and into `AgentState` at LangGraph dispatch.
- Add `infra/docker-compose.checkpointer.yml`.
- Swap `MemorySaver()` → `PostgresSaver.from_conn_string(...)` at `multi_agent_graph.py:80`.
- Add `cost_exhausted_node` and wire it as the abort target for `CostGuardError`.
- Add `POST /incidents/{incident_id}/resume` endpoint.
- Test-First: `test_trace_propagation.py` (3 cases), `test_cost_guard_pipeline.py`, `test_postgres_checkpointer.py` (cross-process resume).

**Note on US4 priority labelling**: spec.md labels US4 as P2 because the
*observable user benefit* (one-parent-many-children trace tree visible in
Langfuse UI) is a developer-experience improvement, not a runtime SLO.
However, the *underlying trace_id threading work in this phase* is P1
because: (i) US3's `cost_exhausted_node` persists state through
PostgresSaver, which round-trips trace_id through JSON serialization;
(ii) US1's cross-process resume replays AgentState from PostgresSaver, so
trace_id must be a state field before resume can ship; (iii) Constitution
VII.3 forbids dropping trace_id between agents — this is a hard gate, not
optional. Conclusion: the trace_id threading task (T045/T046) ships in
PR-4 alongside US3/US1 work and is non-deferrable, even though the
Langfuse-UI-visible benefit is appropriately tagged P2.

### Phase 5 — Benchmark Migration + Extension (PR-5, US5 P2)

- Migrate Sprint 4 `SCENARIOS[0..4]` to `benchmarks/scenarios/001_*.yaml` … `005_*.yaml`.
- Author 45 new scenarios distributed as: 10 CODE additions
  (12 target − 2 migrated: s01 + reclassified s05), 14 INFRA
  (15 − 1: s02), 7 SECURITY (8 − 1: s04), 14 CONFIG (15 − 1: s03).
  Total reconciles: 5 migrated + 45 new = 50.
- Each yaml carries `human_labeled_by: meizhuixu` + `labeled_at: YYYY-MM-DD` + `ground_truth_notes`.
- Implement `scripts/run_benchmark.py` (yaml loader → results.jsonl + summary.json).
- Implement `scripts/check_scenario_authorship.py` + CI workflow + PR template update.
- Delete inline `SCENARIOS` from `autosentinel/benchmark.py`; runner now reads yaml dir.

### Phase 6 — Polish & Coverage Gate

- Run full suite; confirm 100 % branch coverage on new modules.
- Verify SC-013 `false_negative_count == 0` on SECURITY subset by manual full-50 run.
- Re-run Sprint 4 SC-001 … SC-005 (SC-015 non-regression).

## Complexity Tracking

| Item | Why it's not a violation |
|---|---|
| In-process CostGuard state | Sprint 5 is explicitly single-process; cross-process budget view is YAGNI. Documented in plan + `cost-guard.md` contract. Re-evaluate when multi-worker rollout begins. |
| Hard-coded `postgres / postgres` credentials in compose file | Local-dev-only. Plan + research.md flag this as Phase 4 (AWS) technical debt to be replaced with Secrets Manager during cloud rollout. |
| Single human labeller (meizhuixu) for 50 scenarios | FR-517 forbids AI-generates-and-AI-verifies; it does **not** require multi-annotator agreement. Single-annotator flow is sufficient for the operational decision SC-012 supports. Inter-annotator agreement is queued for Sprint 6+ if external publication is pursued. |

No constitution violations. The `cost_exhausted_node` END path is intentional —
it preserves the user's partial fix on budget exhaustion, so the typed
`CostGuardError` does not regress operability.

## Phase 2 (Tasks) — Out of scope for this command

`tasks.md` is generated by `/speckit.tasks` after this plan is reviewed. The
intended PR sequence is **PR-1 (LLM Client foundation) → PR-2 (4 specialist
agents) → PR-3 (Supervisor) → PR-4 (PostgresSaver + trace + CostGuard wiring)
→ PR-5 (50 scenarios)**.
