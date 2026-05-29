"""Tests for SupervisorAgent — T039 LLM-backed routing.

Three test groups:
- TestSupervisorRouting: invariants on run() output shape (2 active) + 5
  direct get_specialist_key() asserts. 8 historical category-dispatch tests
  remain in the file marked @pytest.mark.skip — they exercised the Sprint 4
  keyword router which T039 retired.
- TestHeldOutRouting: 20-incident held-out set under fixture-mocked LLM
  (per-iteration with_fixture_response). T040 re-runs the same set against
  the real LLM outside CI for the ≥ 70 % stability check.
"""

from decimal import Decimal

import pytest

from autosentinel.agents.supervisor import SupervisorAgent
from autosentinel.llm.factory import AgentModelConfig
from autosentinel.llm.mock_client import MockLLMClient
from autosentinel.llm.protocol import LLMResponse
from autosentinel.models import AgentState

from tests.unit._llm_fixtures import supervisor_fixture


_TEST_TRACE_ID = "0" * 32
_DEPRECATED_BY_T039 = (
    "deprecated by T039: supervisor no longer dispatches on error_category"
)


def _make_state(error_category: str) -> AgentState:
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
        specialist=None,
        agent_trace=[],
        approval_required=False,
    )
    state["trace_id"] = _TEST_TRACE_ID
    return state


class TestSupervisorRouting:
    def setup_method(self):
        self.mock_client = MockLLMClient()
        self.mock_client.with_fixture_response(
            supervisor_fixture(specialist="code_fixer", rationale="test routing")
        )
        self.mock_config = AgentModelConfig(
            model="mock-supervisor",
            temperature=0.0,
            max_tokens=512,
            endpoint_alias="mock",
        )
        self.agent = SupervisorAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_code_routes_to_code_fixer(self):
        result = self.agent.run(_make_state("CODE"))
        assert "code_fixer" in result["routing_decision"].lower() or "CodeFixer" in result["routing_decision"]

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_security_routes_to_code_fixer(self):
        result = self.agent.run(_make_state("SECURITY"))
        assert "CodeFixer" in result["routing_decision"]

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_infra_routes_to_infra_sre(self):
        result = self.agent.run(_make_state("INFRA"))
        assert "InfraSRE" in result["routing_decision"]

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_config_routes_to_infra_sre(self):
        result = self.agent.run(_make_state("CONFIG"))
        assert "InfraSRE" in result["routing_decision"]

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_unknown_fallback_routes_to_code_fixer(self):
        result = self.agent.run(_make_state("UNKNOWN"))
        assert "CodeFixer" in result["routing_decision"]

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_none_category_fallback_routes_to_code_fixer(self):
        result = self.agent.run(_make_state(None))
        assert "CodeFixer" in result["routing_decision"]

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_routing_decision_contains_category(self):
        result = self.agent.run(_make_state("INFRA"))
        assert "INFRA" in result["routing_decision"]

    @pytest.mark.skip(reason=_DEPRECATED_BY_T039)
    def test_routing_decision_format(self):
        result = self.agent.run(_make_state("CODE"))
        assert "→" in result["routing_decision"] or "->" in result["routing_decision"]

    def test_appends_supervisor_to_agent_trace(self):
        result = self.agent.run(_make_state("CODE"))
        assert result["agent_trace"] == ["SupervisorAgent"]

    def test_returns_only_routing_fields(self):
        result = self.agent.run(_make_state("CODE"))
        assert set(result.keys()) == {"specialist", "routing_decision", "agent_trace"}

    def test_get_specialist_key_code(self):
        assert self.agent.get_specialist_key("CODE") == "code_fixer"

    def test_get_specialist_key_security(self):
        assert self.agent.get_specialist_key("SECURITY") == "code_fixer"

    def test_get_specialist_key_infra(self):
        assert self.agent.get_specialist_key("INFRA") == "infra_sre"

    def test_get_specialist_key_config(self):
        assert self.agent.get_specialist_key("CONFIG") == "infra_sre"

    def test_get_specialist_key_unknown_fallback(self):
        assert self.agent.get_specialist_key("UNKNOWN") == "code_fixer"


