"""Integration tests: multi-agent graph security gate (T011b).

Tests HIGH_RISK interrupt/resume, CAUTION pass-through,
Docker-unavailable resilience, and end-to-end SC-003 verification.

Hermetic: every graph is built through the D2 `agents=` injection seam with
MockLLMClient fixtures (no real provider, zero spend). HIGH_RISK is driven by
a deny-listed CodeFixer artifact ("DROP TABLE users") that the SecurityReviewer
deny-list override forces to HIGH_RISK regardless of the LLM verdict; CAUTION
is driven by the SecurityReviewer fixture verdict on a non-deny-listed artifact.
"""

import json
import logging
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from langgraph.types import Command

from autosentinel.models import AgentState
from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.conftest import _setup_docker_success
from tests.integration._pr4_helpers import (
    build_fixture_clients,
    build_injected_agents,
)

# Deny-listed fix body → SecurityReviewer deny-list override → HIGH_RISK.
_HIGH_RISK_ARTIFACT = "DROP TABLE users"


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


def _initial_state(log_file: Path, fix_script: str | None = None) -> AgentState:
    return AgentState(
        log_path=str(log_file),
        error_log=None, parse_error=None,
        analysis_result=None, analysis_error=None,
        fix_script=fix_script,
        execution_result=None, execution_error=None,
        report_text=None, report_path=None,
        error_category=None, fix_artifact=None,
        security_verdict=None, routing_decision=None,
        agent_trace=[], approval_required=False,
    )


def _graph(**fixture_kwargs):
    """Build a multi-agent graph with MockLLMClient agents injected via the
    D2 seam. `fixture_kwargs` are forwarded to build_fixture_clients."""
    agents = build_injected_agents(build_fixture_clients(**fixture_kwargs))
    return build_multi_agent_graph(agents=agents)


def _high_risk_graph():
    """SECURITY incident → CodeFixer emits the deny-listed artifact → HIGH_RISK."""
    return _graph(
        diagnosis_category="SECURITY",
        supervisor_specialist="code_fixer",
        code_fixer_artifact=_HIGH_RISK_ARTIFACT,
    )


