"""Tests for VerifierAgent — sole Docker executor, reads fix_artifact."""

from unittest.mock import MagicMock, patch

import pytest

from autosentinel.agents.verifier import VerifierAgent
from autosentinel.models import AgentState


def _make_state(fix_artifact: str | None = None) -> AgentState:
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
        security_verdict="SAFE",
        routing_decision="CODE → CodeFixerAgent",
        agent_trace=["DiagnosisAgent", "SupervisorAgent", "CodeFixerAgent", "SecurityReviewerAgent"],
        approval_required=False,
    )


@pytest.fixture
def mock_docker_success():
    with patch("autosentinel.agents.verifier.docker") as mock_docker:
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = [b"Fix applied\n", b""]
        yield mock_docker


@pytest.fixture
def mock_docker_failure():
    with patch("autosentinel.agents.verifier.docker") as mock_docker:
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 1}
        mock_container.logs.side_effect = [b"", b"Error: assertion failed\n"]
        yield mock_docker


@pytest.fixture
def mock_docker_timeout():
    import requests.exceptions
    with patch("autosentinel.agents.verifier.docker") as mock_docker:
        mock_client = MagicMock()
        mock_container = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.side_effect = requests.exceptions.ReadTimeout()
        yield mock_docker


@pytest.fixture
def mock_docker_unavailable():
    import docker as docker_mod
    with patch("autosentinel.agents.verifier.docker") as mock_docker:
        mock_docker.from_env.side_effect = docker_mod.errors.DockerException("daemon down")
        yield mock_docker


class TestVerifierAgentNoFixArtifact:
    def test_none_fix_artifact_returns_skipped(self):
        agent = VerifierAgent()
        with patch("autosentinel.agents.verifier.docker"):
            result = agent.run(_make_state(None))
        assert result["execution_result"]["status"] == "skipped"
        assert result["execution_error"] is None

    def test_appends_to_agent_trace_when_skipped(self):
        agent = VerifierAgent()
        with patch("autosentinel.agents.verifier.docker"):
            result = agent.run(_make_state(None))
        assert "VerifierAgent" in result["agent_trace"]


class TestVerifierAgentSuccess:
    def test_success_status(self, mock_docker_success):
        agent = VerifierAgent()
        result = agent.run(_make_state('print("fix")'))
        assert result["execution_result"]["status"] == "success"

    def test_success_return_code_zero(self, mock_docker_success):
        agent = VerifierAgent()
        result = agent.run(_make_state('print("fix")'))
        assert result["execution_result"]["return_code"] == 0

    def test_success_stdout_captured(self, mock_docker_success):
        agent = VerifierAgent()
        result = agent.run(_make_state('print("fix")'))
        assert result["execution_result"]["stdout"] == "Fix applied\n"

    def test_success_execution_error_is_none(self, mock_docker_success):
        agent = VerifierAgent()
        result = agent.run(_make_state('print("fix")'))
        assert result["execution_error"] is None

    def test_appends_to_agent_trace(self, mock_docker_success):
        agent = VerifierAgent()
        result = agent.run(_make_state('print("fix")'))
        assert result["agent_trace"] == ["VerifierAgent"]


class TestVerifierAgentFailure:
    def test_failure_status(self, mock_docker_failure):
        agent = VerifierAgent()
        result = agent.run(_make_state('raise ValueError()'))
        assert result["execution_result"]["status"] == "failure"

    def test_failure_nonzero_return_code(self, mock_docker_failure):
        agent = VerifierAgent()
        result = agent.run(_make_state('raise ValueError()'))
        assert result["execution_result"]["return_code"] == 1


class TestVerifierAgentTimeout:
    def test_timeout_status(self, mock_docker_timeout):
        agent = VerifierAgent()
        result = agent.run(_make_state('import time; time.sleep(999)'))
        assert result["execution_result"]["status"] == "timeout"

    def test_timeout_execution_error_is_none(self, mock_docker_timeout):
        agent = VerifierAgent()
        result = agent.run(_make_state('import time; time.sleep(999)'))
        assert result["execution_error"] is None


class TestVerifierAgentDockerUnavailable:
    def test_docker_unavailable_sets_execution_error(self, mock_docker_unavailable):
        agent = VerifierAgent()
        result = agent.run(_make_state('print("fix")'))
        assert result["execution_error"] is not None
        assert result["execution_result"] is None

    def test_docker_unavailable_still_appends_trace(self, mock_docker_unavailable):
        agent = VerifierAgent()
        result = agent.run(_make_state('print("fix")'))
        assert "VerifierAgent" in result["agent_trace"]


class TestVerifierAgentReadsFixArtifact:
    def test_reads_fix_artifact_not_fix_script(self, mock_docker_success):
        """Verifier must use fix_artifact (v2), not fix_script (v1)."""
        state = _make_state(None)
        state = dict(state)
        state["fix_script"] = 'print("v1 script")'   # v1 field — must be ignored
        state["fix_artifact"] = 'print("v2 artifact")'  # v2 field — must be used
        agent = VerifierAgent()
        result = agent.run(AgentState(**state))
        assert result["execution_result"]["status"] == "success"
