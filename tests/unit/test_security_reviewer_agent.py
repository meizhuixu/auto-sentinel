"""Tests for SecurityReviewerAgent — keyword detection on fix_artifact."""

import inspect

import pytest

from autosentinel.agents.security_reviewer import SecurityReviewerAgent, _HIGH_RISK_KEYWORDS
from autosentinel.models import AgentState


def _make_state(fix_artifact: str | None) -> AgentState:
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
        error_category="CODE",
        fix_artifact=fix_artifact,
        security_verdict=None,
        routing_decision=None,
        agent_trace=[],
        approval_required=False,
    )


class TestSecurityReviewerSafeArtifacts:
    def setup_method(self):
        self.agent = SecurityReviewerAgent()

    def test_clean_script_returns_safe(self):
        result = self.agent.run(_make_state('print("Restarting connection pool...")'))
        assert result["security_verdict"] == "SAFE"

    def test_none_fix_artifact_returns_safe(self):
        result = self.agent.run(_make_state(None))
        assert result["security_verdict"] == "SAFE"

    def test_empty_fix_artifact_returns_safe(self):
        result = self.agent.run(_make_state(""))
        assert result["security_verdict"] == "SAFE"

    def test_gc_script_returns_safe(self):
        result = self.agent.run(_make_state('print("Triggering garbage collection...")'))
        assert result["security_verdict"] == "SAFE"


class TestSecurityReviewerHighRiskKeywords:
    def setup_method(self):
        self.agent = SecurityReviewerAgent()

    @pytest.mark.parametrize("keyword", _HIGH_RISK_KEYWORDS)
    def test_each_keyword_triggers_high_risk(self, keyword):
        result = self.agent.run(_make_state(f'print("doing {keyword} now")'))
        assert result["security_verdict"] == "HIGH_RISK", (
            f"Expected HIGH_RISK for keyword '{keyword}'"
        )

    def test_drop_table_users_high_risk(self):
        result = self.agent.run(_make_state("DROP TABLE users"))
        assert result["security_verdict"] == "HIGH_RISK"

    def test_rm_rf_slash_high_risk(self):
        result = self.agent.run(_make_state("rm -rf /"))
        assert result["security_verdict"] == "HIGH_RISK"

    def test_keyword_case_sensitive(self):
        # Keywords are checked as-is (case-sensitive per spec)
        result = self.agent.run(_make_state("drop table users"))
        assert result["security_verdict"] == "SAFE"


class TestSecurityReviewerAgentTrace:
    def setup_method(self):
        self.agent = SecurityReviewerAgent()

    def test_appends_to_agent_trace(self):
        result = self.agent.run(_make_state("clean script"))
        assert result["agent_trace"] == ["SecurityReviewerAgent"]

    def test_returns_only_expected_fields(self):
        result = self.agent.run(_make_state("clean script"))
        assert set(result.keys()) == {"security_verdict", "agent_trace"}

    def test_todo_comment_present(self):
        import autosentinel.agents.security_reviewer as mod
        src = inspect.getsource(mod)
        assert "TODO(W2)" in src

    def test_reads_fix_artifact_not_fix_script(self):
        # fix_script is None, fix_artifact has a HIGH_RISK keyword
        state = AgentState(
            log_path="dummy.json",
            error_log=None, parse_error=None,
            analysis_result=None, analysis_error=None,
            fix_script=None,          # v1 field — must NOT be read
            execution_result=None, execution_error=None,
            report_text=None, report_path=None,
            error_category="CODE",
            fix_artifact="DROP TABLE sessions",   # v2 field — MUST be read
            security_verdict=None, routing_decision=None,
            agent_trace=[], approval_required=False,
        )
        result = self.agent.run(state)
        assert result["security_verdict"] == "HIGH_RISK"
