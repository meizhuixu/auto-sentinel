# Data Model: Sprint 5 — Real LLM Integration

All schemas are **Pydantic v2** unless noted. `AgentState` is the existing
LangGraph `TypedDict` — Sprint 5 **extends** it in place rather than replacing
it. `CostGuardError` is a typed exception, not a Pydantic schema, but its
attribute surface is documented at the end.

File mapping:

| Schema | File | Status |
|---|---|---|
| `Message` | `autosentinel/llm/protocol.py` | NEW |
| `LLMRequest` | `autosentinel/llm/protocol.py` | NEW |
| `LLMResponse` | `autosentinel/llm/protocol.py` | NEW |
| `AgentModelConfig` | `autosentinel/llm/factory.py` | NEW |
| `EndpointConfig` | `autosentinel/llm/factory.py` | NEW |
| `ModelRoutingConfig` | `autosentinel/llm/factory.py` | NEW |
| `CostGuardState` | `autosentinel/llm/cost_guard.py` | NEW |
| `AgentState` | `autosentinel/models.py` | **EXTEND IN PLACE** (do not create a new file) |
| `BenchmarkScenario` / `BenchmarkResult` | `autosentinel/benchmark.py` (top of file, alongside the rewritten yaml runner — PR-5 reshapes this file to carry both schemas and runner; no new file added) | NEW |
| `CostGuardError` | `autosentinel/llm/errors.py` | NEW (exception, not Pydantic) |

---

## 1. `Message`

```python
from typing import Literal
from pydantic import BaseModel

class Message(BaseModel):
    model_config = {"frozen": True}

    role: Literal["system", "user", "assistant"]
    content: str
```

**Fields**:
- `role`: chat-completion role; only system / user / assistant in Sprint 5
  (no tool-call / function-call surface yet).
- `content`: prompt or response text. Empty string is allowed (downstream
  truncation behaviour).

**Invariants**:
- Frozen — agents constructing messages cannot mutate them after handoff to
  the LLM client.

---

## 2. `LLMRequest`

```python
import re
from pydantic import BaseModel, Field, field_validator

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")

class LLMRequest(BaseModel):
    model_config = {"frozen": True}

    messages: list[Message] = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=32_768)
    trace_id: str
    agent_name: str = Field(min_length=1)

    @field_validator("trace_id")
    @classmethod
    def _trace_id_shape(cls, v: str) -> str:
        if not _TRACE_ID_RE.fullmatch(v):
            raise ValueError(f"trace_id must be 32 lowercase hex chars; got {v!r}")
        return v
```

**Fields**:
- `messages`: at least one message; system-prompt convention is the first.
- `model`: must match a model declared under some endpoint in `model_routing.yaml` (cross-validated by `ModelRoutingConfig`, not by `LLMRequest` alone).
- `temperature`: 0.0 – 2.0 (OpenAI SDK range).
- `max_tokens`: 1 – 32_768; per-agent value comes from `AgentModelConfig`.
- `trace_id`: 32-char lowercase hex (matches project-4 LLMTracer regex).
- `agent_name`: free-text, used as the `component` tag on the LLMTracer span.

**Invariants**:
- `trace_id` regex enforced — empty string fails (closes the
  `test_llmtracer_rejects_missing_trace_id` boundary).
- Frozen.

---

## 3. `LLMResponse`

```python
from decimal import Decimal
from pydantic import BaseModel, Field, model_validator

class LLMResponse(BaseModel):
    model_config = {"frozen": True}

    content: str
    model: str = Field(min_length=1)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    latency_ms: int = Field(ge=0)
    trace_id: str

    @model_validator(mode="after")
    def _trace_id_matches_request(self) -> "LLMResponse":
        # The client copies trace_id from request → response unchanged;
        # this is a guard against a future bug, not a runtime branch.
        if not _TRACE_ID_RE.fullmatch(self.trace_id):
            raise ValueError("LLMResponse trace_id malformed")
        return self
```

**Fields**:
- `content`: model-generated text (free-form; agent code parses with structured-output schemas downstream — Constitution V).
- `prompt_tokens` / `completion_tokens`: from provider response; both `≥ 0`.
- `cost_usd`: `Decimal` (financial precision; no `float`); computed by the client from `LLMTracer.set_cost_breakdown()` inputs or via the response's reported usage.
- `latency_ms`: client-side wall-clock, recorded inside the `LLMTracer` context.
- `trace_id`: copied from the corresponding `LLMRequest` unchanged.

**Invariants**:
- All numeric fields `≥ 0`.
- `cost_usd` is `Decimal`, not `float` — propagated to `CostGuardState.total_spent_usd` for accurate summation.

