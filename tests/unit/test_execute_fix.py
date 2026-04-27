"""Unit tests for the execute_fix node — Docker SDK fully mocked."""

import requests.exceptions
import docker.errors
import pytest
from unittest.mock import MagicMock, patch

from autosentinel.nodes.execute_fix import execute_fix


def _base_state(**overrides):
    state = {
        "log_path": "data/incoming/test.json",
        "error_log": None,
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "fix_script": 'print("hello")',
        "execution_result": None,
        "execution_error": None,
        "report_text": None,
        "report_path": None,
    }
    state.update(overrides)
    return state


class TestExecuteFixSuccess:
    def test_status_is_success(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        result = execute_fix(_base_state())
        assert result["execution_result"]["status"] == "success"

    def test_return_code_is_zero(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        result = execute_fix(_base_state())
        assert result["execution_result"]["return_code"] == 0

    def test_stdout_captured(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        result = execute_fix(_base_state())
        assert result["execution_result"]["stdout"] == "hello from sandbox\n"

    def test_stderr_empty(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        result = execute_fix(_base_state())
        assert result["execution_result"]["stderr"] == ""

    def test_duration_ms_non_negative(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        result = execute_fix(_base_state())
        assert result["execution_result"]["duration_ms"] >= 0

    def test_execution_error_is_none(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        result = execute_fix(_base_state())
        assert result["execution_error"] is None

    def test_container_removed(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        execute_fix(_base_state())
        mock_container.remove.assert_called_once_with(force=True)

    def test_container_run_with_sandbox_options(self, mock_docker_success):
        mock_docker, mock_container = mock_docker_success
        execute_fix(_base_state(fix_script='print("hello")'))
        call_kwargs = mock_docker.from_env.return_value.containers.run.call_args
        assert call_kwargs.kwargs["mem_limit"] == "64m"
        assert call_kwargs.kwargs["network_mode"] == "none"
        assert call_kwargs.kwargs["detach"] is True


class TestExecuteFixFailure:
    def test_status_is_failure(self, mock_docker_failure):
        mock_docker, mock_container = mock_docker_failure
        result = execute_fix(_base_state())
        assert result["execution_result"]["status"] == "failure"

    def test_return_code_is_nonzero(self, mock_docker_failure):
        mock_docker, mock_container = mock_docker_failure
        result = execute_fix(_base_state())
        assert result["execution_result"]["return_code"] == 1

    def test_stderr_captured(self, mock_docker_failure):
        mock_docker, mock_container = mock_docker_failure
        result = execute_fix(_base_state())
        assert result["execution_result"]["stderr"] == "Error: something went wrong\n"

    def test_execution_error_is_none(self, mock_docker_failure):
        mock_docker, mock_container = mock_docker_failure
        result = execute_fix(_base_state())
        assert result["execution_error"] is None

    def test_container_removed(self, mock_docker_failure):
        mock_docker, mock_container = mock_docker_failure
        execute_fix(_base_state())
        mock_container.remove.assert_called_once_with(force=True)


class TestExecuteFixTimeout:
    def test_status_is_timeout(self, mock_docker_timeout):
        mock_docker, mock_container = mock_docker_timeout
        result = execute_fix(_base_state())
        assert result["execution_result"]["status"] == "timeout"

    def test_return_code_is_none(self, mock_docker_timeout):
        mock_docker, mock_container = mock_docker_timeout
        result = execute_fix(_base_state())
        assert result["execution_result"]["return_code"] is None

    def test_stdout_is_empty(self, mock_docker_timeout):
        mock_docker, mock_container = mock_docker_timeout
        result = execute_fix(_base_state())
        assert result["execution_result"]["stdout"] == ""

    def test_container_killed(self, mock_docker_timeout):
        mock_docker, mock_container = mock_docker_timeout
        execute_fix(_base_state())
        mock_container.kill.assert_called_once()

    def test_container_removed_after_kill(self, mock_docker_timeout):
        mock_docker, mock_container = mock_docker_timeout
        execute_fix(_base_state())
        mock_container.remove.assert_called_once_with(force=True)

    def test_execution_error_is_none(self, mock_docker_timeout):
        mock_docker, mock_container = mock_docker_timeout
        result = execute_fix(_base_state())
        assert result["execution_error"] is None


class TestExecuteFixDockerUnavailable:
    def test_execution_result_is_none(self, mock_docker_unavailable):
        result = execute_fix(_base_state())
        assert result["execution_result"] is None

    def test_execution_error_set(self, mock_docker_unavailable):
        result = execute_fix(_base_state())
        assert result["execution_error"] is not None
        assert isinstance(result["execution_error"], str)
        assert len(result["execution_error"]) > 0

    def test_no_container_operations(self, mock_docker_unavailable):
        execute_fix(_base_state())
        mock_docker_unavailable.from_env.return_value.containers.run.assert_not_called()

    def test_does_not_raise(self, mock_docker_unavailable):
        result = execute_fix(_base_state())
        assert result is not None


class TestExecuteFixSkipped:
    def test_status_is_skipped(self, mock_docker_success):
        mock_docker, _ = mock_docker_success
        result = execute_fix(_base_state(fix_script=None))
        assert result["execution_result"]["status"] == "skipped"

    def test_return_code_is_none(self, mock_docker_success):
        mock_docker, _ = mock_docker_success
        result = execute_fix(_base_state(fix_script=None))
        assert result["execution_result"]["return_code"] is None

    def test_execution_error_is_none(self, mock_docker_success):
        mock_docker, _ = mock_docker_success
        result = execute_fix(_base_state(fix_script=None))
        assert result["execution_error"] is None

    def test_docker_not_called(self, mock_docker_success):
        mock_docker, _ = mock_docker_success
        execute_fix(_base_state(fix_script=None))
        mock_docker.from_env.assert_not_called()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_docker_success():
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = [b"hello from sandbox\n", b""]
        yield mock_docker, mock_container


@pytest.fixture
def mock_docker_failure():
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 1}
        mock_container.logs.side_effect = [b"", b"Error: something went wrong\n"]
        yield mock_docker, mock_container


@pytest.fixture
def mock_docker_timeout():
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.side_effect = requests.exceptions.ReadTimeout()
        yield mock_docker, mock_container


@pytest.fixture
def mock_docker_unavailable():
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        mock_docker.from_env.side_effect = docker.errors.DockerException("Cannot connect to Docker daemon")
        yield mock_docker
