"""Shared pytest fixtures for the diagnostic pipeline test suite."""

# Sprint 5: multi_agent_graph constructs LLM clients at module-import time
# via build_client_for_agent(), which checks ARK_API_KEY / GLM_API_KEY env
# vars upfront. Tests use MockLLMClient and never call real APIs, but the
# env check still runs. Use setdefault so developers with real keys set
# locally aren't overridden when running integration tests.
#
# PR-4 follow-up: refactor multi_agent_graph to lazy/factory construction
# so module-import side effects (env check, future PostgresSaver connection)
# don't bleed into pytest collection.
import os
os.environ.setdefault("ARK_API_KEY", "test-fake-ark-key")
os.environ.setdefault("GLM_API_KEY", "test-fake-glm-key")

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from autosentinel.llm.cost_guard import get_cost_guard
from autosentinel.models import AgentState, DiagnosticState


@pytest.fixture(autouse=True)
def cost_guard_reset():
    """Reset the CostGuard singleton between tests so cumulative spend from
    one test never bleeds into the next.

    Relies on PYTEST_CURRENT_TEST being set by pytest during the runtest
    phases (setup/call/teardown) — CostGuard.reset_for_test() refuses without
    it. The defensive assert below makes the failure mode loud if pytest's
    behaviour ever changes (e.g., a future plugin runs autouse fixtures
    outside the runtest phase).

    Sprint 1-4 tests that never touch CostGuard are unaffected: the singleton
    starts at total_spent_usd=0, this fixture sets it back to 0 — no-op.
    Tests that DO accumulate (T012/T013 ark/glm client tests) get a clean
    slate per test instead of inheriting spend from prior tests.
    """
    assert os.environ.get("PYTEST_CURRENT_TEST"), (
        "cost_guard_reset autouse fixture expects PYTEST_CURRENT_TEST to be set "
        "by pytest before fixture body runs"
    )
    get_cost_guard().reset_for_test()
    yield


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
        fix_script=None,
        execution_result=None,
        execution_error=None,
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
        fix_script=None,
        execution_result=None,
        execution_error=None,
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
        fix_script=None,
        execution_result=None,
        execution_error=None,
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
def client(tmp_path, monkeypatch):
    """TestClient wrapping the FastAPI app; exercises the full lifespan."""
    monkeypatch.chdir(tmp_path)
    from starlette.testclient import TestClient
    from autosentinel.api.main import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def mock_pipeline(tmp_path):
    """Patch run_pipeline in queue.py's namespace; writes a sentinel report file."""
    report = tmp_path / "sentinel-report.md"
    report.write_text("# Sentinel Report")

    def _fake_pipeline(log_path):
        return report

    with patch("autosentinel.api.queue.run_pipeline", side_effect=_fake_pipeline):
        yield report


def build_initial_state(log_file: str, tmp_path: Path) -> AgentState:
    """Construct a zero-field AgentState pointing to a log file under tmp_path."""
    return AgentState(
        log_path=str(tmp_path / log_file),
        error_log=None,
        parse_error=None,
        analysis_result=None,
        analysis_error=None,
        fix_script=None,
        execution_result=None,
        execution_error=None,
        report_text=None,
        report_path=None,
        error_category=None,
        fix_artifact=None,
        security_verdict=None,
        routing_decision=None,
        agent_trace=[],
        approval_required=False,
        # Sprint 5 sentinel defaults — "0"*32 is a valid 32-char lowercase
        # hex string (passes LLMRequest trace_id regex); 0.0 is the natural
        # zero-spend starting point for CostGuard accumulation.
        trace_id="0" * 32,
        cost_accumulated_usd=0.0,
    )


def _setup_docker_success(mock_docker: MagicMock) -> None:
    """Configure a docker mock that simulates a successful container run."""
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_docker.from_env.return_value = mock_client
    mock_client.containers.run.return_value = mock_container
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = [b"Fix applied\n", b""]


def invoke_with_docker_mock(graph, state: AgentState) -> AgentState:
    """Invoke multi-agent graph with Docker mocked for success."""
    with patch("autosentinel.agents.verifier.docker") as mock_docker:
        _setup_docker_success(mock_docker)
        cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
        return graph.invoke(state, cfg)


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
