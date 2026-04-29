# Research: Sprint 4 - Multi-Agent Migration

## Decision 1: LangGraph Fan-Out for Parallel Execution

**Decision**: Use multiple `add_edge` calls from the same source node for static fan-out. Fields written by parallel branches MUST use `Annotated[list, operator.add]` as a reducer; fields written by exactly one branch need no reducer.

**Verified in LangGraph 1.1.9** (installed version):

```python
# Confirmed working pattern:
class AgentState(TypedDict):
    fix_artifact:    Optional[str]          # written by one branch only → no reducer
    security_verdict: Optional[str]         # written by one branch only → no reducer
    agent_trace: Annotated[list[str], operator.add]  # written by both → reducer required

builder.add_edge("supervisor", "code_fixer")
builder.add_edge("supervisor", "security_reviewer")   # fan-out
builder.add_edge("code_fixer", "supervisor_merge")
builder.add_edge("security_reviewer", "supervisor_merge")  # fan-in
```

**Critical constraint**: In fan-out, both parallel nodes receive the **same state snapshot** — Security Reviewer cannot see Code Fixer's `fix_artifact` during the parallel step. In Sprint 4 mock mode, Security Reviewer runs keyword check on `state["fix_script"]` (already set by `analyze_error`) rather than `fix_artifact`. In Sprint 5, Security Reviewer will be sequential after Code Fixer.

**Fan-out compile error if no reducer**: `InvalidUpdateError: At key 'X': Can receive only one value per step` — confirmed by test. Solution: only use `Annotated` on fields that multiple parallel branches write.

**Alternatives considered**:
- LangGraph `Send` API: More flexible for dynamic fan-out but overkill for a static 2-branch parallel step. Reserved for Sprint 5.
- Separate async tasks: Would require `asyncio.to_thread` coordination outside LangGraph, breaking the state-channel-only rule (Constitution VI).

---

## Decision 2: LangGraph interrupt() + Command(resume=) Pattern

**Decision**: Use `interrupt(value)` inside the Security Reviewer node (or a dedicated gate node) to suspend the pipeline on HIGH_RISK verdicts. Resume via `graph.invoke(Command(resume="approved"), config)`. Requires a checkpointer (MemorySaver in dev/test).

**Verified in LangGraph 1.1.9**:

```python
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import MemorySaver

def security_gate_node(state):
    if state["security_verdict"] == "HIGH_RISK":
        interrupt({"reason": "HIGH_RISK fix requires human approval"})
    return {}   # continues normally for SAFE / CAUTION

# In tests — simulate human approval:
cfg = {"configurable": {"thread_id": "test-1"}}
result1 = graph.invoke(state, cfg)           # suspends, returns __interrupt__
result2 = graph.invoke(Command(resume="approved"), cfg)  # resumes
```

**Graph must be compiled with checkpointer for interrupt to work**:
```python
graph = builder.compile(checkpointer=MemorySaver())
```

**Alternatives considered**:
- Conditional edge routing to a dead-end node: Cannot resume — pipeline is terminated, not suspended.
- External signal / event: Out of scope for Sprint 4 (no UI layer).

---

## Decision 3: BaseAgent Interface — TypedDict over Pydantic V2

**Decision**: Use `TypedDict` for `AgentState`, consistent with the existing codebase pattern. Define `BaseAgent` as an ABC with `@abstractmethod run(state: AgentState) -> AgentState`. This satisfies the Constitution VI clause "TypedDict compatible with LangGraph's state channel reducer."

**Rationale**: The existing `DiagnosticState` is a TypedDict; switching to Pydantic V2 would require rewriting all Sprint 1–3 nodes and conftest fixtures. TypedDict with `Annotated` reducers is LangGraph's idiomatic state pattern. Pydantic V2 support in LangGraph exists but adds `model_validate` / `model_dump` overhead at every node boundary.

**BaseAgent definition**:
```python
from abc import ABC, abstractmethod
class BaseAgent(ABC):
    @abstractmethod
    def run(self, state: AgentState) -> AgentState: ...
```

Each LangGraph node is a thin wrapper: `lambda state: agent.run(state)`.

**Alternatives considered**:
- Pydantic V2 BaseModel for AgentState: Constitution-compliant but requires full state-layer migration. Deferred to Sprint 5 if needed.
- Dataclass: Not compatible with LangGraph state channels.

---

## Decision 4: CI Docker Import Check — AST-Based pytest Test

**Decision**: Implement the SC-004 import check as a pytest test using Python's stdlib `ast` module. No new dependencies required. The check walks all `.py` files under `autosentinel/`, asserts that `import docker` / `from docker` appears only in `autosentinel/agents/verifier.py` (or `autosentinel/agents/verifier/__init__.py`).

**Rationale**: Neither `ruff` nor `import-linter` is installed. Adding `import-linter` as a dev dependency is an option but introduces maintenance overhead for a check that stdlib `ast` can perform in < 20 lines. The pytest approach is immediately runnable in CI without config changes.

**Implementation sketch**:
```python
# tests/test_docker_import_boundary.py
import ast
from pathlib import Path

ALLOWED = {"autosentinel/agents/verifier.py",
           "autosentinel/agents/verifier/__init__.py"}

def _imports_docker(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "docker" or a.name.startswith("docker.") for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "docker" or node.module.startswith("docker.")):
                return True
    return False

def test_only_verifier_imports_docker():
    root = Path("autosentinel")
    violations = [
        str(p.relative_to(Path(".")))
        for p in root.rglob("*.py")
        if _imports_docker(p) and str(p.relative_to(Path("."))) not in ALLOWED
    ]
    assert violations == [], f"Forbidden docker imports in: {violations}"
```

