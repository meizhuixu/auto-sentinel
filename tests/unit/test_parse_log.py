"""Unit tests for the parse_log node."""

import json

import pytest

from autosentinel.nodes.parse_log import parse_log


def test_parse_log_happy_path(connectivity_state):
    result = parse_log(connectivity_state)
    assert result["parse_error"] is None
    assert result["error_log"] is not None
    assert result["error_log"]["service_name"] == "payment-service"
    assert result["error_log"]["error_type"] == "ConnectionTimeout"
    assert result["error_log"]["timestamp"] == "2026-04-24T10:15:00Z"
    assert "db.internal:5432" in result["error_log"]["message"]


def test_parse_log_invalid_json(tmp_path):
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
    result = parse_log(state)
    assert result["error_log"] is None
    assert result["parse_error"] is not None
    assert "bad.json" in result["parse_error"]


def test_parse_log_missing_required_field(tmp_path):
    log = {
        "timestamp": "2026-04-24T10:00:00Z",
        "error_type": "SomeError",
        "message": "something went wrong",
    }
    log_file = tmp_path / "missing-field.json"
    log_file.write_text(json.dumps(log))
    state = {
        "log_path": str(log_file),
        "error_log": None,
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "report_text": None,
        "report_path": None,
    }
    result = parse_log(state)
    assert result["error_log"] is None
    assert result["parse_error"] is not None
    assert "service_name" in result["parse_error"]


def test_parse_log_missing_file(tmp_path):
    state = {
        "log_path": str(tmp_path / "nonexistent.json"),
        "error_log": None,
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "report_text": None,
        "report_path": None,
    }
    result = parse_log(state)
    assert result["error_log"] is None
    assert result["parse_error"] is not None


def test_parse_log_optional_stack_trace_absent(tmp_path):
    log = {
        "timestamp": "2026-04-24T10:00:00Z",
        "service_name": "svc",
        "error_type": "Error",
        "message": "boom",
    }
    log_file = tmp_path / "no-trace.json"
    log_file.write_text(json.dumps(log))
    state = {
        "log_path": str(log_file),
        "error_log": None,
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "report_text": None,
        "report_path": None,
    }
    result = parse_log(state)
    assert result["parse_error"] is None
    assert result["error_log"]["stack_trace"] is None
