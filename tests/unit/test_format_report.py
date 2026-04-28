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
        "fix_script": None,
        "execution_result": None,
        "execution_error": None,
        "report_text": None,
        "report_path": None,
    }


@pytest.fixture
def state_with_execution_success(state_with_analysis):
    state = dict(state_with_analysis)
    state["execution_result"] = {
        "status": "success",
        "return_code": 0,
        "stdout": "Fix applied successfully\n",
        "stderr": "",
        "duration_ms": 342,
        "error": None,
    }
    return state


@pytest.fixture
def state_with_execution_error(state_with_analysis):
    state = dict(state_with_analysis)
    state["execution_error"] = "Cannot connect to Docker daemon"
    return state


@pytest.fixture
def state_with_execution_skipped(state_with_analysis):
    state = dict(state_with_analysis)
    state["execution_result"] = {
        "status": "skipped",
        "return_code": None,
        "stdout": "",
        "stderr": "",
        "duration_ms": 0,
        "error": None,
    }
    return state


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


# ---------------------------------------------------------------------------
# Sprint 3: Sandbox Execution section tests
# ---------------------------------------------------------------------------

def test_sandbox_section_success(state_with_execution_success, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_execution_success)
    text = result["report_text"]
    assert "## Sandbox Execution" in text
    assert "**Status**: success" in text
    assert "**Return code**: 0" in text
    assert "Fix applied successfully" in text


def test_sandbox_section_execution_error(state_with_execution_error, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_execution_error)
    text = result["report_text"]
    assert "## Sandbox Execution" in text
    assert "**Status**: error" in text
    assert "Cannot connect to Docker daemon" in text


def test_sandbox_section_skipped(state_with_execution_skipped, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_execution_skipped)
    text = result["report_text"]
    assert "## Sandbox Execution" in text
    assert "skipped" in text


# ---------------------------------------------------------------------------
# Sprint 4: Security Review section tests
# ---------------------------------------------------------------------------

@pytest.fixture
def state_with_safe_verdict(state_with_execution_success):
    state = dict(state_with_execution_success)
    state["error_category"] = "CODE"
    state["fix_artifact"] = 'print("fix applied")'
    state["security_verdict"] = "SAFE"
    state["routing_decision"] = "CODE → CodeFixerAgent"
    state["agent_trace"] = ["DiagnosisAgent", "SupervisorAgent", "CodeFixerAgent", "SecurityReviewerAgent", "VerifierAgent"]
    state["approval_required"] = False
    return state


@pytest.fixture
def state_with_caution_verdict(state_with_execution_success):
    state = dict(state_with_execution_success)
    state["error_category"] = "CODE"
    state["fix_artifact"] = 'print("fix applied")'
    state["security_verdict"] = "CAUTION"
    state["routing_decision"] = "CODE → CodeFixerAgent"
    state["agent_trace"] = ["DiagnosisAgent", "SupervisorAgent", "CodeFixerAgent", "SecurityReviewerAgent", "VerifierAgent"]
    state["approval_required"] = False
    return state


@pytest.fixture
def state_with_high_risk_approved(state_with_execution_success):
    state = dict(state_with_execution_success)
    state["error_category"] = "SECURITY"
    state["fix_artifact"] = "DROP TABLE users"
    state["security_verdict"] = "HIGH_RISK"
    state["routing_decision"] = "SECURITY → CodeFixerAgent"
    state["agent_trace"] = ["DiagnosisAgent", "SupervisorAgent", "CodeFixerAgent", "SecurityReviewerAgent", "VerifierAgent"]
    state["approval_required"] = True
    return state


def test_security_section_safe_no_badge(state_with_safe_verdict, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_safe_verdict)
    text = result["report_text"]
    assert "## Security Review" in text
    assert "SAFE" in text
    assert "⚠ CAUTION" not in text
    assert "HIGH RISK" not in text


def test_security_section_caution_badge(state_with_caution_verdict, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_caution_verdict)
    text = result["report_text"]
    assert "## Security Review" in text
    assert "⚠ CAUTION" in text


def test_security_section_high_risk_badge(state_with_high_risk_approved, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = format_report(state_with_high_risk_approved)
    text = result["report_text"]
    assert "## Security Review" in text
    assert "HIGH RISK" in text
