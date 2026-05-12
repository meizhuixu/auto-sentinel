"""build_multi_agent_graph() — Sprint 4 v2 multi-agent LangGraph pipeline."""

import logging

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from autosentinel.agents.code_fixer import CodeFixerAgent
from autosentinel.agents.diagnosis import DiagnosisAgent
from autosentinel.agents.infra_sre import InfraSREAgent
from autosentinel.agents.security_reviewer import SecurityReviewerAgent
from autosentinel.agents.supervisor import SupervisorAgent
from autosentinel.agents.verifier import VerifierAgent
from autosentinel.llm.factory import build_client_for_agent
from autosentinel.models import AgentState
from autosentinel.nodes.format_report import format_report
from autosentinel.nodes.parse_log import parse_log

_logger = logging.getLogger(__name__)

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


def _route_to_specialist(state: AgentState) -> str:
    return _supervisor_agent.get_specialist_key(state.get("error_category"))


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


def build_multi_agent_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("parse_log",          parse_log)
    builder.add_node("diagnosis_agent",    lambda s: _diagnosis_agent.run(s))
    builder.add_node("supervisor_route",   lambda s: _supervisor_agent.run(s))
    builder.add_node("code_fixer_agent",   lambda s: _code_fixer_agent.run(s))
    builder.add_node("infra_sre_agent",    lambda s: _infra_sre_agent.run(s))
    builder.add_node("security_reviewer",  lambda s: _security_reviewer_agent.run(s))
    builder.add_node("security_gate",      security_gate)
    builder.add_node("verifier_agent",     lambda s: _verifier_agent.run(s))
    builder.add_node("format_report",      format_report)

    builder.add_edge(START, "parse_log")
    builder.add_conditional_edges("parse_log", _route_after_parse,
                                  {END: END, "diagnosis_agent": "diagnosis_agent"})
    builder.add_edge("diagnosis_agent",   "supervisor_route")
    builder.add_conditional_edges("supervisor_route", _route_to_specialist,
                                  {"code_fixer": "code_fixer_agent",
                                   "infra_sre":  "infra_sre_agent"})

    # Sequential: specialist → security_reviewer (reads fix_artifact)
    builder.add_edge("code_fixer_agent",  "security_reviewer")
    builder.add_edge("infra_sre_agent",   "security_reviewer")

    builder.add_edge("security_reviewer", "security_gate")
    builder.add_edge("security_gate",     "verifier_agent")
    builder.add_edge("verifier_agent",    "format_report")
    builder.add_edge("format_report",     END)

    return builder.compile(checkpointer=MemorySaver())
