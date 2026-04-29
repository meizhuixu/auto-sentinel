"""Tests for InfraSREAgent — mock fix generation for INFRA/CONFIG."""

import inspect

import pytest

from autosentinel.agents.infra_sre import InfraSREAgent
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


class TestInfraSREAgent:
    def setup_method(self):
        self.agent = InfraSREAgent()

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
