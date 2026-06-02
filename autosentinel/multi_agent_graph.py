"""build_multi_agent_graph() — Sprint 4 v2 multi-agent LangGraph pipeline.

Sprint 5 PR-4 adds, all via keyword-only params on build_multi_agent_graph:
  * D1 — env-gated, injectable checkpointer (PostgresSaver vs MemorySaver),
  * D2 — a test-only `agents=` injection seam (no production-factory change),
  * T042/T043 — a `cost_exhausted_node` reached by intercepting CostGuardError
    raised inside any LLM-call agent, aborting the pipeline cleanly to END.
"""

import atexit
import logging
import os
import secrets
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from autosentinel.agents.code_fixer import CodeFixerAgent
from autosentinel.agents.diagnosis import DiagnosisAgent
from autosentinel.agents.infra_sre import InfraSREAgent
from autosentinel.agents.security_reviewer import SecurityReviewerAgent
from autosentinel.agents.supervisor import SupervisorAgent
from autosentinel.agents.verifier import VerifierAgent
from autosentinel.llm.cost_guard import get_cost_guard
from autosentinel.llm.errors import CostGuardError
from autosentinel.llm.factory import build_client_for_agent
from autosentinel.models import AgentState
from autosentinel.nodes.format_report import format_report
from autosentinel.nodes.parse_log import parse_log

_logger = logging.getLogger(__name__)

# Per-DSN PostgresSaver cache. The env-gated path opens ONE connection per DSN
# and reuses it across build_multi_agent_graph() calls (the resume endpoint
# builds a graph per request — without this it would leak a PG connection each
# time). The context manager is held open for the process lifetime since the
# saver's connection must outlive each build() call.
# TECHNICAL DEBT — Phase 4 (AWS): the local-dev DSN uses postgres/postgres;
# replace with Secrets Manager-issued credentials before any non-laptop deploy.
_postgres_savers: dict = {}
_open_checkpointer_cms: list = []


@atexit.register
def _close_open_checkpointers() -> None:
    """Close any process-lifetime PostgresSaver connections before interpreter
    shutdown, so psycopg doesn't emit a rollback-on-GC error during teardown."""
    while _open_checkpointer_cms:
        cm = _open_checkpointer_cms.pop()
        try:
            cm.__exit__(None, None, None)
        except Exception:
            pass
    _postgres_savers.clear()

_COST_EXHAUSTED_NODE = "cost_exhausted"

_diagnosis_client, _diagnosis_config = build_client_for_agent("diagnosis")
_diagnosis_agent = DiagnosisAgent(
    llm_client=_diagnosis_client, model_config=_diagnosis_config
)

_supervisor_client, _supervisor_config = build_client_for_agent("supervisor")
_supervisor_agent = SupervisorAgent(
    llm_client=_supervisor_client, model_config=_supervisor_config
)

_code_fixer_client, _code_fixer_config = build_client_for_agent("code_fixer")
_code_fixer_agent = CodeFixerAgent(
    llm_client=_code_fixer_client, model_config=_code_fixer_config
)

_infra_sre_client, _infra_sre_config = build_client_for_agent("infra_sre")
_infra_sre_agent = InfraSREAgent(
    llm_client=_infra_sre_client, model_config=_infra_sre_config
)

_security_reviewer_client, _security_reviewer_config = build_client_for_agent(
    "security_reviewer"
)
_security_reviewer_agent = SecurityReviewerAgent(
    llm_client=_security_reviewer_client, model_config=_security_reviewer_config
)

_verifier_agent = VerifierAgent()


def _route_after_parse(state: AgentState) -> str:
    return END if state.get("parse_error") else "diagnosis_agent"


def cost_exhausted_node(state: AgentState) -> AgentState:
    """Terminal node reached when an LLM-call agent trips the CostGuard (T042).

    Mirrors the Decimal source-of-truth spend into the JSON-friendly float
    AgentState field and stamps the trace so the report and tests can see the
    pipeline aborted on budget rather than completing.
    """
    total = float(get_cost_guard().state.total_spent)
    return {
        "cost_accumulated": total,
        "agent_trace": ["cost_guard_triggered"],
    }


def _guarded(agent, node_name: str):
    """Wrap an LLM-call agent's node so a CostGuardError raised mid-run is
    caught and recorded as state["cost_exhausted"]=True (T043). The post-node
    conditional edge then routes to cost_exhausted_node instead of the normal
    successor. Non-budget exceptions propagate unchanged.

    Deterministic state-flag routing is used in preference to Command(goto=...)
    because a runtime goto does not replace a node's static outgoing edge — the
    pipeline would fan out to BOTH targets.
    """

    def _node(state: AgentState):
        try:
            return agent.run(state)
        except CostGuardError:
            _logger.info("cost_guard_triggered", extra={"node": node_name})
            return {"cost_exhausted": True}

    return _node


def _or_cost_exhausted(next_node: str):
    """Conditional-edge router: divert to cost_exhausted_node when the guard
    tripped, else continue to `next_node`."""

    def _route(state: AgentState) -> str:
        return _COST_EXHAUSTED_NODE if state.get("cost_exhausted") else next_node

    return _route


