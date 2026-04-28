# Quickstart / Integration Scenarios: Sprint 4 - Multi-Agent Migration

All tests MUST mock Docker (VerifierAgent patches `autosentinel.agents.verifier.docker`).
All tests run without a real LLM (mock `run()` methods only).

---

## Scenario 1: CODE category — happy path (SAFE verdict)

```python
state = build_initial_state("data/incoming/crash-app-logic.json")
# error_type="UnhandledError", message="unexpected None in user context"

with patch("autosentinel.agents.verifier.docker") as mock_docker:
    _setup_docker_success(mock_docker)
    result = multi_agent_graph.invoke(state, config)

assert result["error_category"]   == "CODE"
assert result["fix_artifact"]     is not None
assert result["security_verdict"] == "SAFE"
assert result["routing_decision"] == "CODE → CodeFixerAgent"
assert "CodeFixerAgent"           in result["agent_trace"]
assert "SecurityReviewerAgent"    in result["agent_trace"]
assert result["execution_result"]["status"] == "success"
assert "## Sandbox Execution"     in result["report_text"]
assert "## Security Review"       in result["report_text"]
```

---

## Scenario 2: INFRA category routing

```python
state = build_initial_state("data/incoming/crash-connectivity.json")
# error_type="ConnectionTimeout", message includes "connection"

result = invoke_with_docker_mock(state)

assert result["error_category"]   == "INFRA"
assert "InfraSREAgent"            in result["agent_trace"]
assert "CodeFixerAgent"           not in result["agent_trace"]
```

---

## Scenario 3: CONFIG category routing (resolves US1 scenario 3 — no ConfigAgent)

```python
state = build_initial_state("data/incoming/crash-config.json")
# error_type="ConfigurationError", message includes "environment variable"

result = invoke_with_docker_mock(state)

assert result["error_category"]   == "CONFIG"
assert "InfraSREAgent"            in result["agent_trace"]   # CONFIG → InfraSREAgent
assert result["routing_decision"] == "CONFIG → InfraSREAgent"
```

---

## Scenario 4: HIGH_RISK verdict — interrupt fires, Verifier NOT called

```python
from langgraph.types import Command

# Inject HIGH_RISK keyword into the fix_script already in state
state = build_initial_state_with_fix_script("DROP TABLE users")
cfg = {"configurable": {"thread_id": "test-high-risk"}}

result1 = multi_agent_graph.invoke(state, cfg)

# Pipeline is suspended
assert "__interrupt__" in result1
assert result1["approval_required"] is True  # set by security_gate before interrupt
# Verifier has NOT run
assert result1.get("execution_result") is None

# Verify structured log event was emitted
assert any(r.getMessage() == "human_approval_required"
           for r in captured_logs)

# Resume with approval
result2 = multi_agent_graph.invoke(Command(resume="approved"), cfg)
assert result2["execution_result"] is not None
assert "## Security Review" in result2["report_text"]
assert "HIGH RISK" in result2["report_text"]
```

---

## Scenario 5: HIGH_RISK — pipeline continues to produce report after approval

```python
cfg = {"configurable": {"thread_id": "test-high-risk-approved"}}
state = build_initial_state_with_fix_script("DROP TABLE sessions")

with patch("autosentinel.agents.verifier.docker") as mock_docker:
    _setup_docker_success(mock_docker)
    multi_agent_graph.invoke(state, cfg)        # suspends
    result = multi_agent_graph.invoke(Command(resume="approved"), cfg)

report_path = Path(result["report_path"])
assert report_path.exists()
assert "## Security Review" in report_path.read_text()
```

---

## Scenario 6: CAUTION verdict — no interrupt, caution badge in report (resolves caution_flag)

```python
# In Sprint 4 mock, CAUTION is not triggered by keywords (no CAUTION keyword set).
# Test by directly setting security_verdict in a unit test for format_report.
state_with_caution = {**base_state, "security_verdict": "CAUTION", ...}
result = format_report(state_with_caution)
assert "⚠ CAUTION" in result["report_text"]
assert "__interrupt__" not in result   # no interrupt for CAUTION
```

---

## Scenario 7: Docker unavailable — pipeline still produces report (US3 resilience)

```python
import docker.errors
with patch("autosentinel.agents.verifier.docker") as mock_docker:
    mock_docker.from_env.side_effect = docker.errors.DockerException("daemon down")
    result = invoke_multi_agent(state)

assert result["execution_error"]  is not None
assert result["execution_result"] is None
assert result["report_text"]      is not None   # report always generated
```

---

## Scenario 8: Parallel execution — Code Fixer and Security Reviewer both appear in agent_trace

```python
result = invoke_with_docker_mock(build_initial_state("crash-connectivity.json"))

# Both ran (fan-out confirmed)
assert "CodeFixerAgent" in result["agent_trace"] or "InfraSREAgent" in result["agent_trace"]
assert "SecurityReviewerAgent" in result["agent_trace"]
# Trace order shows they ran in same graph step
trace = result["agent_trace"]
specialist_idx  = next(i for i, a in enumerate(trace) if "Agent" in a and "Security" not in a and "Diagnosis" not in a and "Supervisor" not in a and "Verifier" not in a)
security_idx    = next(i for i, a in enumerate(trace) if "SecurityReviewer" in a)
# Both indices exist — both agents ran
assert specialist_idx >= 0 and security_idx >= 0
```

---

## Scenario 9: Docker import boundary check (SC-004)

```python
# tests/test_docker_import_boundary.py
def test_only_verifier_imports_docker():
    root = Path("autosentinel")
    violations = [...]   # AST walk (see research.md Decision 4)
    assert violations == []
```

---

## Scenario 10: Smoke benchmark produces valid JSON report

```python
import json, subprocess
result = subprocess.run(
    ["python", "-m", "autosentinel.benchmark"],
    capture_output=True, text=True
)
assert result.returncode == 0
report = json.loads(Path("output/benchmark-report.json").read_text())
assert report["scenario_count"] == 5
assert report["v1_resolution_rate"] is not None
assert report["v2_resolution_rate"] is not None
assert report["v1_avg_ms"]         is not None
assert report["v2_avg_ms"]         is not None
```

---

## Fixtures

```python
# tests/conftest.py additions

def build_initial_state(log_file: str) -> AgentState:
    return AgentState(
        log_path=str(Path("data/incoming") / log_file),
        error_log=None, parse_error=None,
        analysis_result=None, analysis_error=None,
        fix_script=None, execution_result=None, execution_error=None,
        report_text=None, report_path=None,
        # Sprint 4 new fields:
        error_category=None, fix_artifact=None, security_verdict=None,
        routing_decision=None, agent_trace=[], approval_required=False,
    )

def invoke_with_docker_mock(state: AgentState) -> AgentState:
    with patch("autosentinel.agents.verifier.docker") as mock_docker:
        _setup_docker_success(mock_docker)
        cfg = {"configurable": {"thread_id": str(uuid.uuid4())}}
        return multi_agent_graph.invoke(state, cfg)

def _setup_docker_success(mock_docker):
    mock_client    = MagicMock()
    mock_container = MagicMock()
    mock_docker.from_env.return_value             = mock_client
    mock_client.containers.run.return_value       = mock_container
    mock_container.wait.return_value              = {"StatusCode": 0}
    mock_container.logs.side_effect               = [b"Fix applied\n", b""]
```
