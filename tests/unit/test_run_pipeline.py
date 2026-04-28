"""Unit tests for run_pipeline() public API and CLI entry point."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autosentinel import DiagnosticError, run_pipeline
from autosentinel.__main__ import main


# --- run_pipeline() ---

def test_run_pipeline_happy_path(connectivity_state, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_pipeline(connectivity_state["log_path"])
    assert isinstance(result, Path)
    assert result.exists()


def test_run_pipeline_multi_agent_flag(connectivity_state, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AUTOSENTINEL_MULTI_AGENT", "1")
    with patch("autosentinel.agents.verifier.docker") as md:
        mock_client = MagicMock()
        mock_container = MagicMock()
        md.from_env.return_value = mock_client
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = [b"OK\n", b""]
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


def test_run_pipeline_returns_existing_report(connectivity_state, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_pipeline(connectivity_state["log_path"])
    assert result.suffix == ".md"
    assert "report" in result.name


def test_run_pipeline_analysis_error_raises_diagnostic_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import json
    log = {
        "timestamp": "2026-04-25T10:00:00Z",
        "service_name": "svc",
        "error_type": "Error",
        "message": "boom",
    }
    log_file = tmp_path / "test.json"
    log_file.write_text(json.dumps(log))
    # Patch the name in graph.py's namespace so build_graph() picks up the mock.
    with patch(
        "autosentinel.graph.analyze_error",
        return_value={"analysis_result": None, "analysis_error": "mock analysis failure"},
    ):
        with pytest.raises(DiagnosticError, match="mock analysis failure"):
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