---

## 4. `AgentModelConfig`

```python
class AgentModelConfig(BaseModel):
    model: str
    temperature: float = Field(ge=0.0, le=2.0)
    max_tokens: int = Field(ge=1, le=32_768)
    endpoint_alias: str  # Resolved at config load time (set by ModelRoutingConfig)
```

**Fields** & **Invariants**: per-agent reflection of `model_routing.yaml`'s
`agents.<name>` block. `endpoint_alias` is **not** in the yaml — it is computed
at load time by walking `endpoints.*.models` and finding which alias contains
this agent's model. Models that appear in zero endpoints raise a
`ConfigurationError` at startup.

---

## 5. `EndpointConfig`

```python
from pydantic import HttpUrl

class EndpointConfig(BaseModel):
    base_url: HttpUrl
    api_key_env: str = Field(min_length=1)  # name of env var holding the API key
    models: list[str] = Field(min_length=1)
```

**Invariants**:
- `models` non-empty.
- `api_key_env` is the env-var **name**; the API key value is **never** stored
  in this object (Constitution VII.4 spirit + general secrets hygiene).

---

## 6. `ModelRoutingConfig`

```python
class ModelRoutingConfig(BaseModel):
    agents: dict[str, AgentModelConfig]
    endpoints: dict[str, EndpointConfig]

    @model_validator(mode="after")
    def _every_agent_model_is_registered(self) -> "ModelRoutingConfig":
        all_models: dict[str, str] = {}  # model_name → endpoint_alias
        for alias, ep in self.endpoints.items():
            for m in ep.models:
                if m in all_models:
                    raise ValueError(f"model {m!r} declared under multiple endpoints")
                all_models[m] = alias
        for agent_name, cfg in self.agents.items():
            if cfg.model not in all_models:
                raise ValueError(
                    f"agent {agent_name!r} uses model {cfg.model!r} not declared under any endpoint"
                )
            cfg.endpoint_alias = all_models[cfg.model]  # back-fill
        return self
```

**Invariants**:
- Each agent's `model` exists in exactly one endpoint's `models` list.
- API-key env vars are checked by `factory.py` at startup (separate from this
  validator, since `os.environ` is process state, not config state).

---

## 7. `CostGuardState`

```python
from datetime import datetime

class CostGuardState(BaseModel):
    total_spent_usd: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    budget_limit_usd: Decimal = Field(ge=Decimal("0"))
    call_count: int = Field(default=0, ge=0)
    last_updated: datetime | None = None
```

**Fields**:
- `total_spent_usd`: cumulative sum of `LLMResponse.cost_usd` since process start (or last `reset_for_test()`).
- `budget_limit_usd`: from `AUTOSENTINEL_BUDGET_LIMIT_USD` env var, default `20.6`.
- `call_count`: integer counter for telemetry.
- `last_updated`: `datetime` of the most recent successful accumulation.

**Invariants**:
- Both `Decimal` fields `≥ 0`.
- Only mutated under `threading.Lock` inside `CostGuard`.

---

## 8. `AgentState` — Sprint 5 extension (in `autosentinel/models.py`)

**This is an extension**, not a new schema. The existing `TypedDict` at
`autosentinel/models.py:45` keeps Sprint 1-3 and Sprint 4 sections unchanged;
Sprint 5 adds a third section. `autosentinel/agents/state.py` (the re-export
shim) is **not** modified.

```python
# autosentinel/models.py — append-only
from typing import Annotated, Optional
from typing_extensions import NotRequired, TypedDict
import operator

class AgentState(TypedDict):
    # ── Sprint 1–3 (unchanged) ──────────────────────────────────────────
    log_path: str
    error_log: Optional["ErrorLog"]
    parse_error: Optional[str]
    analysis_result: Optional["AnalysisResult"]
    analysis_error: Optional[str]
    fix_script: Optional[str]
    execution_result: Optional["ExecutionResult"]
    execution_error: Optional[str]
    report_text: Optional[str]
    report_path: Optional[str]
    # ── Sprint 4 (unchanged) ────────────────────────────────────────────
    error_category: Optional[str]
    fix_artifact: Optional[str]
    security_verdict: Optional[str]
    routing_decision: Optional[str]
    agent_trace: Annotated[list[str], operator.add]
    approval_required: bool
    # ── Sprint 5 (new) ──────────────────────────────────────────────────
    trace_id: NotRequired[str]                  # 32-char lowercase hex; set at FastAPI ingest
    cost_accumulated_usd: NotRequired[float]    # mirror of CostGuardState for in-state visibility
    security_classifier_model: NotRequired[str] # GLM model identity used by SecurityReviewer; NotRequired for backward compat with Sprint 4 state literals
```

