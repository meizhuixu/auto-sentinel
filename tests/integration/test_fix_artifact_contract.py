"""Integration: fix-artifact contract end-to-end (Sprint 6 T006).

A MockLLMClient CodeFixer that persistently emits a bare-`return` fragment
must no longer produce a format-induced sandbox failure: the producer retries
once (same fragment — the mock is persistent), passes it through, and the
Verifier's deterministic normalization wraps it so the sandbox executes it.

Hermetic: D2 `agents=` seam + MockLLMClient + mocked docker — zero
real-provider traffic, zero spend (contracts/fix-artifact.md, spec.md US1).
"""

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autosentinel.models import AgentState
from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.integration._pr4_helpers import (
    build_fixture_clients,
    build_injected_agents,
)

_FRAGMENT = "value = {'user_id': 42}.get('user_id')\nreturn"


def _write_log(tmp_path: Path) -> Path:
    log_file = tmp_path / "key_error.json"
    log_file.write_text(json.dumps({
        "timestamp": "2026-07-03T00:00:00Z",
        "service_name": "payments",
        "error_type": "KeyError",
        "message": "'user_id'",
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
def cfg():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def _docker_capture(mock_docker) -> dict:
    """containers.run double: exit 0 + capture the mounted fix.py content."""
    captured: dict = {}

    def _run(image, command, **kwargs):
        captured["command"] = command
        for host_path in (kwargs.get("volumes") or {}):
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


class TestFragmentSurvivesPipeline:
    def test_bare_return_fragment_reaches_sandbox_and_succeeds(self, cfg, tmp_path):
        clients = build_fixture_clients(code_fixer_artifact=_FRAGMENT)
        graph = build_multi_agent_graph(agents=build_injected_agents(clients))
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            captured = _docker_capture(mock_docker)
            result = graph.invoke(_initial_state(_write_log(tmp_path)), cfg)

        # pipeline completed and the sandbox actually executed the fix
        assert result["execution_error"] is None
        assert result["execution_result"]["status"] == "success"
        # what ran is the WRAPPED form — not the raw fragment, not `python -c`
        assert captured["command"] == ["python", "/workspace/fix.py"]
        assert "def __autosentinel_fix__" in captured["file_content"]
        assert "return" in captured["file_content"]

    def test_normalization_outcome_recorded_in_final_state(self, cfg, tmp_path):
        clients = build_fixture_clients(code_fixer_artifact=_FRAGMENT)
        graph = build_multi_agent_graph(agents=build_injected_agents(clients))
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            _docker_capture(mock_docker)
            result = graph.invoke(_initial_state(_write_log(tmp_path)), cfg)
        assert result["fix_normalization"]["outcome"] == "wrapped"

    def test_producer_retried_exactly_once_on_fragment(self, cfg, tmp_path):
        clients = build_fixture_clients(code_fixer_artifact=_FRAGMENT)
        graph = build_multi_agent_graph(agents=build_injected_agents(clients))
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            _docker_capture(mock_docker)
            graph.invoke(_initial_state(_write_log(tmp_path)), cfg)
        # persistent mock keeps returning the fragment: 1 original + 1 retry
        assert clients["code_fixer"].call_count == 2


class TestGenuinelyBrokenFixStillFailsHonestly:
    def test_nonzero_exit_reports_failure(self, cfg, tmp_path):
        """The contract fix must not mask real fix defects (spec US1 AC-2)."""
        clients = build_fixture_clients(
            code_fixer_artifact='raise RuntimeError("fix does not work")'
        )
        graph = build_multi_agent_graph(agents=build_injected_agents(clients))
        with patch("autosentinel.agents.verifier.docker") as mock_docker:
            mock_client = MagicMock()
            mock_container = MagicMock()
            mock_docker.from_env.return_value = mock_client
            mock_client.containers.run.return_value = mock_container
            mock_container.wait.return_value = {"StatusCode": 1}
            mock_container.logs.side_effect = [b"", b"RuntimeError: fix does not work\n"]
            result = graph.invoke(_initial_state(_write_log(tmp_path)), cfg)
        assert result["execution_result"]["status"] == "failure"
        assert result["fix_normalization"]["outcome"] == "verbatim"
