"""Tests for DiagnosisAgent — keyword routing to CODE/INFRA/CONFIG/SECURITY."""

import pytest

from autosentinel.agents.diagnosis import DiagnosisAgent
from autosentinel.models import AgentState
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient

from tests.unit._llm_fixtures import diagnosis_fixture


def _make_state(error_type: str, message: str, trace_id: str | None = None) -> AgentState:
    state = AgentState(
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
    if trace_id is not None:
        state["trace_id"] = trace_id
    return state


class TestDiagnosisAgentRouting:
    def setup_method(self):
        self.mock_client = MockLLMClient()
        self.mock_config = AgentModelConfig(
            model="mock-diagnosis",
            temperature=0.0,
            max_tokens=1024,
            endpoint_alias="mock",
        )
        self.agent = DiagnosisAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

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


class TestDiagnosisAgentLLMWiring:
    """T025: assert DiagnosisAgent invokes LLMClient.complete() with correct kwargs."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(diagnosis_fixture())
        self.mock_config = AgentModelConfig(
            model="mock-diagnosis",
            temperature=0.0,
            max_tokens=1024,
            endpoint_alias="mock",
        )
        self.agent = DiagnosisAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_complete_called_once_with_correct_agent_name_and_trace_id(self):
        state = _make_state("UnhandledError", "test", trace_id="a" * 32)
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "diagnosis"
        assert req.model == "mock-diagnosis"
        assert req.trace_id == "a" * 32
