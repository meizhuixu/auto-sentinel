"""Tests for CodeFixerAgent — invariants + LLM wiring.

Functional category-based artifact tests were removed when CodeFixerAgent
moved from mock dict to real LLM (Sprint 5 PR-2 3b T032); routing/output
correctness is now validated by the 50-scenario benchmark in PR-5, not unit
tests.
"""

from decimal import Decimal

from autosentinel.agents.code_fixer import CodeFixerAgent
from autosentinel.models import AgentState
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient
from autosentinel.llm.protocol import LLMResponse

from tests.unit._llm_fixtures import (
    SequenceLLMClient,
    code_fixer_fixture,
    script_fixture,
)


_DEFAULT_TRACE_ID = "0" * 32


def _make_state(error_category: str, trace_id: str | None = None) -> AgentState:
    state = AgentState(
        log_path="dummy.json",
        error_log={
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "svc",
            "error_type": "RuntimeError",
            "message": "boom",
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
        error_category=error_category,
        fix_artifact=None,
        security_verdict=None,
        routing_decision=None,
        agent_trace=[],
        approval_required=False,
    )
    state["trace_id"] = trace_id if trace_id is not None else _DEFAULT_TRACE_ID
    return state


def _make_mock_config() -> AgentModelConfig:
    return AgentModelConfig(
        model="mock-code-fixer",
        temperature=0.0,
        max_tokens=1024,
        endpoint_alias="mock",
    )


class TestCodeFixerAgentInvariants:
    """Agent-interface invariants (independent of LLM content)."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(code_fixer_fixture())
        self.agent = CodeFixerAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    def test_sets_fix_artifact_to_non_empty_string(self):
        result = self.agent.run(_make_state("CODE"))
        assert isinstance(result["fix_artifact"], str)
        assert len(result["fix_artifact"]) > 0

    def test_appends_to_agent_trace(self):
        result = self.agent.run(_make_state("CODE"))
        assert result["agent_trace"] == ["CodeFixerAgent"]

    def test_returns_only_expected_fields(self):
        result = self.agent.run(_make_state("CODE"))
        assert set(result.keys()) == {"fix_artifact", "agent_trace"}


class TestCodeFixerAgentLLMWiring:
    """T026/T032: assert CodeFixerAgent invokes LLMClient.complete() for both
    CODE and SECURITY shapes with correct kwargs."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(code_fixer_fixture())
        self.mock_config = _make_mock_config()
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


class TestCodeFixerAgentFenceHandling:
    """T032: defensive markdown-fence stripping (prompts forbid fences, but
    LLMs occasionally emit them anyway)."""

    def _agent_with_content(self, content: str) -> tuple[CodeFixerAgent, MockLLMClient]:
        response = LLMResponse(
            content=content,
            model="mock-code-fixer",
            prompt_tokens=90,
            completion_tokens=25,
            cost=Decimal("0.0004"),
            latency_ms=500,
            trace_id="0" * 32,
        )
        client = MockLLMClient().with_fixture_response(response)
        agent = CodeFixerAgent(llm_client=client, model_config=_make_mock_config())
        return agent, client

    def test_strips_fenced_python_block(self):
        fenced = '```python\nprint("hello")\n```'
        agent, _ = self._agent_with_content(fenced)
        result = agent.run(_make_state("CODE", trace_id="0" * 32))
        assert result["fix_artifact"] == 'print("hello")'

    def test_passes_through_unfenced_content(self):
        agent, _ = self._agent_with_content('print("plain")')
        result = agent.run(_make_state("CODE", trace_id="0" * 32))
        assert result["fix_artifact"] == 'print("plain")'


# ── Sprint 6 (006-fix-verification-integrity, T004) ─────────────────────────
# contracts/fix-artifact.md producer obligations: compile()-validation after
# fence-stripping + exactly one retry with the compile error appended.


class TestCodeFixerArtifactValidation:
    def _agent(self, contents: list[str]) -> tuple[CodeFixerAgent, SequenceLLMClient]:
        client = SequenceLLMClient([script_fixture(c) for c in contents])
        agent = CodeFixerAgent(llm_client=client, model_config=_make_mock_config())
        return agent, client

    def test_compile_clean_response_makes_no_retry(self):
        agent, client = self._agent(['print("valid fix")'])
        result = agent.run(_make_state("CODE"))
        assert client.call_count == 1
        assert result["fix_artifact"] == 'print("valid fix")'

    def test_fragment_triggers_exactly_one_retry(self):
        agent, client = self._agent(["return", 'print("valid on retry")'])
        result = agent.run(_make_state("CODE"))
        assert client.call_count == 2
        assert result["fix_artifact"] == 'print("valid on retry")'

    def test_retry_prompt_carries_the_compile_error(self):
        agent, client = self._agent(["return", 'print("valid on retry")'])
        agent.run(_make_state("CODE"))
        retry_user_content = " ".join(
            m.content for m in client.requests[1].messages if m.role == "user"
        )
        assert "'return' outside function" in retry_user_content
        assert "return" in retry_user_content  # the offending artifact is shown back

    def test_retry_still_broken_passes_artifact_through_without_raising(self):
        # Verifier's deterministic layer owns the last line of defense —
        # the producer must never crash the pipeline over a bad artifact
        agent, client = self._agent(["return", "return"])
        result = agent.run(_make_state("CODE"))
        assert client.call_count == 2  # exactly one retry, never more
        assert result["fix_artifact"] == "return"

    def test_fenced_valid_script_is_stripped_before_validation(self):
        agent, client = self._agent(['```python\nprint("fenced fix")\n```'])
        result = agent.run(_make_state("CODE"))
        assert client.call_count == 1  # fence-stripped artifact compiles: no retry
        assert result["fix_artifact"] == 'print("fenced fix")'

    def test_retry_uses_same_trace_id_and_agent_name(self):
        agent, client = self._agent(["return", 'print("ok")'])
        agent.run(_make_state("CODE", trace_id="d" * 32))
        assert client.requests[1].trace_id == "d" * 32
        assert client.requests[1].agent_name == "code_fixer"


class TestCodeFixerAgentRequestKwargs:
    """T032: focused checks on the LLMRequest envelope built by the agent."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(code_fixer_fixture())
        self.mock_config = _make_mock_config()
        self.agent = CodeFixerAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_trace_id_passed_through(self):
        self.agent.run(_make_state("CODE", trace_id="b" * 32))
        assert self.mock_client.last_request.trace_id == "b" * 32

    def test_agent_name_is_code_fixer(self):
        self.agent.run(_make_state("CODE", trace_id="0" * 32))
        assert self.mock_client.last_request.agent_name == "code_fixer"

    def test_model_field_from_config(self):
        self.agent.run(_make_state("CODE", trace_id="0" * 32))
        assert self.mock_client.last_request.model == self.mock_config.model
