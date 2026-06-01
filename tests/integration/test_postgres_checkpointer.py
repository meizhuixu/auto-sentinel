"""T029 [US1] [PR-4] — cross-process interrupt durability via PostgresSaver.

Process-A starts the pipeline, reaches the HIGH_RISK interrupt, and exits.
Process-B (a real subprocess, fresh interpreter) reconnects to the SAME
PostgresSaver, resumes the SAME thread_id, and must:
  * resume from the interrupt point (specialist agents do NOT re-run), and
  * reach the Verifier (which runs in process-B).

Requires infra/docker-compose.checkpointer.yml running on localhost:5434.

FAILING until: build_multi_agent_graph(*, checkpointer=, agents=) injection
seam (D2) lands and the PostgresSaver swap (T035) is wired.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.integration._pr4_helpers import (
    CHECKPOINTER_DSN,
    ZERO_TRACE_ID,
    build_fixture_clients,
    build_injected_agents,
    requires_checkpointer,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_log(tmp_path: Path) -> Path:
    log = tmp_path / "high_risk.json"
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
    return log


def _initial_state(log_file: Path) -> dict:
    return {
        "log_path": str(log_file),
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
        "trace_id": ZERO_TRACE_ID,
        "cost_accumulated_usd": 0.0,
    }


@requires_checkpointer
def test_cross_process_resume_does_not_rerun_specialists(tmp_path):
    thread_id = "t029-" + uuid.uuid4().hex
    log = _write_log(tmp_path)

    # ── Process A: run until the HIGH_RISK interrupt, then "exit" ──────────
    clients_a = build_fixture_clients(code_fixer_artifact="DROP TABLE users")
    agents_a = build_injected_agents(clients_a)
    cfg = {"configurable": {"thread_id": thread_id}}

    with PostgresSaver.from_conn_string(CHECKPOINTER_DSN) as checkpointer:
        checkpointer.setup()
        graph_a = build_multi_agent_graph(checkpointer=checkpointer, agents=agents_a)
        result_a = graph_a.invoke(_initial_state(log), cfg)

    assert "__interrupt__" in result_a, "process-A should suspend at HIGH_RISK gate"
    trace_a = result_a.get("agent_trace", [])
    assert trace_a.count("CodeFixerAgent") == 1
    assert "SecurityReviewerAgent" in trace_a
    assert "VerifierAgent" not in trace_a, "Verifier must not run before approval"

    # ── Process B: fresh interpreter, same DSN + thread_id, resume ─────────
    env = dict(os.environ)
    env["AUTOSENTINEL_CHECKPOINTER_DSN"] = CHECKPOINTER_DSN
    env.setdefault("ARK_API_KEY", "test-fake-ark-key")
    env.setdefault("GLM_API_KEY", "test-fake-glm-key")

    proc = subprocess.run(
        [sys.executable, "-m", "tests.integration._resume_worker", thread_id],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"resume worker failed:\nSTDOUT:{proc.stdout}\nSTDERR:{proc.stderr}"

    line = next(
        (ln for ln in proc.stdout.splitlines() if ln.startswith("RESUME_RESULT ")),
        None,
    )
    assert line is not None, f"no RESUME_RESULT in worker stdout:\n{proc.stdout}"
    out = json.loads(line[len("RESUME_RESULT ") :])

    # Specialists ran exactly once (in process-A); process-B did NOT re-run them.
    assert out["agent_trace"].count("CodeFixerAgent") == 1
    assert out["agent_trace"].count("SecurityReviewerAgent") == 1
    # Verifier ran in process-B.
    assert "VerifierAgent" in out["agent_trace"]
    assert out["execution_status"] == "success"
    # trace_id survived the cross-process checkpoint round-trip unchanged.
    assert out["trace_id"] == ZERO_TRACE_ID
