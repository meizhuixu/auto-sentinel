"""Shared pytest fixtures for the diagnostic pipeline test suite."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from autosentinel.models import DiagnosticState


@pytest.fixture
def connectivity_state(tmp_path) -> DiagnosticState:
    """DiagnosticState with log_path pointing to a connectivity crash log."""
    log = {
        "timestamp": "2026-04-24T10:15:00Z",
        "service_name": "payment-service",
        "error_type": "ConnectionTimeout",
        "message": "Database connection timed out after 30s waiting for host db.internal:5432",
        "stack_trace": "Traceback (most recent call last):\n  File 'db.py', line 42, in connect\n    raise ConnectionTimeout('db.internal:5432 unreachable')",
    }
    log_file = tmp_path / "crash-connectivity.json"
    log_file.write_text(json.dumps(log))
    return DiagnosticState(
        log_path=str(log_file),
        error_log=None,
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
        report_text=None,
        report_path=None,
    )


@pytest.fixture
def resource_state(tmp_path) -> DiagnosticState:
    """DiagnosticState with log_path pointing to a resource exhaustion log."""
    log = {
        "timestamp": "2026-04-24T11:00:00Z",
        "service_name": "order-processor",
        "error_type": "OOMKilled",
        "message": "Container killed: memory limit of 512Mi exceeded",
        "stack_trace": None,
    }
    log_file = tmp_path / "crash-resource.json"
    log_file.write_text(json.dumps(log))
    return DiagnosticState(
        log_path=str(log_file),
        error_log=None,
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
        report_text=None,
        report_path=None,
    )


@pytest.fixture
def config_state(tmp_path) -> DiagnosticState:
    """DiagnosticState with log_path pointing to a configuration error log."""
    log = {
        "timestamp": "2026-04-24T09:30:00Z",
        "service_name": "auth-service",
        "error_type": "ConfigurationError",
        "message": "Required environment variable JWT_SECRET_KEY is not set",
        "stack_trace": None,
    }
    log_file = tmp_path / "crash-config.json"
    log_file.write_text(json.dumps(log))
    return DiagnosticState(
        log_path=str(log_file),
        error_log=None,
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
        report_text=None,
        report_path=None,
    )


@pytest.fixture
def populated_connectivity_state(connectivity_state) -> DiagnosticState:
    """DiagnosticState with error_log already populated (post-parse_log)."""
    state = dict(connectivity_state)
    state["error_log"] = {
        "timestamp": "2026-04-24T10:15:00Z",
        "service_name": "payment-service",
        "error_type": "ConnectionTimeout",
        "message": "Database connection timed out after 30s waiting for host db.internal:5432",
        "stack_trace": "Traceback (most recent call last):\n  File 'db.py', line 42, in connect\n    raise ConnectionTimeout('db.internal:5432 unreachable')",
    }
    return DiagnosticState(**state)


@pytest.fixture
def mock_tool_use_response():
    """Factory that returns a mock Anthropic Message with a tool_use block."""
    def _factory(
        error_category: str = "connectivity",
        root_cause_hypothesis: str = "Database host unreachable due to network partition",
        confidence: float = 0.92,
        remediation_steps: list[str] | None = None,
    ) -> MagicMock:
        if remediation_steps is None:
            remediation_steps = ["Check DB host DNS resolution", "Verify firewall rules"]
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "diagnose_error"
        tool_use_block.input = {
            "error_category": error_category,
            "root_cause_hypothesis": root_cause_hypothesis,
            "confidence": confidence,
            "remediation_steps": remediation_steps,
        }
        response = MagicMock()
        response.content = [tool_use_block]
        return response
    return _factory
