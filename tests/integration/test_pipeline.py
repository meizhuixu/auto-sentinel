"""Integration tests for the full diagnostic pipeline."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autosentinel.graph import build_graph


def test_full_pipeline_happy_path(connectivity_state, mock_tool_use_response, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_response = mock_tool_use_response(error_category="connectivity")
    with patch("autosentinel.nodes.analyze_error.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        graph = build_graph()
        result = graph.invoke(connectivity_state)

    assert result["parse_error"] is None
    assert result["analysis_error"] is None
    assert result["error_log"] is not None
    assert result["analysis_result"] is not None
    assert result["report_text"] is not None
    assert result["report_path"] is not None


def test_pipeline_node_execution_order(connectivity_state, mock_tool_use_response, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_response = mock_tool_use_response()
    executed_nodes = []
    with patch("autosentinel.nodes.analyze_error.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        graph = build_graph()
        for chunk in graph.stream(connectivity_state):
            executed_nodes.extend(chunk.keys())

    assert executed_nodes == ["parse_log", "analyze_error", "format_report"]


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
        "report_text": None,
        "report_path": None,
    }
    graph = build_graph()
    result = graph.invoke(state)

    assert result["parse_error"] is not None
    assert result["analysis_result"] is None
    assert result["report_text"] is None
