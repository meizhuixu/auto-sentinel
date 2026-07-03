"""T044 [US4] [PR-4] — trace_id propagation (contracts/trace-propagation.md).

Three cases (the contract's minimum):

(a) test_trace_id_end_to_end_consistency — one trace_id, generated at FastAPI
    ingest, observed unchanged by every LLM-call agent and returned in the 202
    body. FAILING until trace_id generation (T045) + worker→graph threading
    (T046) land.

(b) test_llmtracer_rejects_missing_trace_id — the real ArkLLMClient surfaces an
    empty trace_id as ValueError, unwrapped (Constitution VII.3 / T047). This
    already holds via LLMRequest validation; the case pins the contract.

(c) test_state_serialization_preserves_trace_id — trace_id survives the
    PostgresSaver JSON round-trip byte-for-byte. FAILING until the
    build_multi_agent_graph(*, checkpointer=, agents=) seam (D2) lands.
    Requires the checkpointer container on :5434.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

import autosentinel.multi_agent_graph as mag
from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.integration._pr4_helpers import (
    CHECKPOINTER_DSN,
    RecordingMock,
    build_fixture_clients,
    build_injected_agents,
    requires_checkpointer,
    setup_docker_success,
)

_KNOWN_TRACE_ID = "abcdef0123456789abcdef0123456789"

_VALID_PAYLOAD = {
    "service_name": "trace-svc",
    "error_type": "RuntimeError",
    "message": "boom",
    "timestamp": "2026-05-29T00:00:00Z",
    "stack_trace": None,
}


# ── (a) end-to-end consistency through the FastAPI endpoint ────────────────
def test_trace_id_end_to_end_consistency(client, monkeypatch):
    monkeypatch.setenv("AUTOSENTINEL_MULTI_AGENT", "1")

    recorder = RecordingMock()
    for agent in (
        mag._diagnosis_agent,
        mag._supervisor_agent,
        mag._code_fixer_agent,
        mag._infra_sre_agent,
        mag._security_reviewer_agent,
    ):
        monkeypatch.setattr(agent, "_llm_client", recorder)

    with patch("autosentinel.agents.verifier.docker") as md:
        setup_docker_success(md)
        resp = client.post("/api/v1/alerts", json=_VALID_PAYLOAD)
        assert resp.status_code == 202
        # T045: ingest returns the generated trace_id so callers can correlate.
        trace_id = resp.json()["trace_id"]

        # wait for the async worker to drive the pipeline to completion
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and len(recorder.calls) < 3:
            time.sleep(0.05)

    assert len(recorder.calls) >= 3, f"pipeline did not run all agents: {recorder.calls}"
    observed = {tid for _agent, tid in recorder.calls}
    assert observed == {trace_id}, (
        f"every agent must observe the ingest trace_id {trace_id!r}; got {observed!r}"
    )


# ── (b) empty trace_id surfaces as unwrapped ValueError (T047, both clients) ─
def test_llmtracer_rejects_missing_trace_id():
    from autosentinel.llm.ark_client import ArkLLMClient
    from autosentinel.llm.glm_client import GlmLLMClient
    from autosentinel.llm.protocol import Message

    ark = ArkLLMClient(api_key="test-fake-ark-key")
    with pytest.raises(ValueError, match="32 lowercase hex"):
        ark.complete(
            messages=[Message(role="user", content="hi")],
            model="doubao-1.5-lite-32k",
            trace_id="",
            agent_name="diagnosis",
            max_tokens=128,
            temperature=0.0,
        )

    # T047: GlmLLMClient surfaces the same unwrapped ValueError (it builds the
    # LLMRequest before opening the tracer / issuing any SDK call).
    glm = GlmLLMClient(api_key="test-fake-glm-key")
    with pytest.raises(ValueError, match="32 lowercase hex"):
        glm.complete(
            messages=[Message(role="user", content="hi")],
            model="glm-4.7",
            trace_id="",
            agent_name="security_reviewer",
            max_tokens=128,
            temperature=0.0,
        )


# ── (c) trace_id survives PostgresSaver serialization round-trip ───────────
@requires_checkpointer
def test_state_serialization_preserves_trace_id(tmp_path):
    log = tmp_path / "trace.json"
    log.write_text(
        json.dumps(
            {
                "timestamp": "2026-05-29T00:00:00Z",
                "service_name": "svc",
                "error_type": "SecurityException",
                "message": "sql injection",
                "stack_trace": None,
            }
        )
    )

    clients = build_fixture_clients(code_fixer_artifact='print("DROP TABLE users")')
    agents = build_injected_agents(clients)
    cfg = {"configurable": {"thread_id": "t044c-" + uuid.uuid4().hex}}

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
        "trace_id": _KNOWN_TRACE_ID,
        "cost_accumulated": 0.0,
    }

    with PostgresSaver.from_conn_string(CHECKPOINTER_DSN) as checkpointer:
        checkpointer.setup()
        graph = build_multi_agent_graph(checkpointer=checkpointer, agents=agents)
        result = graph.invoke(initial_state, cfg)
        assert "__interrupt__" in result, "expected HIGH_RISK interrupt to persist a checkpoint"

        # Read the persisted state straight back out of PostgresSaver.
        snapshot = graph.get_state(cfg)

    assert snapshot.values["trace_id"] == _KNOWN_TRACE_ID
