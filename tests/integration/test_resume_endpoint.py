"""T036 [US1] [PR-4] — POST /incidents/{incident_id}/resume endpoint.

Pre-seed a HIGH_RISK interrupt checkpoint at thread_id == incident_id via a
PostgresSaver graph built with the D2 `agents=` seam (hermetic, no real
provider), then drive the resume endpoint and assert the pipeline completes
past the security gate with trace_id preserved.

Requires infra/docker-compose.checkpointer.yml on :5434.

FAILING until the resume endpoint (T036) lands.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from unittest.mock import patch

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.integration._pr4_helpers import (
    CHECKPOINTER_DSN,
    build_fixture_clients,
    build_injected_agents,
    requires_checkpointer,
    setup_docker_success,
)


def _seed_high_risk_checkpoint(incident_id: str, log: Path) -> None:
    """Run process-A up to the HIGH_RISK interrupt, persisting a checkpoint at
    thread_id == incident_id in the shared PostgresSaver."""
    clients = build_fixture_clients(code_fixer_artifact="DROP TABLE users")
    agents = build_injected_agents(clients)
    initial_state = {
        "log_path": str(log),
        "error_log": None,
        "parse_error": None,
        "analysis_result": None,
        "analysis_error": None,
        "fix_script": None,
        "execution_result": None,
        "execution_error": None,
        "report_text": None,
        "report_path": None,
        "error_category": None,
        "fix_artifact": None,
        "security_verdict": None,
        "routing_decision": None,
        "specialist": None,
        "agent_trace": [],
        "approval_required": False,
        "trace_id": incident_id,  # trace_id == incident_id == thread_id
        "cost_accumulated": 0.0,
    }
    cfg = {"configurable": {"thread_id": incident_id}}
    with PostgresSaver.from_conn_string(CHECKPOINTER_DSN) as checkpointer:
        checkpointer.setup()
        graph = build_multi_agent_graph(checkpointer=checkpointer, agents=agents)
        result = graph.invoke(initial_state, cfg)
    assert "__interrupt__" in result, "pre-seed must suspend at HIGH_RISK gate"


@requires_checkpointer
def test_resume_endpoint_completes_pipeline(client, tmp_path, monkeypatch):
    # The endpoint's graph must bind to the SAME PostgresSaver as the pre-seed.
    monkeypatch.setenv("AUTOSENTINEL_CHECKPOINTER_DSN", CHECKPOINTER_DSN)

    incident_id = secrets.token_hex(16)
    log = tmp_path / "hr.json"
    log.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-31T00:00:00Z",
                "service_name": "svc",
                "error_type": "SecurityException",
                "message": "sql injection",
                "stack_trace": None,
            }
        )
    )
    _seed_high_risk_checkpoint(incident_id, log)

    with patch("autosentinel.agents.verifier.docker") as md:
        setup_docker_success(md)
        resp = client.post(
            f"/incidents/{incident_id}/resume",
            json={"decision": "approve", "reviewer_notes": "looks fine"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # (b) pipeline completed past the gate after approval
    assert body["approval_required"] is True
    assert body["execution_status"] == "success"
    assert "VerifierAgent" in body["agent_trace"]
    # (c) trace_id preserved across the resume
    assert body["trace_id"] == incident_id
