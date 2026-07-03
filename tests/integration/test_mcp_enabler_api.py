"""Integration tests for the M4 MCP-enabler API surface (specs/m4-mcp-enabler).

Covers FR-002..FR-005: optional X-Trace-Id on POST /api/v1/alerts,
GET /api/v1/alerts/{job_id} status polling, and GET /api/v1/incidents
keyword search. Follows tests/integration/test_api.py patterns (the `client`
fixture chdirs into tmp_path, so `data/incoming/` and `output/` are
test-local).
"""

import asyncio
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest


VALID_PAYLOAD = {
    "service_name": "payment-service",
    "error_type": "ConnectionTimeout",
    "message": "Database connection timed out after 30s",
    "timestamp": "2026-07-03T10:00:00Z",
}

TRACE_ID = "deadbeef" * 4  # valid ^[0-9a-f]{32}$


def _drain(client) -> None:
    """Block the test thread until the app's queue is fully drained."""
    future = asyncio.run_coroutine_threadsafe(
        client.app.state.queue.join(),
        client.app.state.loop,
    )
    future.result(timeout=10.0)


def _write_result_sidecar(job_id: str, **overrides) -> dict:
    """Fabricate a completed output/{job_id}-result.json (CWD is tmp_path)."""
    data = {
        "trace_id": job_id,
        "status": "completed",
        "diagnosis": {
            "category": "runtime",
            "severity": "medium",
            "summary": "KeyError on missing dict key in payment-service.",
        },
        "fix": {
            "fix_plan": "Use dict.get with a default instead of [] access.",
            "risk_level": "low",
            "code_diff": "",
        },
        "service_name": "payment-service",
        "error_type": "KeyError",
        "report_path": f"/abs/output/{job_id}-report.md",
    }
    data.update(overrides)
    out = Path("output")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{job_id}-result.json").write_text(json.dumps(data), encoding="utf-8")
    return data


# ---------------------------------------------------------------------------
# FR-005 — optional X-Trace-Id header on POST /api/v1/alerts
# ---------------------------------------------------------------------------

def test_post_alert_with_valid_x_trace_id_uses_it_as_job_and_trace_id(client, mock_pipeline):
    resp = client.post(
        "/api/v1/alerts", json=VALID_PAYLOAD, headers={"X-Trace-Id": TRACE_ID}
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"] == TRACE_ID
    assert body["trace_id"] == TRACE_ID
    _drain(client)
    assert (Path("data/incoming") / f"{TRACE_ID}.json").exists()


@pytest.mark.parametrize(
    "bad_header",
    [
        "not-hex",
        "DEADBEEF" * 4,                            # uppercase rejected
        "abc123",                                   # too short
        "deadbeef" * 4 + "00",                      # too long
        "123e4567-e89b-12d3-a456-426614174000",     # uuid form rejected
    ],
)
def test_post_alert_with_invalid_x_trace_id_returns_400(client, bad_header):
    resp = client.post(
        "/api/v1/alerts", json=VALID_PAYLOAD, headers={"X-Trace-Id": bad_header}
    )
    assert resp.status_code == 400
    assert "X-Trace-Id" in resp.json()["detail"]
    assert "32" in resp.json()["detail"]


def test_post_alert_without_x_trace_id_generates_32hex_id(client, mock_pipeline):
    resp = client.post("/api/v1/alerts", json=VALID_PAYLOAD)
    assert resp.status_code == 202
    body = resp.json()
    assert re.fullmatch(r"[0-9a-f]{32}", body["job_id"])
    assert body["trace_id"] == body["job_id"]


# ---------------------------------------------------------------------------
# FR-003 — GET /api/v1/alerts/{job_id}
# ---------------------------------------------------------------------------

def test_get_alert_completed_returns_sidecar_content(client):
    _write_result_sidecar(TRACE_ID)
    resp = client.get(f"/api/v1/alerts/{TRACE_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == TRACE_ID
    assert body["trace_id"] == TRACE_ID
    assert body["status"] == "completed"
    assert body["diagnosis"] == {
        "category": "runtime",
        "severity": "medium",
        "summary": "KeyError on missing dict key in payment-service.",
    }
    assert body["fix"] == {
        "fix_plan": "Use dict.get with a default instead of [] access.",
        "risk_level": "low",
        "code_diff": "",
    }
    assert body["report_path"] == f"/abs/output/{TRACE_ID}-report.md"


def test_get_alert_processing_when_only_incoming_exists(client):
    incoming = Path("data/incoming")
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / f"{TRACE_ID}.json").write_text(json.dumps(VALID_PAYLOAD))
    resp = client.get(f"/api/v1/alerts/{TRACE_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "job_id": TRACE_ID,
        "trace_id": TRACE_ID,
        "status": "processing",
        "diagnosis": None,
        "fix": None,
        "report_path": None,
    }


def test_get_alert_unknown_job_id_returns_404(client):
    resp = client.get(f"/api/v1/alerts/{'0' * 32}")
    assert resp.status_code == 404


def test_get_alert_failed_after_pipeline_error(client):
    """Worker failure must surface as status=failed, not eternal processing."""

    def _raise(log_path, *, trace_id=None):
        raise RuntimeError("pipeline exploded")

    with patch("autosentinel.api.queue.run_pipeline", side_effect=_raise):
        resp = client.post(
            "/api/v1/alerts", json=VALID_PAYLOAD, headers={"X-Trace-Id": TRACE_ID}
        )
        assert resp.status_code == 202
        _drain(client)

    resp = client.get(f"/api/v1/alerts/{TRACE_ID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    assert body["trace_id"] == TRACE_ID
    assert body["diagnosis"] is None
    assert body["fix"] is None
    assert body["report_path"] is None


# ---------------------------------------------------------------------------
# FR-004 — GET /api/v1/incidents keyword search
# ---------------------------------------------------------------------------

def _seed_two_incidents() -> tuple[str, str]:
    key_error_id = "aa" * 16
    oom_id = "bb" * 16
    _write_result_sidecar(key_error_id, trace_id=key_error_id)
    _write_result_sidecar(
        oom_id,
        trace_id=oom_id,
        service_name="order-processor",
        error_type="OOMKilled",
        diagnosis={
            "category": "infra",
            "severity": "medium",
            "summary": "Container killed: memory limit exceeded.",
        },
        fix={
            "fix_plan": "Raise the memory limit to 1Gi.",
            "risk_level": "medium",
            "code_diff": "",
        },
    )
    return key_error_id, oom_id


def test_search_incidents_happy_path_ranked(client):
    key_error_id, oom_id = _seed_two_incidents()
    resp = client.get("/api/v1/incidents", params={"q": "KeyError payment-service"})
    assert resp.status_code == 200
    incidents = resp.json()["incidents"]
    # The OOM incident matches no query term (score 0) and is excluded.
    assert [i["id"] for i in incidents] == [key_error_id]
    assert oom_id not in [i["id"] for i in incidents]
    top = incidents[0]
    assert top["title"] == "KeyError in payment-service"
    assert top["resolution"] == "Use dict.get with a default instead of [] access."


def test_search_incidents_matches_incoming_payload_message(client):
    """Terms found only in the stored data/incoming payload still match."""
    job_id = "cc" * 16
    _write_result_sidecar(job_id, trace_id=job_id)
    incoming = Path("data/incoming")
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / f"{job_id}.json").write_text(
        json.dumps({**VALID_PAYLOAD, "message": "zorblatt overflow detected"})
    )
    resp = client.get("/api/v1/incidents", params={"q": "zorblatt"})
    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()["incidents"]] == [job_id]


