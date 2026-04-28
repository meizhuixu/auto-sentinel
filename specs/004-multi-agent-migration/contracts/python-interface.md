# Python Interface Contracts: Sprint 4 - Multi-Agent Migration

## Abstract: `autosentinel.agents.base.BaseAgent`

```python
from abc import ABC, abstractmethod
from autosentinel.agents.state import AgentState

class BaseAgent(ABC):
    @abstractmethod
    def run(self, state: AgentState) -> AgentState:
        """
        Process the current pipeline state and return updated fields.
        MUST be a pure function of state — no side effects except Docker (Verifier only).
        All mock implementations MUST include:
            # TODO(W2): replace with real LLM call
        """
        ...
```

**Contract invariants**:
- Returns a partial dict (only changed fields); LangGraph merges it
- MUST NOT raise exceptions — all errors captured in state fields
- MUST append `self.__class__.__name__` to `agent_trace` in every return
- MUST NOT import or call `docker` SDK (except `VerifierAgent`)

---

## `autosentinel.agents.state.AgentState`

```python
import operator
from typing import Annotated, Optional
from typing_extensions import TypedDict
from autosentinel.models import AnalysisResult, ErrorLog, ExecutionResult

class AgentState(TypedDict):
    # ── Sprint 1–3 (unchanged) ─────────────────────────────────────────
    log_path:         str
    error_log:        Optional[ErrorLog]
    parse_error:      Optional[str]
    analysis_result:  Optional[AnalysisResult]   # v1 only
    analysis_error:   Optional[str]              # v1 only
    fix_script:       Optional[str]              # v1 only (analyze_error)
    execution_result: Optional[ExecutionResult]
    execution_error:  Optional[str]
    report_text:      Optional[str]
    report_path:      Optional[str]
    # ── Sprint 4 (new) ─────────────────────────────────────────────────
    error_category:   Optional[str]    # CODE | INFRA | CONFIG | SECURITY
    fix_artifact:     Optional[str]    # produced by specialist agent
    security_verdict: Optional[str]    # SAFE | CAUTION | HIGH_RISK
    routing_decision: Optional[str]    # human-readable routing log
    agent_trace:      Annotated[list[str], operator.add]  # parallel-safe
    approval_required: bool
```

---

## Agent Contracts

### `DiagnosisAgent.run(state) -> AgentState`

**Reads**: `state["error_log"]`
**Writes**: `error_category`, `agent_trace`

| Condition | `error_category` |
|-----------|-----------------|
| error_type/message matches connectivity/network/timeout keywords | `"INFRA"` |
| error_type/message matches memory/oom/cpu/resource keywords | `"INFRA"` |
| error_type/message matches config/env/secret/variable keywords | `"CONFIG"` |
| error_type/message matches security/injection/xss/auth keywords | `"SECURITY"` |
| fallback (all others, including `application_logic`) | `"CODE"` |

Mock return:
```python
# TODO(W2): replace with real LLM call
return {"error_category": derived_category, "agent_trace": ["DiagnosisAgent"]}
```

---

### `SupervisorAgent.run(state) -> AgentState` (route phase)

**Reads**: `state["error_category"]`
**Writes**: `routing_decision`

The Supervisor does NOT directly invoke agents — it sets `routing_decision` and LangGraph
conditional edges handle the dispatch. The supervisor node returns:

```python
return {
    "routing_decision": f"{state['error_category']} → {specialist_name}",
    "agent_trace": ["SupervisorAgent"],
}
```

Routing table (see data-model.md): CODE/SECURITY/UNKNOWN → CodeFixerAgent; INFRA/CONFIG → InfraSREAgent.

---

### `CodeFixerAgent.run(state) -> AgentState`

**Reads**: `state["error_log"]`, `state["error_category"]`
**Writes**: `fix_artifact`, `agent_trace`

```python
# TODO(W2): replace with real LLM call
_MOCK_FIXES = {
    "CODE":     'print("Flushing stale state and re-initialising application context...")',
    "SECURITY": 'print("Applying security patch to input validation layer...")',
}
return {
    "fix_artifact": _MOCK_FIXES.get(state["error_category"], _MOCK_FIXES["CODE"]),
    "agent_trace": ["CodeFixerAgent"],
}
```

---

### `InfraSREAgent.run(state) -> AgentState`

**Reads**: `state["error_log"]`, `state["error_category"]`
**Writes**: `fix_artifact`, `agent_trace`

```python
# TODO(W2): replace with real LLM call
_MOCK_FIXES = {
    "INFRA":  'print("Restarting connection pool for upstream dependency...")',
    "CONFIG": 'print("Reloading environment variables from secrets store...")',
}
return {
    "fix_artifact": _MOCK_FIXES.get(state["error_category"], _MOCK_FIXES["INFRA"]),
    "agent_trace": ["InfraSREAgent"],
}
```

---

### `SecurityReviewerAgent.run(state) -> AgentState`

