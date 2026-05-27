"""Tests for InfraSREAgent — invariants + LLM wiring.

Functional category-based artifact tests were removed when InfraSREAgent
moved from mock dict to real LLM (Sprint 5 PR-2 3b T033); routing/output
correctness is now validated by the 50-scenario benchmark in PR-5, not unit
tests.
"""

from decimal import Decimal

from autosentinel.agents.infra_sre import InfraSREAgent
from autosentinel.models import AgentState
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient
from autosentinel.llm.protocol import LLMResponse

from tests.unit._llm_fixtures import infra_sre_fixture


_DEFAULT_TRACE_ID = "0" * 32


def _make_state(error_category: str, trace_id: str | None = None) -> AgentState:
    state = AgentState(
        log_path="dummy.json",
        error_log={
            "timestamp": "2026-04-28T00:00:00Z",
            "service_name": "svc",
            "error_type": "ConnectionTimeout",
            "message": "db unreachable",
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
        model="mock-infra-sre",
        temperature=0.0,
        max_tokens=1024,
        endpoint_alias="mock",
    )


class TestInfraSREAgentInvariants:
    """Agent-interface invariants (independent of LLM content)."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(infra_sre_fixture())
        self.agent = InfraSREAgent(
            llm_client=self.mock_client,
            model_config=_make_mock_config(),
        )

    def test_sets_fix_artifact_to_non_empty_string(self):
        result = self.agent.run(_make_state("INFRA"))
        assert isinstance(result["fix_artifact"], str)
        assert len(result["fix_artifact"]) > 0

    def test_appends_to_agent_trace(self):
        result = self.agent.run(_make_state("INFRA"))
        assert result["agent_trace"] == ["InfraSREAgent"]

    def test_returns_only_expected_fields(self):
        result = self.agent.run(_make_state("INFRA"))
        assert set(result.keys()) == {"fix_artifact", "agent_trace"}


class TestInfraSREAgentLLMWiring:
    """T027/T033: assert InfraSREAgent invokes LLMClient.complete() for both
    INFRA and CONFIG shapes with correct kwargs."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(infra_sre_fixture())
        self.mock_config = _make_mock_config()
        self.agent = InfraSREAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_complete_called_for_infra_incident(self):
        state = _make_state("INFRA", trace_id="e" * 32)
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "infra_sre"
        assert req.model == "mock-infra-sre"
        assert req.trace_id == "e" * 32

    def test_complete_called_for_config_incident(self):
        state = _make_state("CONFIG", trace_id="f" * 32)
        self.agent.run(state)
        assert self.mock_client.call_count == 1
        req = self.mock_client.last_request
        assert req is not None
        assert req.agent_name == "infra_sre"
        assert req.trace_id == "f" * 32


class TestInfraSREAgentFenceHandling:
    """T033: defensive markdown-fence stripping (prompts forbid fences, but
    LLMs occasionally emit them anyway)."""

    def _agent_with_content(self, content: str) -> tuple[InfraSREAgent, MockLLMClient]:
        response = LLMResponse(
            content=content,
            model="mock-infra-sre",
            prompt_tokens=90,
            completion_tokens=25,
            cost_usd=Decimal("0.0004"),
            latency_ms=500,
            trace_id="0" * 32,
        )
        client = MockLLMClient().with_fixture_response(response)
        agent = InfraSREAgent(llm_client=client, model_config=_make_mock_config())
        return agent, client

    def test_strips_fenced_bash_block(self):
        fenced = '```bash\nsystemctl restart redis\n```'
        agent, _ = self._agent_with_content(fenced)
        result = agent.run(_make_state("INFRA", trace_id="0" * 32))
        assert result["fix_artifact"] == "systemctl restart redis"

    def test_passes_through_unfenced_content(self):
        agent, _ = self._agent_with_content('systemctl restart redis')
        result = agent.run(_make_state("INFRA", trace_id="0" * 32))
        assert result["fix_artifact"] == "systemctl restart redis"


class TestInfraSREAgentRequestKwargs:
    """T033: focused checks on the LLMRequest envelope built by the agent."""

    def setup_method(self):
        self.mock_client = MockLLMClient().with_fixture_response(infra_sre_fixture())
        self.mock_config = _make_mock_config()
        self.agent = InfraSREAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    def test_trace_id_passed_through(self):
        self.agent.run(_make_state("INFRA", trace_id="e" * 32))
        assert self.mock_client.last_request.trace_id == "e" * 32

    def test_agent_name_is_infra_sre(self):
        self.agent.run(_make_state("INFRA", trace_id="0" * 32))
        assert self.mock_client.last_request.agent_name == "infra_sre"

    def test_model_field_from_config(self):
        self.agent.run(_make_state("INFRA", trace_id="0" * 32))
        assert self.mock_client.last_request.model == self.mock_config.model
