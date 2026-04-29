"""Tests for SupervisorAgent — routing table and routing_decision format."""

import pytest

from autosentinel.agents.supervisor import SupervisorAgent
from autosentinel.models import AgentState


def _make_state(error_category: str) -> AgentState:
    return AgentState(
        log_path="dummy.json",
        error_log=None,
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
        fix_script=None,
        execution_result=None,
        execution_error=None,
        report_text=None,
        report_path=None,
        error_category=error_category,
        fix_artifact=None,
        security_verdict=None,
        routing_decision=None,
        agent_trace=[],
        approval_required=False,
    )


class TestSupervisorRouting:
    def setup_method(self):
        self.agent = SupervisorAgent()

    def test_code_routes_to_code_fixer(self):
        result = self.agent.run(_make_state("CODE"))
        assert "code_fixer" in result["routing_decision"].lower() or "CodeFixer" in result["routing_decision"]

    def test_security_routes_to_code_fixer(self):
        result = self.agent.run(_make_state("SECURITY"))
        assert "CodeFixer" in result["routing_decision"]

    def test_infra_routes_to_infra_sre(self):
        result = self.agent.run(_make_state("INFRA"))
        assert "InfraSRE" in result["routing_decision"]

    def test_config_routes_to_infra_sre(self):
        result = self.agent.run(_make_state("CONFIG"))
        assert "InfraSRE" in result["routing_decision"]

    def test_unknown_fallback_routes_to_code_fixer(self):
        result = self.agent.run(_make_state("UNKNOWN"))
        assert "CodeFixer" in result["routing_decision"]

    def test_none_category_fallback_routes_to_code_fixer(self):
        result = self.agent.run(_make_state(None))
        assert "CodeFixer" in result["routing_decision"]

    def test_routing_decision_contains_category(self):
        result = self.agent.run(_make_state("INFRA"))
        assert "INFRA" in result["routing_decision"]

    def test_routing_decision_format(self):
        result = self.agent.run(_make_state("CODE"))
        assert "→" in result["routing_decision"] or "->" in result["routing_decision"]

    def test_appends_supervisor_to_agent_trace(self):
        result = self.agent.run(_make_state("CODE"))
        assert result["agent_trace"] == ["SupervisorAgent"]

    def test_returns_only_routing_fields(self):
        result = self.agent.run(_make_state("CODE"))
        assert set(result.keys()) == {"routing_decision", "agent_trace"}

    def test_get_specialist_key_code(self):
        assert self.agent.get_specialist_key("CODE") == "code_fixer"

    def test_get_specialist_key_security(self):
        assert self.agent.get_specialist_key("SECURITY") == "code_fixer"

    def test_get_specialist_key_infra(self):
        assert self.agent.get_specialist_key("INFRA") == "infra_sre"

    def test_get_specialist_key_config(self):
        assert self.agent.get_specialist_key("CONFIG") == "infra_sre"

    def test_get_specialist_key_unknown_fallback(self):
        assert self.agent.get_specialist_key("UNKNOWN") == "code_fixer"
