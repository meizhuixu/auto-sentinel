"""Unit tests for the analyze_error node."""

import pytest

from autosentinel.nodes.analyze_error import analyze_error


def test_analyze_error_happy_path(populated_connectivity_state):
    result = analyze_error(populated_connectivity_state)

    assert result["analysis_error"] is None
    assert result["analysis_result"] is not None
    assert result["analysis_result"]["error_category"] == "connectivity"
    assert 0.0 <= result["analysis_result"]["confidence"] <= 1.0
    assert len(result["analysis_result"]["remediation_steps"]) >= 1
    assert result["analysis_result"]["root_cause_hypothesis"]


def test_analyze_error_classifies_connectivity(populated_connectivity_state):
    result = analyze_error(populated_connectivity_state)
    assert result["analysis_result"]["error_category"] == "connectivity"


def test_analyze_error_classifies_resource_exhaustion(resource_state):
    state = dict(resource_state)
    state["error_log"] = {
        "timestamp": "2026-04-25T11:00:00Z",
        "service_name": "order-processor",
        "error_type": "OOMKilled",
        "message": "Container killed: memory limit of 512Mi exceeded",
        "stack_trace": None,
    }
    result = analyze_error(state)
    assert result["analysis_result"]["error_category"] == "resource_exhaustion"


def test_analyze_error_classifies_configuration(config_state):
    state = dict(config_state)
    state["error_log"] = {
        "timestamp": "2026-04-25T09:30:00Z",
        "service_name": "auth-service",
        "error_type": "ConfigurationError",
        "message": "Required environment variable JWT_SECRET_KEY is not set",
        "stack_trace": None,
    }
    result = analyze_error(state)
    assert result["analysis_result"]["error_category"] == "configuration"


def test_analyze_error_fallback_to_application_logic(populated_connectivity_state):
    state = dict(populated_connectivity_state)
    state["error_log"] = {
        "timestamp": "2026-04-25T10:00:00Z",
        "service_name": "svc",
        "error_type": "NullPointerException",
        "message": "Unexpected null value in payment handler",
        "stack_trace": None,
    }
    result = analyze_error(state)
    assert result["analysis_result"]["error_category"] == "application_logic"


def test_analyze_error_result_schema(populated_connectivity_state):
    result = analyze_error(populated_connectivity_state)
    ar = result["analysis_result"]
    assert ar["error_category"] in (
        "connectivity", "resource_exhaustion", "configuration", "application_logic"
    )
    assert isinstance(ar["root_cause_hypothesis"], str) and ar["root_cause_hypothesis"]
    assert isinstance(ar["confidence"], float)
    assert 0.0 <= ar["confidence"] <= 1.0
    assert isinstance(ar["remediation_steps"], list)
    assert len(ar["remediation_steps"]) >= 1
