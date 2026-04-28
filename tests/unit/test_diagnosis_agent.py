"""Tests for DiagnosisAgent — keyword routing to CODE/INFRA/CONFIG/SECURITY."""

import pytest

from autosentinel.agents.diagnosis import DiagnosisAgent
from autosentinel.models import AgentState


def _make_state(error_type: str, message: str) -> AgentState:
    return AgentState(
        log_path="dummy.json",
        error_log={
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "svc",
            "error_type": error_type,
            "message": message,
            "stack_trace": None,
        },
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
        fix_script=None,
        execution_result=None,
        execution_error=None,
        report_text=None,
        report_path=None,
        error_category=None,
        fix_artifact=None,
        security_verdict=None,
        routing_decision=None,
        agent_trace=[],
        approval_required=False,
    )


class TestDiagnosisAgentRouting:
    def setup_method(self):
        self.agent = DiagnosisAgent()

    def test_connectivity_maps_to_infra(self):
        state = _make_state("ConnectionTimeout", "connection refused")
        result = self.agent.run(state)
        assert result["error_category"] == "INFRA"

    def test_network_maps_to_infra(self):
        state = _make_state("NetworkError", "unreachable host")
        result = self.agent.run(state)
        assert result["error_category"] == "INFRA"

    def test_oom_maps_to_infra(self):
        state = _make_state("OOMKilled", "memory limit exceeded")
        result = self.agent.run(state)
        assert result["error_category"] == "INFRA"

    def test_cpu_maps_to_infra(self):
        state = _make_state("ResourceError", "cpu throttling detected")
        result = self.agent.run(state)
        assert result["error_category"] == "INFRA"

    def test_config_maps_to_config(self):
        state = _make_state("ConfigurationError", "environment variable not set")
        result = self.agent.run(state)
        assert result["error_category"] == "CONFIG"

    def test_secret_maps_to_config(self):
        state = _make_state("StartupError", "secret JWT_KEY is missing")
        result = self.agent.run(state)
        assert result["error_category"] == "CONFIG"

    def test_security_maps_to_security(self):
        state = _make_state("SecurityException", "sql injection attempt detected")
        result = self.agent.run(state)
        assert result["error_category"] == "SECURITY"

    def test_auth_maps_to_security(self):
        state = _make_state("AuthError", "authentication failed")
        result = self.agent.run(state)
        assert result["error_category"] == "SECURITY"

    def test_application_logic_maps_to_code(self):
        state = _make_state("UnhandledError", "unexpected None in user context")
        result = self.agent.run(state)
        assert result["error_category"] == "CODE"

    def test_unknown_fallback_maps_to_code(self):
        state = _make_state("WeirdException", "something went wrong")
        result = self.agent.run(state)
        assert result["error_category"] == "CODE"

    def test_appends_to_agent_trace(self):
        state = _make_state("UnhandledError", "test")
        result = self.agent.run(state)
        assert result["agent_trace"] == ["DiagnosisAgent"]

    def test_does_not_set_other_fields(self):
        state = _make_state("UnhandledError", "test")
        result = self.agent.run(state)
        assert set(result.keys()) == {"error_category", "agent_trace"}

    def test_todo_comment_present(self):
        import inspect
        import autosentinel.agents.diagnosis as mod
        src = inspect.getsource(mod)
        assert "TODO(W2)" in src
