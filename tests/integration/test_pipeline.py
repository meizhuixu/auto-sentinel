"""Integration tests for the full diagnostic pipeline."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autosentinel.graph import build_graph


def test_full_pipeline_happy_path(connectivity_state, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        _setup_docker_success(mock_docker)
        graph = build_graph()
        result = graph.invoke(connectivity_state)

    assert result["parse_error"] is None
    assert result["analysis_error"] is None
    assert result["error_log"] is not None
    assert result["analysis_result"] is not None
    assert result["report_text"] is not None
    assert result["report_path"] is not None


def test_pipeline_node_execution_order(connectivity_state, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        _setup_docker_success(mock_docker)
        graph = build_graph()
        executed_nodes = []
        for chunk in graph.stream(connectivity_state):
            executed_nodes.extend(chunk.keys())

    assert executed_nodes == ["parse_log", "analyze_error", "execute_fix", "format_report"]


def test_pipeline_routes_to_end_on_parse_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {")
    state = {
        "log_path": str(bad_file),
        "error_log": None,
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "fix_script": None,
        "execution_result": None,
        "execution_error": None,
        "report_text": None,
        "report_path": None,
    }
    graph = build_graph()
    result = graph.invoke(state)

    assert result["parse_error"] is not None
    assert result["analysis_result"] is None
    assert result["report_text"] is None


def test_pipeline_report_contains_sandbox_section(connectivity_state, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        _setup_docker_success(mock_docker)
        graph = build_graph()
        result = graph.invoke(connectivity_state)

    report_path = Path(result["report_path"])
    assert report_path.exists()
    report_text = report_path.read_text()
    assert "## Sandbox Execution" in report_text


def test_pipeline_continues_when_docker_unavailable(connectivity_state, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import docker.errors
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        mock_docker.from_env.side_effect = docker.errors.DockerException("daemon unavailable")
        graph = build_graph()
        result = graph.invoke(connectivity_state)

    assert result["report_text"] is not None
    assert result["report_path"] is not None
    assert result["execution_error"] is not None
    assert result["execution_result"] is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_docker_success(mock_docker):
    mock_client = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_container = MagicMock()
    mock_client.containers.run.return_value = mock_container
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = [b"Fix applied\n", b""]
