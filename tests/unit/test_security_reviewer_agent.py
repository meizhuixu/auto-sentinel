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


class TestSecurityReviewerSecretCredentialOverride:
    """Constitution Principle V: a fix that touches secrets/credentials MUST be
    HIGH_RISK. LLM semantic review proved unreliable for this class — GLM-4.7
    returned non-HIGH_RISK for the hardcoded-credential (032), insecure-deser
    session-secret (034), and weak-crypto password-hashing (035) remediations in
    the T066 security subset. A deterministic keyword override forces HIGH_RISK,
    mirroring the destructive-ops deny-list (defense-in-depth).
    """

    def setup_method(self):
        # LLM says SAFE; the secret/credential override must still force HIGH_RISK.
        self.mock_client = MockLLMClient().with_fixture_response(safe_fixture())
        self.agent = SecurityReviewerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    @pytest.mark.parametrize("artifact", [
        'AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")',           # 032 shape
        'SESSION_SECRET = os.environ.get("SESSION_SECRET_KEY")',  # 034 shape
        'import bcrypt\nreturn bcrypt.hashpw(pw, bcrypt.gensalt())',  # 035 shape
        'API_KEY = config["api_key"]',
        'h = hashlib.pbkdf2_hmac("sha256", password, salt, 100000)',
    ])
    def test_secret_credential_artifact_forces_high_risk(self, artifact):
        result = self.agent.run(_make_state(artifact, trace_id=_TEST_TRACE_ID))
        assert result["security_verdict"] == "HIGH_RISK", (
            f"Principle V: secret/credential-touching fix must be HIGH_RISK: {artifact!r}"
        )

    def test_clean_fix_without_secrets_stays_safe(self):
        # Regression guard: the override must not over-fire on side-effect-free
        # code with no secret/credential surface.
        result = self.agent.run(
            _make_state("import html\nreturn html.escape(user_input)", trace_id=_TEST_TRACE_ID)
        )
        assert result["security_verdict"] == "SAFE"


class TestSecurityReviewerLLMFailureFailSafe:
    """Constitution Principle V: the gate MUST emit a verdict for every fix
    (100% coverage, no bypass). When the GLM call fails (timeout / provider
    error), the agent must NOT crash the pipeline — it falls back to a fail-safe
    HIGH_RISK verdict (an unreviewable fix is held for human approval). T066
    full run: a GLM timeout on the 034 security review produced no verdict at
    all, counted as an SC-013 false negative.
    """

    def test_llm_timeout_falls_back_to_high_risk(self):
        from autosentinel.llm.errors import LLMTimeoutError

        client = MockLLMClient().with_error(LLMTimeoutError("timed out"))
        agent = SecurityReviewerAgent(llm_client=client, model_config=_make_mock_config())
        result = agent.run(_make_state("print('a clean fix')", trace_id=_TEST_TRACE_ID))
        assert result["security_verdict"] == "HIGH_RISK"
        assert result["agent_trace"] == ["SecurityReviewerAgent"]

    def test_llm_provider_error_falls_back_to_high_risk(self):
        from autosentinel.llm.errors import LLMProviderError

        client = MockLLMClient().with_error(LLMProviderError("5xx"))
        agent = SecurityReviewerAgent(llm_client=client, model_config=_make_mock_config())
        result = agent.run(_make_state("print('a clean fix')", trace_id=_TEST_TRACE_ID))
        assert result["security_verdict"] == "HIGH_RISK"


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


class TestSecurityReviewerPromptAlignsPrincipleV:
    """Constitution Principle V: HIGH_RISK is defined as any fix that modifies
    production configuration, issues database write operations, or touches
    secrets/credentials. Prompt templates that encode remediation logic MUST be
    versioned and tested like source code (Principle V). This pins SYSTEM_PROMPT
    to the Principle-V definition rather than a generic 'destructiveness' framing
    — the original prompt judged only destructive ops (data drop / rm -rf /
    chmod), which let secret/config-touching fixes slip through as SAFE.
    """

    def test_system_prompt_encodes_principle_v_high_risk_categories(self):
        from autosentinel.agents.prompts.security_reviewer import SYSTEM_PROMPT

        prompt = SYSTEM_PROMPT.lower()
        assert "configuration" in prompt, \
            "HIGH_RISK must cover production-configuration changes (Principle V)"
        assert "database" in prompt, \
            "HIGH_RISK must cover database write operations (Principle V)"
        assert ("secret" in prompt) or ("credential" in prompt), \
            "HIGH_RISK must cover secrets/credentials (Principle V)"


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
