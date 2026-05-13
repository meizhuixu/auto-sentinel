"""Tests for SecurityReviewerAgent — LLM verdict + deny-list override."""

import pytest

from autosentinel.agents.security_reviewer import SecurityReviewerAgent, _HIGH_RISK_KEYWORDS
from autosentinel.models import AgentState

from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient

from tests.unit._llm_fixtures import (
    safe_fixture,
    caution_fixture,
)


_TEST_TRACE_ID = "0" * 32


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
        self.mock_client = MockLLMClient().with_fixture_response(safe_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    def test_clean_script_returns_safe(self):
        result = self.agent.run(_make_state('print("Restarting connection pool...")', trace_id=_TEST_TRACE_ID))
        assert result["security_verdict"] == "SAFE"

    def test_none_fix_artifact_returns_safe(self):
        result = self.agent.run(_make_state(None, trace_id=_TEST_TRACE_ID))
        assert result["security_verdict"] == "SAFE"

    def test_empty_fix_artifact_returns_safe(self):
        result = self.agent.run(_make_state("", trace_id=_TEST_TRACE_ID))
        assert result["security_verdict"] == "SAFE"

    def test_gc_script_returns_safe(self):
        result = self.agent.run(_make_state('print("Triggering garbage collection...")', trace_id=_TEST_TRACE_ID))
        assert result["security_verdict"] == "SAFE"


class TestSecurityReviewerDenyListOverride:
    """T034: deny-list keywords force HIGH_RISK even when LLM returns SAFE.

    Defense-in-depth: prompt-injection-resistant; LLM verdict can be
    overridden by hard-coded keyword match on the fix_artifact.
    """

    def setup_method(self):
        # LLM returns SAFE — but artifact contains HIGH_RISK keyword,
        # so the agent MUST upgrade the verdict to HIGH_RISK.
        self.mock_client = MockLLMClient().with_fixture_response(safe_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    @pytest.mark.parametrize("keyword", _HIGH_RISK_KEYWORDS)
    def test_keyword_override_forces_high_risk(self, keyword):
        result = self.agent.run(
            _make_state(f'print("doing {keyword} now")', trace_id=_TEST_TRACE_ID)
        )
        assert result["security_verdict"] == "HIGH_RISK", (
            f"Expected deny-list override for keyword '{keyword}' (LLM said SAFE)"
        )

    def test_drop_table_users_overrides_to_high_risk(self):
        result = self.agent.run(
            _make_state("DROP TABLE users", trace_id=_TEST_TRACE_ID)
        )
        assert result["security_verdict"] == "HIGH_RISK"

    def test_rm_rf_slash_overrides_to_high_risk(self):
        result = self.agent.run(
            _make_state("rm -rf /", trace_id=_TEST_TRACE_ID)
        )
        assert result["security_verdict"] == "HIGH_RISK"

    def test_lowercase_keyword_does_not_override(self):
        # 'drop table users' (lowercase) not in deny-list → LLM verdict SAFE wins
        result = self.agent.run(
            _make_state("drop table users", trace_id=_TEST_TRACE_ID)
        )
        assert result["security_verdict"] == "SAFE"


class TestSecurityReviewerAgentTrace:
    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(caution_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    def test_appends_to_agent_trace(self):
        result = self.agent.run(_make_state("clean script", trace_id=_TEST_TRACE_ID))
        assert result["agent_trace"] == ["SecurityReviewerAgent"]

    def test_returns_only_expected_fields(self):
        result = self.agent.run(_make_state("clean script", trace_id=_TEST_TRACE_ID))
        assert set(result.keys()) == {"security_verdict", "security_classifier_model", "agent_trace"}

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
        state["trace_id"] = _TEST_TRACE_ID
        result = self.agent.run(state)
        assert result["security_verdict"] == "HIGH_RISK"


class TestSecurityReviewerLLMWiring:
    """T028: assert SecurityReviewerAgent invokes LLMClient.complete()
    with GLM-bound model_config and correct trace_id."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(safe_fixture())
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
