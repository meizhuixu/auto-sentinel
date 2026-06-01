"""Process-B worker for the T029 cross-process resume test.

Run as a SUBPROCESS (fresh interpreter) by test_postgres_checkpointer.py:

    uv run --extra dev python -m tests.integration._resume_worker <thread_id>

Reconnects to the SAME PostgresSaver (AUTOSENTINEL_CHECKPOINTER_DSN) and
resumes the pipeline that process-A suspended at the HIGH_RISK interrupt.
On resume LangGraph replays from the checkpoint: the specialist agents already
ran in process-A and MUST NOT run again. The Verifier runs here, in process-B.

Emits a single ``RESUME_RESULT <json>`` line on stdout for the parent to parse.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

from autosentinel.multi_agent_graph import build_multi_agent_graph
from tests.integration._pr4_helpers import (
    build_fixture_clients,
    build_injected_agents,
    setup_docker_success,
)


def main() -> int:
    dsn = os.environ["AUTOSENTINEL_CHECKPOINTER_DSN"]
    thread_id = sys.argv[1]

    clients = build_fixture_clients(code_fixer_artifact="DROP TABLE users")
    agents = build_injected_agents(clients)

    with PostgresSaver.from_conn_string(dsn) as checkpointer:
        graph = build_multi_agent_graph(checkpointer=checkpointer, agents=agents)
        cfg = {"configurable": {"thread_id": thread_id}}
        with patch("autosentinel.agents.verifier.docker") as md:
            setup_docker_success(md)
            result = graph.invoke(Command(resume="approved"), cfg)

    execution_result = result.get("execution_result") or {}
    out = {
        "agent_trace": result.get("agent_trace", []),
        "execution_status": execution_result.get("status"),
        "approval_required": result.get("approval_required"),
        "trace_id": result.get("trace_id"),
    }
    print("RESUME_RESULT " + json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
