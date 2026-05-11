"""Tests for SecurityReviewerAgent — keyword detection on fix_artifact."""

import inspect

import pytest

from autosentinel.agents.security_reviewer import SecurityReviewerAgent, _HIGH_RISK_KEYWORDS
from autosentinel.models import AgentState
from decimal import Decimal

from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient
from autosentinel.llm.protocol import LLMResponse


_TEST_TRACE_ID = "d" * 32


def _safe_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "SAFE", "reasoning": "no destructive ops"}',
        model="glm-4.7",
        prompt_tokens=100,
        completion_tokens=30,
        cost_usd=Decimal("0.0005"),
        latency_ms=500,
        trace_id=_TEST_TRACE_ID,
    )


def _high_risk_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "HIGH_RISK", "reasoning": "DROP TABLE detected"}',
        model="glm-4.7",
        prompt_tokens=120,
        completion_tokens=40,
        cost_usd=Decimal("0.0008"),
        latency_ms=850,
        trace_id=_TEST_TRACE_ID,
    )


def _caution_fixture() -> LLMResponse:
    return LLMResponse(
        content='{"verdict": "CAUTION", "reasoning": "ambiguous shell command"}',
        model="glm-4.7",
        prompt_tokens=110,
        completion_tokens=35,
        cost_usd=Decimal("0.0006"),
        latency_ms=700,
        trace_id=_TEST_TRACE_ID,
    )


def _make_mock_config() -> AgentModelConfig:
    return AgentModelConfig(
        model="mock-security-reviewer",
        temperature=0.0,
        max_tokens=1024,
        endpoint_alias="mock",
    )


def _make_state(fix_artifact: str | None, trace_id: str | None = None) -> AgentState:
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
        error_category="CODE",
        fix_artifact=fix_artifact,
        security_verdict=None,
        routing_decision=None,
        agent_trace=[],
        approval_required=False,
    )
    if trace_id is not None:
        state["trace_id"] = trace_id
    return state


class TestSecurityReviewerSafeArtifacts:
    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(_safe_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

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
        self.mock_client = MockLLMClient().with_fixture_response(_high_risk_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

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
        self.mock_client = MockLLMClient().with_fixture_response(_caution_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

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


class TestSecurityReviewerLLMWiring:
    """T028: assert SecurityReviewerAgent invokes LLMClient.complete()
    with GLM-bound model_config and correct trace_id."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(_safe_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    def test_complete_called_with_correct_kwargs(self):
        state = _make_state("clean script", trace_id=_TEST_TRACE_ID)
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "security_reviewer"
        assert req.model == "mock-security-reviewer"
        assert req.trace_id == _TEST_TRACE_ID
