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


class TestVerifierAgentContainerCleanup:
    def test_container_remove_failure_is_swallowed(self):
        """container.remove() raising must not propagate — verifier must not crash."""
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_docker.from_env.return_value = mock_client
            mock_client.containers.run.return_value = mock_container
            mock_container.wait.return_value = {"StatusCode": 0}
            mock_container.logs.side_effect = [b"out\n", b""]
            mock_container.remove.side_effect = Exception("daemon disconnected")
            agent = VerifierAgent()
            result = agent.run(_make_state('print("x")'))
        assert result["execution_result"]["status"] == "success"
        assert result["execution_error"] is None


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


# ── Sprint 6 (006-fix-verification-integrity, T003) ─────────────────────────
# contracts/fix-artifact.md consumer obligations: deterministic normalization
# before any container work + file-mount execution replacing `python -c`.


def _capture_run_kwargs(mock_docker):
    """Arm containers.run to record kwargs AND read the mounted fix.py at call
    time (the temp dir is cleaned up after run(), so read during the call)."""
    from pathlib import Path

    captured: dict = {}

    def _run(image, command, **kwargs):
        captured["image"] = image
        captured["command"] = command
        captured["kwargs"] = kwargs
        volumes = kwargs.get("volumes") or {}
        for host_path, bind in volumes.items():
            captured["bind"] = bind
            fix_file = Path(host_path) / "fix.py"
            if fix_file.exists():
                captured["file_content"] = fix_file.read_text()
        container = MagicMock()
        container.wait.return_value = {"StatusCode": 0}
        container.logs.side_effect = [b"ok\n", b""]
        return container

    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.containers.run.side_effect = _run
    return captured


class TestVerifierFileMountExecution:
    def test_runs_fix_py_from_workspace_not_python_dash_c(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            captured = _capture_run_kwargs(mock_docker)
            agent = VerifierAgent()
            result = agent.run(_make_state('print("fix")'))
        assert captured["command"] == ["python", "/workspace/fix.py"]
        assert result["execution_result"]["status"] == "success"

    def test_mounts_artifact_read_only_at_workspace(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            captured = _capture_run_kwargs(mock_docker)
            agent = VerifierAgent()
            agent.run(_make_state('print("fix")'))
        assert captured["bind"] == {"bind": "/workspace", "mode": "ro"}

    def test_file_content_is_the_verbatim_artifact(self):
        artifact = 'import sys\nprint("fix")\nsys.exit(0)'
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            captured = _capture_run_kwargs(mock_docker)
            agent = VerifierAgent()
            agent.run(_make_state(artifact))
        assert captured["file_content"] == artifact

    def test_sandbox_limits_preserved(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            captured = _capture_run_kwargs(mock_docker)
            agent = VerifierAgent()
            agent.run(_make_state('print("fix")'))
        assert captured["image"] == "python:3.10-alpine"
        assert captured["kwargs"]["mem_limit"] == "64m"
        assert captured["kwargs"]["network_mode"] == "none"


class TestVerifierNormalizationWrapped:
    def test_bare_return_fragment_executes_wrapped(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            captured = _capture_run_kwargs(mock_docker)
            agent = VerifierAgent()
            result = agent.run(_make_state("value = {'a': 1}.get('a')\nreturn"))
        assert "def __autosentinel_fix__" in captured["file_content"]
        assert result["execution_result"]["status"] == "success"

    def test_wrapped_outcome_recorded_in_state(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            _capture_run_kwargs(mock_docker)
            agent = VerifierAgent()
            result = agent.run(_make_state("return"))
        assert result["fix_normalization"]["outcome"] == "wrapped"

    def test_verbatim_outcome_recorded_in_state(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            _capture_run_kwargs(mock_docker)
            agent = VerifierAgent()
            result = agent.run(_make_state('print("fix")'))
        assert result["fix_normalization"]["outcome"] == "verbatim"


class TestVerifierNormalizationRejected:
    def test_rejected_artifact_returns_honest_failure_without_container(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            agent = VerifierAgent()
            result = agent.run(_make_state("def broken(:"))
        mock_docker.from_env.assert_not_called()
        assert result["execution_result"]["status"] == "failure"
        assert result["execution_result"]["return_code"] is None
        assert result["execution_error"] is None
        assert result["fix_normalization"]["outcome"] == "rejected"

    def test_rejected_reason_surfaces_in_stderr(self):
        with patch("autosentinel.agents.verifier.docker"):
            agent = VerifierAgent()
            result = agent.run(_make_state("def broken(:"))
        assert "SyntaxError" in result["execution_result"]["stderr"]

    def test_empty_artifact_is_honest_failure_not_crash(self):
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            agent = VerifierAgent()
            result = agent.run(_make_state(""))
        mock_docker.from_env.assert_not_called()
        assert result["execution_result"]["status"] == "failure"
        assert "empty artifact" in result["execution_result"]["stderr"]

    def test_rejected_still_appends_agent_trace(self):
        with patch("autosentinel.agents.verifier.docker"):
            agent = VerifierAgent()
            result = agent.run(_make_state("def broken(:"))
        assert "VerifierAgent" in result["agent_trace"]
