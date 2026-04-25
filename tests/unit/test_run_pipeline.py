"""Unit tests for run_pipeline() public API and CLI entry point."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autosentinel import DiagnosticError, run_pipeline
from autosentinel.__main__ import main


# --- run_pipeline() ---

def test_run_pipeline_happy_path(connectivity_state, mock_tool_use_response, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    mock_response = mock_tool_use_response()
    with patch("autosentinel.nodes.analyze_error.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.return_value = mock_response
        result = run_pipeline(connectivity_state["log_path"])
    assert isinstance(result, Path)
    assert result.exists()


def test_run_pipeline_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError, match="nonexistent.json"):
        run_pipeline(tmp_path / "nonexistent.json")


def test_run_pipeline_parse_error_raises_diagnostic_error(tmp_path):
    bad_file = tmp_path / "bad.json"
    bad_file.write_text("not valid json {")
    with pytest.raises(DiagnosticError) as exc_info:
        run_pipeline(bad_file)
    assert "bad.json" in str(exc_info.value)


def test_run_pipeline_analysis_error_raises_diagnostic_error(tmp_path):
    import anthropic as _anthropic

    log = {
        "timestamp": "2026-04-24T10:00:00Z",
        "service_name": "svc",
        "error_type": "Error",
        "message": "boom",
    }
    log_file = tmp_path / "test.json"
    log_file.write_text(json.dumps(log))
    with patch("autosentinel.nodes.analyze_error.anthropic.Anthropic") as mock_cls:
        mock_cls.return_value.messages.create.side_effect = _anthropic.APIConnectionError(
            request=MagicMock()
        )
        with pytest.raises(DiagnosticError):
            run_pipeline(log_file)


# --- main() CLI entry point ---

def test_main_success(tmp_path):
    report = tmp_path / "out-report.md"
    report.write_text("# Report")
    with patch("autosentinel.__main__.run_pipeline", return_value=report) as mock_run:
        with patch.object(sys, "argv", ["autosentinel", str(tmp_path / "test.json")]):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code == 0
    mock_run.assert_called_once()


def test_main_file_not_found(tmp_path):
    with patch(
        "autosentinel.__main__.run_pipeline",
        side_effect=FileNotFoundError("not found"),
    ):
        with patch.object(sys, "argv", ["autosentinel", str(tmp_path / "missing.json")]):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code == 1


def test_main_diagnostic_error(tmp_path):
    with patch(
        "autosentinel.__main__.run_pipeline",
        side_effect=DiagnosticError("pipeline failed"),
    ):
        with patch.object(sys, "argv", ["autosentinel", str(tmp_path / "test.json")]):
            with pytest.raises(SystemExit) as exc_info:
                main()
    assert exc_info.value.code == 1
