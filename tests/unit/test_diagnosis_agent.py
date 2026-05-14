"""Tests for DiagnosisAgent — invariants + LLM wiring.

Functional routing tests (keyword → category) were removed when DiagnosisAgent
moved from keyword stub to real LLM (Sprint 5 PR-2 3b T031); routing correctness
is now validated by the 50-scenario benchmark in PR-5, not unit tests.
"""

from autosentinel.agents.diagnosis import DiagnosisAgent
from autosentinel.models import AgentState
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient

from tests.unit._llm_fixtures import diagnosis_fixture


_TEST_TRACE_ID = "0" * 32


def _make_state(error_type: str = "RuntimeError", message: str = "test") -> AgentState:
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
    state["trace_id"] = _TEST_TRACE_ID
    return state


def _make_mock_config() -> AgentModelConfig:
    return AgentModelConfig(
        model="mock-diagnosis",
        temperature=0.0,
        max_tokens=1024,
        endpoint_alias="mock",
    )


class TestDiagnosisAgentInvariants:
    """Agent-interface invariants (independent of LLM verdict content)."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(diagnosis_fixture())
        self.agent = DiagnosisAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    def test_appends_to_agent_trace(self):
        result = self.agent.run(_make_state())
        assert result["agent_trace"] == ["DiagnosisAgent"]

    def test_returns_only_expected_fields(self):
        result = self.agent.run(_make_state())
        assert set(result.keys()) == {"error_category", "agent_trace"}

    def test_sets_error_category_to_string(self):
        result = self.agent.run(_make_state())
        assert isinstance(result["error_category"], str)
        assert result["error_category"] in {"CODE", "INFRA", "CONFIG", "SECURITY"}


class TestDiagnosisAgentLLMWiring:
    """T025/T031: assert DiagnosisAgent invokes LLMClient.complete() with
    correct kwargs (agent_name, model, trace_id)."""

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
        state = _make_state()
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "diagnosis"
        assert req.model == "mock-diagnosis"
        assert req.trace_id == _TEST_TRACE_ID