class TestHighRiskInterrupt:
    """SC-003: HIGH_RISK fix must trigger interrupt before Verifier runs."""

    def test_high_risk_suspends_pipeline(self, tmp_path):
        graph = _high_risk_graph()
        log = _write_log(tmp_path, "SecurityException", "sql injection", "hr.json")
        cfg = {"configurable": {"thread_id": "test-high-risk-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker"):
            result1 = graph.invoke(_initial_state(log), cfg)

        assert "__interrupt__" in result1

    def test_high_risk_sets_approval_required_after_resume(self, tmp_path):
        """approval_required is set in state after security_gate resumes (not before).
        interrupt() prevents the node's return value from being committed on first pass;
        after resume, security_gate completes and sets approval_required=True.
        """
        graph = _high_risk_graph()
        log = _write_log(tmp_path, "SecurityException", "sql injection", "hr2.json")
        cfg = {"configurable": {"thread_id": "test-hr-approval-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker") as md:
            graph.invoke(_initial_state(log), cfg)
            _setup_docker_success(md)
            result2 = graph.invoke(Command(resume="approved"), cfg)

        assert result2.get("approval_required") is True

    def test_high_risk_verifier_not_called_before_approval(self, tmp_path):
        graph = _high_risk_graph()
        log = _write_log(tmp_path, "SecurityException", "sql injection", "hr3.json")
        cfg = {"configurable": {"thread_id": "test-hr-noverify-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker"):
            result1 = graph.invoke(_initial_state(log), cfg)

        assert result1.get("execution_result") is None

    def test_high_risk_emits_human_approval_log(self, tmp_path, caplog):
        graph = _high_risk_graph()
        log = _write_log(tmp_path, "SecurityException", "sql injection", "hr4.json")
        cfg = {"configurable": {"thread_id": "test-hr-log-" + str(uuid.uuid4())}}

        with caplog.at_level(logging.INFO, logger="autosentinel.multi_agent_graph"), \
             patch("autosentinel.agents.verifier.docker"):
            graph.invoke(_initial_state(log), cfg)

        assert any("human_approval_required" in r.getMessage() for r in caplog.records)

    def test_high_risk_resume_runs_verifier(self, tmp_path):
        graph = _high_risk_graph()
        log = _write_log(tmp_path, "SecurityException", "sql injection", "hr5.json")
        cfg = {"configurable": {"thread_id": "test-hr-resume-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker") as md:
            graph.invoke(_initial_state(log), cfg)
            _setup_docker_success(md)
            result2 = graph.invoke(Command(resume="approved"), cfg)

        assert result2.get("execution_result") is not None

    def test_high_risk_report_after_approval(self, tmp_path):
        graph = _high_risk_graph()
        log = _write_log(tmp_path, "SecurityException", "sql injection", "hr6.json")
        cfg = {"configurable": {"thread_id": "test-hr-report-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker") as md:
            graph.invoke(_initial_state(log), cfg)
            _setup_docker_success(md)
            result2 = graph.invoke(Command(resume="approved"), cfg)

        assert result2.get("report_text") is not None
        assert "## Security Review" in result2["report_text"]


class TestCautionPassThrough:
    def test_caution_verdict_does_not_interrupt(self, tmp_path):
        graph = _graph(security_verdict="CAUTION")
        log = _write_log(tmp_path, "UnhandledError", "app logic error", "caution.json")
        cfg = {"configurable": {"thread_id": "test-caution-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)

        assert "__interrupt__" not in result
        assert result.get("execution_result") is not None

    def test_caution_badge_in_report(self, tmp_path):
        graph = _graph(security_verdict="CAUTION")
        log = _write_log(tmp_path, "UnhandledError", "app logic", "caution2.json")
        cfg = {"configurable": {"thread_id": "test-caution2-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)

        assert "⚠ CAUTION" in result.get("report_text", "")


class TestSecurityGateLogFailure:
    def test_log_failure_does_not_block_interrupt(self, tmp_path):
        """_logger.exception branch: if _logger.info raises, interrupt still fires."""
        graph = _high_risk_graph()
        log = _write_log(tmp_path, "SecurityException", "injection", "logfail.json")
        cfg = {"configurable": {"thread_id": "test-logfail-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker"), \
             patch("autosentinel.multi_agent_graph._logger") as mock_logger:
            mock_logger.info.side_effect = RuntimeError("logging infra down")
            result = graph.invoke(_initial_state(log), cfg)

        assert "__interrupt__" in result
        mock_logger.exception.assert_called_once()


class TestDockerUnavailable:
    def test_docker_unavailable_still_produces_report(self, tmp_path):
        import docker as docker_mod
        graph = _graph()
        log = _write_log(tmp_path, "UnhandledError", "app error", "docker_down.json")
        cfg = {"configurable": {"thread_id": "test-docker-down-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker") as md:
            md.from_env.side_effect = docker_mod.errors.DockerException("daemon down")
            result = graph.invoke(_initial_state(log), cfg)

        assert result.get("execution_error") is not None
        assert result.get("execution_result") is None
        assert result.get("report_text") is not None

    def test_safe_path_end_to_end(self, tmp_path):
        """CODE category + SAFE verdict → full pipeline runs without interrupt."""
        graph = _graph(diagnosis_category="CODE", supervisor_specialist="code_fixer")
        log = _write_log(tmp_path, "UnhandledError", "unexpected error in app logic", "safe.json")
        cfg = {"configurable": {"thread_id": "test-safe-" + str(uuid.uuid4())}}

        with patch("autosentinel.agents.verifier.docker") as md:
            _setup_docker_success(md)
            result = graph.invoke(_initial_state(log), cfg)

        assert "__interrupt__" not in result
        assert result["error_category"] == "CODE"
        assert result["security_verdict"] == "SAFE"
        assert result["execution_result"]["status"] == "success"
        assert "## Security Review" in result["report_text"]
