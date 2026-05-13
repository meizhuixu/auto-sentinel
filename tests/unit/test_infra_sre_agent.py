"""Tests for InfraSREAgent — mock fix generation for INFRA/CONFIG."""

import inspect

import pytest

from autosentinel.agents.infra_sre import InfraSREAgent
from autosentinel.models import AgentState
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient

from tests.unit._llm_fixtures import infra_sre_fixture


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


class TestInfraSREAgent:
    def setup_method(self):
        self.mock_client = MockLLMClient()
        self.mock_config = AgentModelConfig(
            model="mock-infra-sre",
            temperature=0.0,
            max_tokens=1024,
            endpoint_alias="mock",
        )
        self.agent = InfraSREAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_sets_fix_artifact_for_infra(self):
        result = self.agent.run(_make_state("INFRA"))
        assert result["fix_artifact"] is not None
        assert len(result["fix_artifact"]) > 0

    def test_sets_fix_artifact_for_config(self):
        result = self.agent.run(_make_state("CONFIG"))
        assert result["fix_artifact"] is not None
        assert len(result["fix_artifact"]) > 0

    def test_fix_artifact_is_string(self):
        result = self.agent.run(_make_state("INFRA"))
        assert isinstance(result["fix_artifact"], str)

    def test_appends_to_agent_trace(self):
        result = self.agent.run(_make_state("INFRA"))
        assert result["agent_trace"] == ["InfraSREAgent"]

    def test_returns_only_expected_fields(self):
        result = self.agent.run(_make_state("INFRA"))
        assert set(result.keys()) == {"fix_artifact", "agent_trace"}

    def test_infra_and_config_produce_different_artifacts(self):
        infra_result = self.agent.run(_make_state("INFRA"))
        config_result = self.agent.run(_make_state("CONFIG"))
        assert infra_result["fix_artifact"] != config_result["fix_artifact"]

    def test_todo_comment_present(self):
        import autosentinel.agents.infra_sre as mod
        src = inspect.getsource(mod)
        assert "TODO(W2)" in src


class TestInfraSREAgentLLMWiring:
    """T027: assert InfraSREAgent invokes LLMClient.complete() with correct kwargs."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(infra_sre_fixture())
        self.mock_config = AgentModelConfig(
            model="mock-infra-sre",
            temperature=0.0,
            max_tokens=1024,
            endpoint_alias="mock",
        )
        self.agent = InfraSREAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_complete_called_with_correct_agent_name_and_trace_id(self):
        state = _make_state("INFRA", trace_id="e" * 32)
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "infra_sre"
        assert req.model == "mock-infra-sre"
        assert req.trace_id == "e" * 32
