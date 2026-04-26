"""Unit tests for AlertPayload and AlertJobResponse Pydantic models."""

import pytest
from pydantic import ValidationError


def test_alert_payload_valid():
    from autosentinel.api.models import AlertPayload
    p = AlertPayload(
        service_name="svc",
        error_type="Timeout",
        message="timed out",
        timestamp="2026-04-25T10:00:00Z",
    )
    assert p.service_name == "svc"
    assert p.stack_trace is None


def test_alert_payload_stack_trace_defaults_to_none():
    from autosentinel.api.models import AlertPayload
    p = AlertPayload(service_name="s", error_type="e", message="m", timestamp="t")
    assert p.stack_trace is None


def test_alert_payload_stack_trace_accepted_when_provided():
    from autosentinel.api.models import AlertPayload
    p = AlertPayload(service_name="s", error_type="e", message="m", timestamp="t", stack_trace="trace")
    assert p.stack_trace == "trace"


def test_alert_payload_missing_service_name_raises():
    from autosentinel.api.models import AlertPayload
    with pytest.raises(ValidationError):
        AlertPayload(error_type="e", message="m", timestamp="t")


def test_alert_payload_missing_error_type_raises():
    from autosentinel.api.models import AlertPayload
    with pytest.raises(ValidationError):
        AlertPayload(service_name="s", message="m", timestamp="t")


def test_alert_payload_missing_message_raises():
    from autosentinel.api.models import AlertPayload
    with pytest.raises(ValidationError):
        AlertPayload(service_name="s", error_type="e", timestamp="t")


def test_alert_payload_missing_timestamp_raises():
    from autosentinel.api.models import AlertPayload
    with pytest.raises(ValidationError):
        AlertPayload(service_name="s", error_type="e", message="m")


def test_alert_payload_extra_fields_ignored():
    from autosentinel.api.models import AlertPayload
    p = AlertPayload(
        service_name="s", error_type="e", message="m", timestamp="t",
        unknown_field="ignored",
    )
    assert not hasattr(p, "unknown_field")


def test_alert_job_response_fields():
    from autosentinel.api.models import AlertJobResponse
    r = AlertJobResponse(job_id="abc-123", status="accepted", message="Alert accepted for processing")
    assert r.job_id == "abc-123"
    assert r.status == "accepted"
    assert r.message == "Alert accepted for processing"


def test_alert_job_response_missing_job_id_raises():
    from autosentinel.api.models import AlertJobResponse
    with pytest.raises(ValidationError):
        AlertJobResponse(status="accepted", message="msg")
