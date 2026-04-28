"""Integration tests: multi-agent graph routing (T011a).

Tests 4-category routing, UNKNOWN fallback, routing_decision format,
and agent_trace ordering (specialist before SecurityReviewerAgent).
"""

import json
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from autosentinel.models import AgentState
from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.conftest import _setup_docker_success


def _write_log(tmp_path: Path, error_type: str, message: str, name: str) -> Path:
    log_file = tmp_path / name
    log_file.write_text(json.dumps({
        "timestamp": "2026-04-28T00:00:00Z",
        "service_name": "test-svc",
        "error_type": error_type,
        "message": message,
        "stack_trace": None,
    }))
    return log_file


def _initial_state(log_file: Path) -> AgentState:
    return AgentState(
        log_path=str(log_file),
        error_log=None, parse_error=None,
        analysis_result=None, analysis_error=None,
        fix_script=None,
        execution_result=None, execution_error=None,
        report_text=None, report_path=None,
        error_category=None, fix_artifact=None,
        security_verdict=None, routing_decision=None,
        agent_trace=[], approval_required=False,
    )


@pytest.fixture
def graph():
    return build_multi_agent_graph()


@pytest.fixture
def cfg():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


class TestCategoryRouting:
    def test_code_category_routes_to_code_fixer(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "UnhandledError", "unexpected None in user context", "code.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        assert result["error_category"] == "CODE"
        assert "CodeFixerAgent" in result["agent_trace"]
        assert "InfraSREAgent" not in result["agent_trace"]

    def test_infra_category_routes_to_infra_sre(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "ConnectionTimeout", "connection refused to db", "infra.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        assert result["error_category"] == "INFRA"
        assert "InfraSREAgent" in result["agent_trace"]
        assert "CodeFixerAgent" not in result["agent_trace"]

    def test_config_category_routes_to_infra_sre(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "ConfigurationError", "environment variable JWT_SECRET not set", "config.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        assert result["error_category"] == "CONFIG"
        assert "InfraSREAgent" in result["agent_trace"]
        assert result["routing_decision"] is not None
        assert "InfraSRE" in result["routing_decision"]

    def test_security_category_routes_to_code_fixer(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "SecurityException", "sql injection attempt detected", "sec.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        assert result["error_category"] == "SECURITY"
        assert "CodeFixerAgent" in result["agent_trace"]


class TestRoutingDecisionRecorded:
    def test_routing_decision_set(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "UnhandledError", "unexpected error", "rd.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        assert result["routing_decision"] is not None
        assert len(result["routing_decision"]) > 0

    def test_routing_decision_contains_category(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "ConnectionTimeout", "timeout", "rd2.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        assert "INFRA" in result["routing_decision"]


class TestAgentTraceOrdering:
    def test_specialist_before_security_reviewer(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "UnhandledError", "app error", "order.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        trace = result["agent_trace"]
        assert "SecurityReviewerAgent" in trace
        security_idx = trace.index("SecurityReviewerAgent")
        specialist_idx = next(
            i for i, a in enumerate(trace)
            if a in ("CodeFixerAgent", "InfraSREAgent")
        )
        assert specialist_idx < security_idx

    def test_diagnosis_before_specialist(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "UnhandledError", "app error", "order2.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        trace = result["agent_trace"]
        diag_idx = trace.index("DiagnosisAgent")
        specialist_idx = next(
            i for i, a in enumerate(trace)
            if a in ("CodeFixerAgent", "InfraSREAgent")
        )
        assert diag_idx < specialist_idx

    def test_all_expected_agents_present(self, graph, cfg, tmp_path):
        log = _write_log(tmp_path, "UnhandledError", "app error", "all.json")
        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)
        for agent in ("DiagnosisAgent", "SupervisorAgent", "SecurityReviewerAgent", "VerifierAgent"):
            assert agent in result["agent_trace"], f"{agent} missing from trace"


class TestParseErrorShortCircuit:
    def test_invalid_json_skips_agents(self, graph, tmp_path):
        bad_log = tmp_path / "bad.json"
        bad_log.write_text("not valid json")
        cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
        result = graph.invoke(_initial_state(bad_log), cfg)
        assert result.get("parse_error") is not None
        assert result.get("report_text") is None