**Alternatives considered**:
- `import-linter` (pip install): More declarative, but adds a new dev dependency and requires `.importlinter` config. Upgrade path documented as TODO in `pyproject.toml`.
- `ruff` custom rule: Requires ruff installation + plugin authoring. Over-engineered for one check.
- `grep`: Explicitly prohibited by Constitution I (grep cannot distinguish `import docker` from a comment or string).

---

## Decision 5: Three Spec Consistency Issues — Resolved

### 5a. "Config Agent" Routing — No ConfigAgent in Agent List

**Issue**: US1 scenario 3 says "Config Agent path" but the 6-agent list has no ConfigAgent.

**Resolution**: `CONFIG` category errors route to `InfraSREAgent`. Configuration issues (environment variables, secrets, deployment manifests) are infrastructure-adjacent and handled by the same agent that handles OOM/CPU/connectivity. The Supervisor's routing table:

| `error_category` | Specialist Agent |
|-----------------|-----------------|
| `CODE` | CodeFixerAgent |
| `INFRA` | InfraSREAgent |
| `CONFIG` | InfraSREAgent |
| `SECURITY` | CodeFixerAgent (security bugs in code) |
| `UNKNOWN` / fallback | CodeFixerAgent |

US1 scenario 3 wording in spec refers to "the Config path" meaning the CONFIG routing branch, not a separate ConfigAgent class. Clarified in data-model.md routing table.

### 5b. application_logic → CODE Category Mapping

**Issue**: Sprint 1–3 uses `error_category` values `connectivity / resource_exhaustion / configuration / application_logic`. Sprint 4 DiagnosisAgent outputs `CODE / INFRA / SECURITY / CONFIG`. These must align.

**Resolution**: DiagnosisAgent mock uses the existing `_mock_classify()` logic as a helper but re-maps its output:

| Old category (`AnalysisResult`) | New category (`AgentState.error_category`) |
|--------------------------------|-------------------------------------------|
| `connectivity` | `INFRA` |
| `resource_exhaustion` | `INFRA` |
| `configuration` | `CONFIG` |
| `application_logic` | `CODE` |

The v1 pipeline (`analyze_error` node) is unchanged. DiagnosisAgent is a new node that calls the same keyword-matching helper and applies this mapping. `fix_script` (Sprint 3) is produced by `analyze_error` for v1 compatibility; `fix_artifact` (Sprint 4) is produced by specialist agents.

### 5c. caution_flag Field — Redundant, Removed

**Issue**: US2 scenario 3 says "a `caution_flag` field is set in the report" for CAUTION verdicts. `AgentState` already has `security_verdict: str` which holds "CAUTION". A separate boolean is redundant.

**Resolution**: Remove `caution_flag` entirely from AgentState and data-model. The `format_report` node reads `security_verdict` and includes a "⚠ CAUTION" badge in the report section when `security_verdict == "CAUTION"`. No additional field needed.

---

## Decision 6: Multi-Agent Graph Architecture

**Graph topology** (with fan-out confirmed working):

```
START
  │
  ▼
diagnosis_agent           ← classifies into CODE/INFRA/CONFIG/SECURITY
  │
  ▼
supervisor_route          ← conditional edges to specialist
  │
  ├──► code_fixer_agent   ─────────────────┐  fan-out (parallel)
  │                                        │
  ├──► infra_sre_agent    ─────────────────┤  (only one specialist fires per run)
  │                                        │
  └──► security_reviewer_agent  ───────────┘  (always fires in parallel with specialist)
                                          │
                                          ▼
                                  supervisor_merge   ← collects fix_artifact + security_verdict
                                          │
                                  [security_verdict == HIGH_RISK?]
                                     YES ↓         NO ↓
                               security_gate    verifier_agent
                           (interrupt() +           │
                            log event)              │
                                   │ resume         │
                                   └────────────────┘
                                          │
                                    format_report
                                          │
                                         END
```

**Node responsibilities**:
- `diagnosis_agent`: reads `error_log` → writes `error_category`
- `supervisor_route`: reads `error_category` → conditional edges to specialist + security_reviewer
- `code_fixer_agent`: reads `error_log + error_category` → writes `fix_artifact`, appends to `agent_trace`
- `infra_sre_agent`: reads `error_log + error_category` → writes `fix_artifact`, appends to `agent_trace`
- `security_reviewer_agent`: reads `error_log + fix_script + error_category` → writes `security_verdict`, appends to `agent_trace`
- `supervisor_merge`: reads `fix_artifact + security_verdict` → writes `routing_decision`
- `security_gate`: if HIGH_RISK → logs + `interrupt()`, else pass-through
- `verifier_agent`: wraps Sprint 3 `execute_fix` logic → writes `execution_result`, `execution_error`
- `format_report`: unchanged from Sprint 3 + adds security verdict section

---

## Decision 7: run_pipeline() Backwards Compatibility

**Decision**: `run_pipeline()` in `autosentinel/__init__.py` MUST remain unchanged in signature. Internally, it calls `build_graph()` which is replaced by `build_multi_agent_graph()`. A feature flag (`AUTOSENTINEL_MULTI_AGENT=1` env var) switches between v1 and v2 graphs during the Sprint 4 transition period, enabling the v1 vs v2 benchmark.

**Rationale**: FR-009 requires the FastAPI gateway and asyncio.Queue to remain unchanged. The benchmark module needs to invoke both graphs. A feature flag is the cleanest way to provide this without duplicating `run_pipeline`.

---

## Decision 8: New Dependencies

| Package | Version | Purpose | Action |
|---------|---------|---------|--------|
| `langgraph` | 1.1.9 (installed) | `interrupt()`, `Command`, fan-out | Already installed |
| `langgraph-checkpoint` | bundled | `MemorySaver` for interrupt tests | Already installed |

No new packages needed.
