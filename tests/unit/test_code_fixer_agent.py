"""Tests for CodeFixerAgent — mock fix generation for CODE/SECURITY."""

import inspect

import pytest

from autosentinel.agents.code_fixer import CodeFixerAgent
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


class TestCodeFixerAgent:
    def setup_method(self):
        self.agent = CodeFixerAgent()

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