**Reads**: `state["fix_artifact"]`, `state["error_category"]`
**Writes**: `security_verdict`, `agent_trace`

```python
# TODO(W2): replace with real LLM call
_HIGH_RISK_KEYWORDS = [
    "DROP TABLE", "DROP DATABASE", "TRUNCATE TABLE",
    "rm -rf /", "rm -rf ~", "chmod 777", "mkfs", "dd if=",
]

def run(self, state):
    artifact = state.get("fix_artifact") or ""
    verdict = "SAFE"
    if any(kw in artifact for kw in _HIGH_RISK_KEYWORDS):
        verdict = "HIGH_RISK"
    return {"security_verdict": verdict, "agent_trace": ["SecurityReviewerAgent"]}
```

---

### `security_gate` node (not a BaseAgent — LangGraph node function)

**Reads**: `state["security_verdict"]`
**Writes**: `approval_required`; may call `interrupt()`

```python
def security_gate(state: AgentState) -> AgentState:
    verdict = state.get("security_verdict")
    approval_required = (verdict == "HIGH_RISK")
    if approval_required:
        try:
            _logger.info("human_approval_required", extra={"fix_artifact": state.get("fix_artifact")})
        except Exception:
            _logger.exception("Failed to emit human_approval_required event")
        interrupt({"reason": "HIGH_RISK fix requires human approval",
                   "fix_artifact": state.get("fix_artifact")})
    return {"approval_required": approval_required}
```

---

### `VerifierAgent.run(state) -> AgentState`

**Reads**: `state["fix_artifact"]`
**Writes**: `execution_result`, `execution_error`, `agent_trace`

Wraps Sprint 3 `execute_fix` logic exactly. The only difference: reads `fix_artifact`
instead of `fix_script`.

```python
def run(self, state: AgentState) -> AgentState:
    # Delegate to execute_fix logic with fix_artifact as the script
    proxy_state = dict(state)
    proxy_state["fix_script"] = state.get("fix_artifact")
    result = _execute_fix_logic(proxy_state)   # extracted from nodes/execute_fix.py
    return {**result, "agent_trace": ["VerifierAgent"]}
```

**ONLY agent permitted to import `docker`.**

---

## `build_multi_agent_graph()` — Graph Assembly Contract

```python
# autosentinel/multi_agent_graph.py

def build_multi_agent_graph() -> CompiledStateGraph:
    builder = StateGraph(AgentState)

    # Nodes
    builder.add_node("parse_log",              parse_log)
    builder.add_node("diagnosis_agent",        lambda s: diagnosis_agent.run(s))
    builder.add_node("supervisor_route",       lambda s: supervisor_agent.run(s))
    builder.add_node("code_fixer_agent",       lambda s: code_fixer_agent.run(s))
    builder.add_node("infra_sre_agent",        lambda s: infra_sre_agent.run(s))
    builder.add_node("security_reviewer",      lambda s: security_reviewer_agent.run(s))
    builder.add_node("security_gate",          security_gate)
    builder.add_node("verifier_agent",         lambda s: verifier_agent.run(s))
    builder.add_node("format_report",          format_report)

    # Edges
    builder.add_edge(START, "parse_log")
    builder.add_conditional_edges("parse_log", _route_after_parse)   # parse_error? → END
    builder.add_edge("parse_log", "diagnosis_agent")
    builder.add_edge("diagnosis_agent", "supervisor_route")

    # Sequential: route to specialist, then security_reviewer reads fix_artifact
    builder.add_conditional_edges("supervisor_route", _route_to_specialist,
                                  {"code_fixer": "code_fixer_agent",
                                   "infra_sre":  "infra_sre_agent"})
    builder.add_edge("code_fixer_agent", "security_reviewer")   # sequential after specialist
    builder.add_edge("infra_sre_agent",  "security_reviewer")   # sequential after specialist

    builder.add_edge("security_reviewer", "security_gate")
    builder.add_edge("security_gate",     "verifier_agent")
    builder.add_edge("verifier_agent",    "format_report")
    builder.add_edge("format_report",     END)

    return builder.compile(checkpointer=MemorySaver())
```

---

## `run_pipeline()` — Feature-Flag Backwards Compatibility

```python
# autosentinel/__init__.py

import os

def run_pipeline(log_path: str | Path) -> Path:
    use_multi_agent = os.getenv("AUTOSENTINEL_MULTI_AGENT", "0") == "1"
    graph = build_multi_agent_graph() if use_multi_agent else build_graph()
    # ... existing invoke logic unchanged
```

---

## `autosentinel/benchmark.py` — Public Interface

```python
def run_benchmark() -> dict:
    """Returns benchmark report dict written to output/benchmark-report.json."""
    ...

# CLI entry point:
# python -m autosentinel.benchmark
# Output: output/benchmark-report.json with fields:
#   scenario_count, v1_resolution_rate, v2_resolution_rate, v1_avg_ms, v2_avg_ms
```