def _resolve_checkpointer(checkpointer):
    """D1 — env-gated checkpointer selection when none is injected.

    AUTOSENTINEL_CHECKPOINTER_DSN set  → PostgresSaver (cross-process durable),
    unset                              → MemorySaver (hermetic, zero-dependency).
    An explicitly injected checkpointer (tests, T029) always wins.
    """
    if checkpointer is not None:
        return checkpointer

    dsn = os.environ.get("AUTOSENTINEL_CHECKPOINTER_DSN")
    if not dsn:
        return MemorySaver()

    if dsn in _postgres_savers:
        return _postgres_savers[dsn]

    # Imported lazily so the module loads (and the hermetic suite collects)
    # without langgraph-checkpoint-postgres being importable / a live container.
    from langgraph.checkpoint.postgres import PostgresSaver

    cm = PostgresSaver.from_conn_string(dsn)
    saver = cm.__enter__()
    saver.setup()
    _open_checkpointer_cms.append(cm)  # keep the connection alive process-wide
    _postgres_savers[dsn] = saver
    return saver


def dispatch(state: AgentState) -> AgentState:
    """Boundary 3 — LangGraph dispatch (per contracts/trace-propagation.md).

    Ensures every state entering the multi-agent pipeline carries a valid
    32-char lowercase hex trace_id. Future PR-4 will move this generation
    upstream to FastAPI ingest_alert (boundary 1); this node then becomes
    a defensive pass-through (only seeds when upstream omitted).
    """
    if not state.get("trace_id"):
        return {"trace_id": secrets.token_hex(16)}
    return {}


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


def build_multi_agent_graph(
    *,
    checkpointer=None,
    agents: Optional[dict] = None,
) -> StateGraph:
    """Compile the v2 multi-agent pipeline.

    Keyword-only params (Sprint 5 PR-4):
      checkpointer — explicit checkpointer instance; when None, selected by
                     AUTOSENTINEL_CHECKPOINTER_DSN (D1, see _resolve_checkpointer).
      agents       — test-only injection seam (D2): dict with keys diagnosis,
                     supervisor, code_fixer, infra_sre, security_reviewer,
                     verifier. When None, the module-level production singletons
                     (built from build_client_for_agent) are used unchanged.
    """
    agents = agents or {
        "diagnosis": _diagnosis_agent,
        "supervisor": _supervisor_agent,
        "code_fixer": _code_fixer_agent,
        "infra_sre": _infra_sre_agent,
        "security_reviewer": _security_reviewer_agent,
        "verifier": _verifier_agent,
    }
    supervisor = agents["supervisor"]

    def _route_to_specialist(state: AgentState) -> str:
        if state.get("cost_exhausted"):
            return _COST_EXHAUSTED_NODE
        return (
            state.get("specialist")
            or supervisor.get_specialist_key(state.get("error_category"))
        )

    builder = StateGraph(AgentState)

    builder.add_node("dispatch",           dispatch)
    builder.add_node("parse_log",          parse_log)
    builder.add_node("diagnosis_agent",    _guarded(agents["diagnosis"], "diagnosis_agent"))
    builder.add_node("supervisor_route",   _guarded(supervisor, "supervisor_route"))
    builder.add_node("code_fixer_agent",   _guarded(agents["code_fixer"], "code_fixer_agent"))
    builder.add_node("infra_sre_agent",    _guarded(agents["infra_sre"], "infra_sre_agent"))
    builder.add_node("security_reviewer",  _guarded(agents["security_reviewer"], "security_reviewer"))
    builder.add_node("security_gate",      security_gate)
    builder.add_node("verifier_agent",     lambda s: agents["verifier"].run(s))
    builder.add_node("format_report",      format_report)
    builder.add_node(_COST_EXHAUSTED_NODE, cost_exhausted_node)

    builder.add_edge(START, "dispatch")
    builder.add_edge("dispatch", "parse_log")
    builder.add_conditional_edges("parse_log", _route_after_parse,
                                  {END: END, "diagnosis_agent": "diagnosis_agent"})

    # Every LLM-call node's outgoing edge is cost-aware: when the _guarded
    # wrapper tripped (state["cost_exhausted"]), divert to cost_exhausted_node;
    # otherwise continue to the normal successor (T042/T043).
    builder.add_conditional_edges("diagnosis_agent", _or_cost_exhausted("supervisor_route"),
                                  {_COST_EXHAUSTED_NODE: _COST_EXHAUSTED_NODE,
                                   "supervisor_route": "supervisor_route"})
    builder.add_conditional_edges("supervisor_route", _route_to_specialist,
                                  {_COST_EXHAUSTED_NODE: _COST_EXHAUSTED_NODE,
                                   "code_fixer": "code_fixer_agent",
                                   "infra_sre":  "infra_sre_agent"})
    builder.add_conditional_edges("code_fixer_agent", _or_cost_exhausted("security_reviewer"),
                                  {_COST_EXHAUSTED_NODE: _COST_EXHAUSTED_NODE,
                                   "security_reviewer": "security_reviewer"})
    builder.add_conditional_edges("infra_sre_agent", _or_cost_exhausted("security_reviewer"),
                                  {_COST_EXHAUSTED_NODE: _COST_EXHAUSTED_NODE,
                                   "security_reviewer": "security_reviewer"})
    builder.add_conditional_edges("security_reviewer", _or_cost_exhausted("security_gate"),
                                  {_COST_EXHAUSTED_NODE: _COST_EXHAUSTED_NODE,
                                   "security_gate": "security_gate"})

    builder.add_edge("security_gate",     "verifier_agent")
    builder.add_edge("verifier_agent",    "format_report")
    builder.add_edge("format_report",     END)

    # Budget-abort target: an LLM-call node diverts here on CostGuardError;
    # from here the pipeline ends cleanly.
    builder.add_edge(_COST_EXHAUSTED_NODE, END)

    return builder.compile(checkpointer=_resolve_checkpointer(checkpointer))