class TestHeldOutRouting:
    """Held-out routing accuracy on 20 incidents from data/routing-eval/held_out_v1.yaml.

    Per-iteration fixture injection emulates a perfectly-calibrated LLM. The
    accuracy threshold (≥ 70 %) thus tests Supervisor's JSON-parse + state
    update contract, not LLM quality. T040 re-runs the set outside CI against
    the real doubao-1.5-lite-32k endpoint for the quality / stability check.
    """

    _EXPECTED_SPECIALIST = {
        "CODE": "code_fixer",
        "SECURITY": "code_fixer",
        "INFRA": "infra_sre",
        "CONFIG": "infra_sre",
    }

    _EXPECTED_LLM_JSON = {
        "r01": '{"specialist": "code_fixer", "rationale": "AttributeError on None discount — code-level bug."}',
        "r02": '{"specialist": "code_fixer", "rationale": "IndexError off-by-one — code-level bug."}',
        "r03": '{"specialist": "code_fixer", "rationale": "TypeError on Decimal+str — code-level cast bug."}',
        "r04": '{"specialist": "code_fixer", "rationale": "Concurrent map writes — code missing mutex."}',
        "r05": '{"specialist": "code_fixer", "rationale": "ReDoS regex pattern — code-level fix."}',
        "r06": '{"specialist": "infra_sre", "rationale": "Postgres WAL disk full — infrastructure remediation."}',
        "r07": '{"specialist": "infra_sre", "rationale": "Kubernetes OOMKill — bump memory limit."}',
        "r08": '{"specialist": "infra_sre", "rationale": "CoreDNS timeout — DNS infra issue."}',
        "r09": '{"specialist": "infra_sre", "rationale": "NetworkPolicy blocking pod traffic — infra."}',
        "r10": '{"specialist": "infra_sre", "rationale": "EBS volume queue saturation — infrastructure tuning."}',
        "r11": '{"specialist": "code_fixer", "rationale": "Token in stdout — code-level redaction fix."}',
        "r12": '{"specialist": "code_fixer", "rationale": "SQL injection — parameterise query in code."}',
        "r13": '{"specialist": "code_fixer", "rationale": "Path traversal — sanitise filename in code."}',
        "r14": '{"specialist": "code_fixer", "rationale": "SSRF to IMDS — code-level URL allowlist."}',
        "r15": '{"specialist": "code_fixer", "rationale": "JWT alg none — enforce alg in code verify."}',
        "r16": '{"specialist": "infra_sre", "rationale": "Missing SMTP_PASSWORD env — config fix."}',
        "r17": '{"specialist": "infra_sre", "rationale": "Timeout too short in services.yaml — config."}',
        "r18": '{"specialist": "infra_sre", "rationale": "Deprecated redis host in helm values — config."}',
        "r19": '{"specialist": "infra_sre", "rationale": "Feature flag combination invalid — config."}',
        "r20": '{"specialist": "infra_sre", "rationale": "LOG_LEVEL=DEBUG in prod — config fix."}',
    }

    def setup_method(self):
        self.mock_client = MockLLMClient()
        self.mock_config = AgentModelConfig(
            model="mock-supervisor",
            temperature=0.0,
            max_tokens=512,
            endpoint_alias="mock",
        )
        self.agent = SupervisorAgent(
            llm_client=self.mock_client,
            model_config=self.mock_config,
        )

    @staticmethod
    def _load_incidents():
        import yaml
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[2]
            / "data/routing-eval/held_out_v1.yaml"
        )
        with path.open() as f:
            return yaml.safe_load(f)["incidents"]

    @staticmethod
    def _state_with_analysis(error_log: str) -> AgentState:
        state = AgentState(
            log_path="dummy.json",
            error_log=None,
            parse_error=None,
            analysis_result=error_log,
            analysis_error=None,
            fix_script=None,
            execution_result=None,
            execution_error=None,
            report_text=None,
            report_path=None,
            error_category=None,
            fix_artifact=None,
            security_verdict=None,
            routing_decision=None,
            specialist=None,
            agent_trace=[],
            approval_required=False,
        )
        state["trace_id"] = _TEST_TRACE_ID
        return state

    def _arm_fixture_for(self, incident_id: str) -> None:
        json_content = self._EXPECTED_LLM_JSON[incident_id]
        self.mock_client.with_fixture_response(
            LLMResponse(
                content=json_content,
                model="mock-supervisor",
                prompt_tokens=70,
                completion_tokens=15,
                cost_usd=Decimal("0.0002"),
                latency_ms=300,
                trace_id=_TEST_TRACE_ID,
            )
        )

    def test_routing_accuracy_above_70pct(self):
        incidents = self._load_incidents()
        hits = 0
        for incident in incidents:
            self._arm_fixture_for(incident["id"])
            state = self._state_with_analysis(incident["error_log"])
            result = self.agent.run(state)
            expected_key = self._EXPECTED_SPECIALIST[incident["expected_category"]]
            if result.get("specialist") == expected_key:
                hits += 1
        acc = hits / len(incidents)
        assert acc >= 0.70, f"accuracy {acc:.2%} below 70%"

    def test_routing_decision_references_analysis_result(self):
        incidents = self._load_incidents()
        r06 = next(i for i in incidents if i["id"] == "r06")
        snippet = "No space left on device"
        assert snippet in r06["error_log"], "snippet must exist in source incident"

        self._arm_fixture_for("r06")
        state = self._state_with_analysis(r06["error_log"])
        result = self.agent.run(state)

        in_routing = snippet in (result.get("routing_decision") or "")
        last_req = self.mock_client.last_request
        in_prompt = False
        if last_req is not None:
            in_prompt = any(snippet in (m.content or "") for m in last_req.messages)

        assert in_routing or in_prompt, (
            f"snippet {snippet!r} not found in routing_decision "
            f"({result.get('routing_decision')!r}) nor in llm_client prompt "
            f"(last_request={last_req!r})"
        )