def test_search_incidents_no_match_returns_empty_list(client):
    _seed_two_incidents()
    resp = client.get("/api/v1/incidents", params={"q": "totally-unrelated-term"})
    assert resp.status_code == 200
    assert resp.json() == {"incidents": []}


def test_search_incidents_limit_defaults_to_5(client):
    for i in range(7):
        job_id = f"{i:02d}" * 16
        _write_result_sidecar(job_id, trace_id=job_id)
    resp = client.get("/api/v1/incidents", params={"q": "KeyError"})
    assert resp.status_code == 200
    assert len(resp.json()["incidents"]) == 5


@pytest.mark.parametrize(("raw_limit", "effective"), [(0, 1), (-3, 1), (100, 6)])
def test_search_incidents_limit_clamped_1_to_50(client, raw_limit, effective):
    for i in range(6):
        job_id = f"{i:02d}" * 16
        _write_result_sidecar(job_id, trace_id=job_id)
    resp = client.get(
        "/api/v1/incidents", params={"q": "KeyError", "limit": raw_limit}
    )
    assert resp.status_code == 200, "out-of-range limit is clamped, not a 422"
    assert len(resp.json()["incidents"]) == effective


def test_search_incidents_title_and_resolution_fallbacks(client):
    # No error_type/service_name -> title falls back to the summary head;
    # no fix_plan -> resolution falls back to the summary.
    job_id = "dd" * 16
    _write_result_sidecar(
        job_id,
        trace_id=job_id,
        service_name="",
        error_type="",
        diagnosis={"category": "unknown", "severity": "medium",
                   "summary": "Mystery crash mentioning flurbwig."},
        fix={"fix_plan": "", "risk_level": "medium", "code_diff": ""},
    )
    resp = client.get("/api/v1/incidents", params={"q": "flurbwig"})
    incidents = resp.json()["incidents"]
    assert incidents[0]["title"] == "Mystery crash mentioning flurbwig."
    assert incidents[0]["resolution"] == "Mystery crash mentioning flurbwig."


def test_search_incidents_title_falls_back_to_id_when_no_summary(client):
    job_id = "ee" * 16
    _write_result_sidecar(
        job_id,
        trace_id=job_id,
        service_name="",
        error_type="",
        diagnosis={"category": "unknown", "severity": "medium", "summary": ""},
        fix={"fix_plan": "grumbly fix plan", "risk_level": "medium",
             "code_diff": ""},
    )
    resp = client.get("/api/v1/incidents", params={"q": "grumbly"})
    incidents = resp.json()["incidents"]
    assert incidents[0]["title"] == job_id
    assert incidents[0]["resolution"] == "grumbly fix plan"


def test_search_incidents_skips_unparseable_sidecar(client):
    good_id, _ = _seed_two_incidents()
    (Path("output") / "broken-result.json").write_text("not json {", encoding="utf-8")
    resp = client.get("/api/v1/incidents", params={"q": "KeyError"})
    assert resp.status_code == 200
    assert any(i["id"] == good_id for i in resp.json()["incidents"])
