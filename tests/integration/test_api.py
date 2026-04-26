"""Integration tests for the Event Gateway API — routes, background processing, and structured logging."""

import asyncio
import json
import time
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest


VALID_PAYLOAD = {
    "service_name": "payment-service",
    "error_type": "ConnectionTimeout",
    "message": "Database connection timed out after 30s",
    "timestamp": "2026-04-25T10:00:00Z",
}


# ---------------------------------------------------------------------------
# US1 — Non-blocking Alert Acceptance (5 route tests)
# ---------------------------------------------------------------------------

def test_post_alert_returns_202(client, mock_pipeline):
    resp = client.post("/api/v1/alerts", json=VALID_PAYLOAD)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "accepted"
    assert "job_id" in body
    assert body["job_id"]


def test_post_alert_missing_field_returns_422(client):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "service_name"}
    resp = client.post("/api/v1/alerts", json=payload)
    assert resp.status_code == 422


def test_post_alert_invalid_json_returns_422(client):
    resp = client.post(
        "/api/v1/alerts",
        content=b"not valid json {",
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 422


def test_post_alert_extra_fields_accepted(client, mock_pipeline):
    payload = {**VALID_PAYLOAD, "unknown_field": "ignored"}
    resp = client.post("/api/v1/alerts", json=payload)
    assert resp.status_code == 202


def test_post_alert_job_ids_are_unique(client, mock_pipeline):
    r1 = client.post("/api/v1/alerts", json=VALID_PAYLOAD)
    r2 = client.post("/api/v1/alerts", json=VALID_PAYLOAD)
    assert r1.json()["job_id"] != r2.json()["job_id"]


# ---------------------------------------------------------------------------
# US2 — Automatic Background Diagnosis (3 background tests)
# ---------------------------------------------------------------------------

def test_background_worker_processes_queued_alert(client, mock_pipeline, tmp_path):
    resp = client.post("/api/v1/alerts", json=VALID_PAYLOAD)
    assert resp.status_code == 202
    from autosentinel.api.queue import get_queue
    queue = get_queue()
    queue.join()
    assert mock_pipeline.exists()


def test_background_worker_handles_pipeline_error(client, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from autosentinel.api.main import create_app
    from starlette.testclient import TestClient

    def _raise(log_path):
        raise RuntimeError("pipeline exploded")

    with patch("autosentinel.api.queue.run_pipeline", side_effect=_raise):
        with TestClient(create_app()) as c:
            resp = c.post("/api/v1/alerts", json=VALID_PAYLOAD)
            assert resp.status_code == 202
            from autosentinel.api.queue import get_queue
            get_queue().join()
            # No unhandled exception — worker survived the error


def test_multiple_alerts_all_processed(client, tmp_path):
    reports = []
    payloads = [
        {**VALID_PAYLOAD, "service_name": f"svc-{i}", "error_type": "ConnectionTimeout"}
        for i in range(10)
    ]

    def _fake(log_path):
        r = tmp_path / f"{Path(log_path).stem}-report.md"
        r.write_text("# Report")
        reports.append(r)
        return r

    with patch("autosentinel.api.queue.run_pipeline", side_effect=_fake):
        for p in payloads:
            resp = client.post("/api/v1/alerts", json=p)
            assert resp.status_code == 202
        from autosentinel.api.queue import get_queue
        get_queue().join()

    assert len(reports) == 10
    assert all(r.exists() for r in reports)


# ---------------------------------------------------------------------------
# US3 — Structured Observability Trace (3 log tests)
# ---------------------------------------------------------------------------

def test_post_alert_emits_alert_received_log(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from autosentinel.api.main import create_app
    from starlette.testclient import TestClient

    captured: list[str] = []

    def _fake(log_path):
        r = tmp_path / "r.md"
        r.write_text("# R")
        return r

    with patch("autosentinel.api.queue.run_pipeline", side_effect=_fake):
        with TestClient(create_app()) as c:
            import autosentinel.api.logging as api_logging
            stream = StringIO()
            logger = api_logging.get_logger("event_gateway")
            original_handler = logger.handlers[0]
            logger.handlers[0].stream = stream

            try:
                resp = c.post("/api/v1/alerts", json=VALID_PAYLOAD)
                assert resp.status_code == 202
                job_id = resp.json()["job_id"]
                from autosentinel.api.queue import get_queue
                get_queue().join()
            finally:
                logger.handlers[0].stream = original_handler.stream

    log_lines = [ln for ln in stream.getvalue().strip().splitlines() if ln]
    events = [json.loads(ln) for ln in log_lines]
    received = [e for e in events if e["event"] == "alert_received"]
    assert received, "Expected alert_received log event"
    e = received[0]
    assert e["correlation_id"] == job_id
    assert e["severity"] == "INFO"
    assert e["component"] == "event_gateway"
    assert "service_name" in e["event_payload"]


def test_post_alert_emits_alert_queued_log_with_depth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from autosentinel.api.main import create_app
    from starlette.testclient import TestClient

    def _fake(log_path):
        r = tmp_path / "r.md"
        r.write_text("# R")
        return r

    with patch("autosentinel.api.queue.run_pipeline", side_effect=_fake):
        with TestClient(create_app()) as c:
            import autosentinel.api.logging as api_logging
            stream = StringIO()
            logger = api_logging.get_logger("event_gateway")
            original_stream = logger.handlers[0].stream
            logger.handlers[0].stream = stream

            try:
                resp = c.post("/api/v1/alerts", json=VALID_PAYLOAD)
                assert resp.status_code == 202
                from autosentinel.api.queue import get_queue
                get_queue().join()
            finally:
                logger.handlers[0].stream = original_stream

    events = [json.loads(ln) for ln in stream.getvalue().strip().splitlines() if ln]
    queued = [e for e in events if e["event"] == "alert_queued"]
    assert queued, "Expected alert_queued log event"
    assert "queue_depth" in queued[0]["event_payload"]


def test_worker_emits_processing_completed_log_with_duration_ms(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from autosentinel.api.main import create_app
    from starlette.testclient import TestClient

    def _fake(log_path):
        r = tmp_path / "r.md"
        r.write_text("# R")
        return r

    with patch("autosentinel.api.queue.run_pipeline", side_effect=_fake):
        with TestClient(create_app()) as c:
            import autosentinel.api.logging as api_logging
            stream = StringIO()
            logger = api_logging.get_logger("event_gateway")
            original_stream = logger.handlers[0].stream
            logger.handlers[0].stream = stream

            try:
                resp = c.post("/api/v1/alerts", json=VALID_PAYLOAD)
                assert resp.status_code == 202
                from autosentinel.api.queue import get_queue
                get_queue().join()
            finally:
                logger.handlers[0].stream = original_stream

    events = [json.loads(ln) for ln in stream.getvalue().strip().splitlines() if ln]
    completed = [e for e in events if e["event"] == "processing_completed"]
    assert completed, "Expected processing_completed log event"
    assert "duration_ms" in completed[0]["event_payload"]
    assert "report_path" in completed[0]["event_payload"]
