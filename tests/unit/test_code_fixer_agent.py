"""Tests for CodeFixerAgent — mock fix generation for CODE/SECURITY."""

import inspect

import pytest

from autosentinel.agents.code_fixer import CodeFixerAgent
from autosentinel.models import AgentState
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient

from tests.unit._llm_fixtures import code_fixer_fixture


def _make_state(error_category: str, trace_id: str | None = None) -> AgentState:
    state = AgentState(
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
    if trace_id is not None:
        state["trace_id"] = trace_id
    return state


class TestCodeFixerAgent:
    def setup_method(self):
        self.mock_client = MockLLMClient()
        self.mock_config = AgentModelConfig(
            model="mock-code-fixer",
            temperature=0.0,
            max_tokens=1024,
            endpoint_alias="mock",
        )
        self.agent = CodeFixerAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_sets_fix_artifact_for_code(self):
        result = self.agent.run(_make_state("CODE"))
        assert result["fix_artifact"] is not None
        assert len(result["fix_artifact"]) > 0

    def test_sets_fix_artifact_for_security(self):
        result = self.agent.run(_make_state("SECURITY"))
        assert result["fix_artifact"] is not None
        assert len(result["fix_artifact"]) > 0

    def test_fix_artifact_is_string(self):
        result = self.agent.run(_make_state("CODE"))
        assert isinstance(result["fix_artifact"], str)

    def test_appends_to_agent_trace(self):
        result = self.agent.run(_make_state("CODE"))
        assert result["agent_trace"] == ["CodeFixerAgent"]

    def test_returns_only_expected_fields(self):
        result = self.agent.run(_make_state("CODE"))
        assert set(result.keys()) == {"fix_artifact", "agent_trace"}

    def test_code_and_security_produce_different_artifacts(self):
        code_result = self.agent.run(_make_state("CODE"))
        sec_result = self.agent.run(_make_state("SECURITY"))
        assert code_result["fix_artifact"] != sec_result["fix_artifact"]

    def test_todo_comment_present(self):
        import autosentinel.agents.code_fixer as mod
        src = inspect.getsource(mod)
        assert "TODO(W2)" in src


class TestCodeFixerAgentLLMWiring:
    """T026: assert CodeFixerAgent invokes LLMClient.complete() for both CODE and SECURITY shapes."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(code_fixer_fixture())
        self.mock_config = AgentModelConfig(
            model="mock-code-fixer",
            temperature=0.0,
            max_tokens=1024,
            endpoint_alias="mock",
        )
        self.agent = CodeFixerAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_complete_called_for_code_incident(self):
        state = _make_state("CODE", trace_id="b" * 32)
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "code_fixer"
        assert req.model == "mock-code-fixer"
        assert req.trace_id == "b" * 32

    def test_complete_called_for_security_incident(self):
        state = _make_state("SECURITY", trace_id="c" * 32)
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "code_fixer"
        assert req.trace_id == "c" * 32
