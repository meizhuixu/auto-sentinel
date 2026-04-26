"""Unit tests for the JSONFormatter and get_logger utility."""

import json
import logging
import sys
from io import StringIO

import pytest


def test_json_formatter_output_is_valid_json():
    from autosentinel.api.logging import get_logger
    stream = StringIO()
    logger = get_logger("test_component")
    logger.handlers[0].stream = stream
    logger.info("test event", extra={
        "correlation_id": "job-1",
        "trace_id": "job-1",
        "event": "alert_received",
        "event_payload": {"service_name": "svc"},
    })
    line = stream.getvalue().strip()
    parsed = json.loads(line)
    assert isinstance(parsed, dict)


def test_json_formatter_contains_all_schema_fields():
    from autosentinel.api.logging import get_logger
    stream = StringIO()
    logger = get_logger("event_gateway")
    logger.handlers[0].stream = stream
    logger.info("event", extra={
        "correlation_id": "job-abc",
        "trace_id": "job-abc",
        "event": "alert_queued",
        "event_payload": {"service_name": "svc", "queue_depth": 1},
    })
    parsed = json.loads(stream.getvalue().strip())
    for field in ("timestamp", "severity", "component", "correlation_id", "trace_id", "event", "event_payload"):
        assert field in parsed, f"Missing field: {field}"


def test_json_formatter_severity_info():
    from autosentinel.api.logging import get_logger
    stream = StringIO()
    logger = get_logger("event_gateway")
    logger.handlers[0].stream = stream
    logger.info("msg", extra={"correlation_id": "j", "trace_id": "j", "event": "e", "event_payload": {}})
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["severity"] == "INFO"


def test_json_formatter_severity_error():
    from autosentinel.api.logging import get_logger
    stream = StringIO()
    logger = get_logger("event_gateway")
    logger.handlers[0].stream = stream
    logger.error("err", extra={"correlation_id": "j", "trace_id": "j", "event": "e", "event_payload": {}})
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["severity"] == "ERROR"


def test_json_formatter_component_field():
    from autosentinel.api.logging import get_logger
    stream = StringIO()
    logger = get_logger("event_gateway")
    logger.handlers[0].stream = stream
    logger.info("msg", extra={"correlation_id": "j", "trace_id": "j", "event": "e", "event_payload": {}})
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["component"] == "event_gateway"


def test_json_formatter_correlation_and_trace_id():
    from autosentinel.api.logging import get_logger
    stream = StringIO()
    logger = get_logger("event_gateway")
    logger.handlers[0].stream = stream
    logger.info("msg", extra={"correlation_id": "my-job", "trace_id": "my-job", "event": "e", "event_payload": {}})
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["correlation_id"] == "my-job"
    assert parsed["trace_id"] == "my-job"


def test_json_formatter_event_payload_preserved():
    from autosentinel.api.logging import get_logger
    stream = StringIO()
    logger = get_logger("event_gateway")
    logger.handlers[0].stream = stream
    payload = {"service_name": "payment-service", "queue_depth": 3}
    logger.info("msg", extra={"correlation_id": "j", "trace_id": "j", "event": "alert_queued", "event_payload": payload})
    parsed = json.loads(stream.getvalue().strip())
    assert parsed["event_payload"] == payload
