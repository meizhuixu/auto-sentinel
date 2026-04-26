"""Unit tests for the format_report node."""

from pathlib import Path

import pytest

from autosentinel.nodes.format_report import format_report


@pytest.fixture
def state_with_analysis(tmp_path):
    log_path = tmp_path / "crash-connectivity.json"
    log_path.write_text("{}")
    return {
        "log_path": str(log_path),
        "error_log": {
            "timestamp": "2026-04-24T10:15:00Z",
            "service_name": "payment-service",
            "error_type": "ConnectionTimeout",
            "message": "DB timed out",
            "stack_trace": None,
        },
        "parse_error": None,
        "analysis_result": {
            "error_category": "connectivity",
            "root_cause_hypothesis": "Database host unreachable due to network partition.",
            "confidence": 0.92,
            "remediation_steps": ["Check DNS", "Verify firewall rules"],
        },
        "analysis_error": None,
        "report_text": None,
        "report_path": None,
    }


def test_format_report_happy_path(state_with_analysis, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_analysis)

    assert result["report_text"] is not None
    assert result["report_path"] is not None
    assert result["report_path"].endswith("-report.md")
    assert "## Root Cause Analysis" in result["report_text"]
    assert "connectivity" in result["report_text"]
    assert "payment-service" in result["report_text"]
    assert "Check DNS" in result["report_text"]


def test_format_report_creates_output_dir(state_with_analysis, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_analysis)
    assert Path(result["report_path"]).exists()


def test_format_report_output_naming(state_with_analysis, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_analysis)
    report_name = Path(result["report_path"]).name
    assert report_name == "crash-connectivity-report.md"


def test_format_report_idempotent(state_with_analysis, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result1 = format_report(state_with_analysis)
    result2 = format_report(state_with_analysis)
    assert result1["report_path"] == result2["report_path"]
    assert result1["report_text"] == result2["report_text"]