**Why `NotRequired`**: existing tests construct `AgentState` literals without
these fields; making them required would break Sprint 4's regression suite.
LangGraph reads `state.get("trace_id", "")` defensively in the dispatch path.

**Field semantics**:
- `trace_id`: stamped once by the LangGraph dispatch layer when consuming a
  message off the asyncio.Queue. Agents read this and pass to
  `LLMClient.complete(trace_id=...)`. Mutating it mid-pipeline is a
  Constitution VII.3 violation (covered by the trace-propagation contract test).
- `cost_accumulated_usd`: snapshot of `CostGuard.total_spent_usd` after each
  agent's run; used by the eventual `cost_exhausted_node` to write the abort
  reason into `state` for the user-facing report.
- `security_classifier_model`: model name (e.g. `'glm-4.7'`) of the LLM that
  produced the security verdict; recorded for trace correlation and benchmark
  eval. Mirrors the `model_routing.yaml` value at the time of the run.
  Written by `SecurityReviewerAgent.run()` after a successful `complete()` call.

**Why `float`, not `Decimal`**: LangGraph's TypedDict serialisation through
PostgresSaver round-trips JSON; `Decimal` requires a custom serialiser.
Precision loss across one or two pipeline runs is < $0.000001 — irrelevant
versus the $20.6 budget. `CostGuardState.total_spent_usd` (the source of
truth) remains `Decimal`.

---

## 9. `BenchmarkScenario` & `BenchmarkResult`

```python
from datetime import date
from pathlib import Path
from typing import Literal

class BenchmarkScenario(BaseModel):
    model_config = {"frozen": True}

    scenario_id: str = Field(pattern=r"^\d{3}_[a-z]+_[a-z0-9_]+$")  # e.g. 001_code_null_pointer
    category: Literal["CODE", "INFRA", "SECURITY", "CONFIG"]
    error_log_path: Path
    expected_classification: str        # ground-truth error_category
    expected_resolution_action: str     # short prose label
    ground_truth_notes: str             # free-form rationale
    human_labeled_by: str = Field(min_length=1)
    labeled_at: date

class BenchmarkResult(BaseModel):
    model_config = {"frozen": True}

    scenario_id: str
    actual_classification: str
    actual_resolution: str
    passed: bool
    latency_ms: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=Decimal("0"))
    trace_id: str
    error: Optional[str] = None         # populated if pipeline raised before Verifier
```

**Invariants**:
- `BenchmarkScenario.scenario_id` regex pins file naming convention.
- `BenchmarkScenario.error_log_path` exists on disk (validated by the runner at load time, not by Pydantic — Pydantic v2 doesn't natively check filesystem state).
- `BenchmarkScenario.human_labeled_by` non-empty — combined with the
  `Scenario-Authored-By` commit trailer enforced in CI, this is the audit
  trail FR-517 demands.
- `BenchmarkResult.trace_id` matches the per-scenario incident `trace_id`
  recorded in `AgentState`.

---

## 10. `CostGuardError` (typed exception, not a Pydantic schema)

```python
# autosentinel/llm/errors.py
from decimal import Decimal

class CostGuardError(Exception):
    def __init__(
        self,
        *,
        current_spent_usd: Decimal,
        attempted_amount_usd: Decimal,
        budget_limit_usd: Decimal,
    ) -> None:
        self.current_spent_usd = current_spent_usd
        self.attempted_amount_usd = attempted_amount_usd
        self.budget_limit_usd = budget_limit_usd
        super().__init__(
            f"CostGuard tripped: spent={current_spent_usd}USD + "
            f"attempted={attempted_amount_usd}USD > budget={budget_limit_usd}USD"
        )
```

**Attributes**:
- `current_spent_usd`: cumulative spend at the moment the guard tripped.
- `attempted_amount_usd`: the cost of the call that *would have* pushed us over.
- `budget_limit_usd`: the configured ceiling.

**Propagation**: raised inside `LLMClient.complete()` post-accumulation. The
LangGraph node executing the agent re-raises; the graph routes to
`cost_exhausted_node` which sets `state["agent_trace"] += ["cost_guard_triggered"]`,
sets `state["cost_accumulated_usd"] = float(current_spent_usd)`, and ends.
**`unittest.TestCase.assertRaises` is NOT how this is tested** — `pytest.raises`
+ DI'd `MockLLMClient` are.

Sibling exception types in `errors.py` (referenced by `contracts/llm-client.md`
but not detailed here): `LLMTimeoutError`, `LLMProviderError`,
`ConfigurationError`. None carry per-attribute payload beyond a message
string in Sprint 5.
