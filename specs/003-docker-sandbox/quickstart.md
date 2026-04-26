# Quickstart / Integration Scenarios: Sprint 3 - Secure Docker Sandbox Execution

## Test Scenarios for `execute_fix` Node

These scenarios drive the Test-First gate (FR-009 / SC-005). All Docker SDK calls
MUST be mocked — tests MUST NOT require a running Docker daemon.

---

### Scenario 1: Successful script execution

**Setup**: `fix_script` contains a valid Python one-liner; `container.wait()` returns `{"StatusCode": 0}`

```python
mock_container.wait.return_value = {"StatusCode": 0}
mock_container.logs.side_effect = [b"Hello from sandbox\n", b""]
state = {
    "fix_script": 'print("Hello from sandbox")',
    # ... other required DiagnosticState keys ...
}
result = execute_fix(state)
```

**Expected**:
- `result["execution_result"]["status"] == "success"`
- `result["execution_result"]["return_code"] == 0`
- `result["execution_result"]["stdout"] == "Hello from sandbox\n"`
- `result["execution_result"]["stderr"] == ""`
- `result["execution_result"]["duration_ms"] >= 0`
- `result["execution_error"] is None`
- `mock_container.remove.assert_called_once_with(force=True)`

---

### Scenario 2: Script exits with non-zero return code

**Setup**: `container.wait()` returns `{"StatusCode": 1}`

```python
mock_container.wait.return_value = {"StatusCode": 1}
mock_container.logs.side_effect = [b"", b"Error: something went wrong\n"]
```

**Expected**:
- `result["execution_result"]["status"] == "failure"`
- `result["execution_result"]["return_code"] == 1`
- `result["execution_result"]["stdout"] == ""`
- `result["execution_result"]["stderr"] == "Error: something went wrong\n"`
- `result["execution_error"] is None`
- Container still removed: `mock_container.remove.assert_called_once_with(force=True)`

---

### Scenario 3: Script exceeds 5-second timeout

**Setup**: `container.wait()` raises `requests.exceptions.ReadTimeout`

```python
import requests.exceptions
mock_container.wait.side_effect = requests.exceptions.ReadTimeout()
```

**Expected**:
- `result["execution_result"]["status"] == "timeout"`
- `result["execution_result"]["return_code"] is None`
- `result["execution_result"]["stdout"] == ""`
- `result["execution_result"]["stderr"] == ""`
- `result["execution_error"] is None`
- Container killed: `mock_container.kill.assert_called_once()`
- Container still removed: `mock_container.remove.assert_called_once_with(force=True)`

---

### Scenario 4: Docker daemon unavailable

**Setup**: `docker.from_env()` raises `docker.errors.DockerException`

```python
mock_docker.from_env.side_effect = docker.errors.DockerException("Cannot connect to Docker daemon")
```

**Expected**:
- `result["execution_result"] is None`
- `result["execution_error"]` is a non-empty string containing the error message
- No container operations attempted

---

### Scenario 5: `fix_script` is None (skipped)

**Setup**: `state["fix_script"] = None`

```python
state = {"fix_script": None, ...}
result = execute_fix(state)
```

**Expected**:
- `result["execution_result"]["status"] == "skipped"`
- `result["execution_result"]["return_code"] is None`
- `result["execution_result"]["stdout"] == ""`
- `result["execution_result"]["stderr"] == ""`
- `result["execution_error"] is None`
- Docker SDK never called: `mock_docker.from_env.assert_not_called()`

---

## Test Scenarios for Updated `format_report` Node

### Scenario 6: Report with successful execution

**Setup**: Full `DiagnosticState` with `execution_result.status == "success"`

**Expected**: Report markdown contains:
```
## Sandbox Execution

**Status**: success
**Return code**: 0
**Duration**: \d+ms
```

### Scenario 7: Report with execution error (Docker unavailable)

**Setup**: `execution_result` is `None`, `execution_error = "Cannot connect to Docker daemon"`

**Expected**: Report markdown contains:
```
## Sandbox Execution

**Status**: error
**Reason**: Cannot connect to Docker daemon
```

### Scenario 8: Report with skipped execution

**Setup**: `execution_result.status == "skipped"`

**Expected**: Report markdown contains:
```
## Sandbox Execution

**Status**: skipped (no fix script generated)
```

---

## End-to-End Integration Scenario

### Scenario 9: Full pipeline with Docker mocked at node boundary

```python
# Patch docker at the module level of execute_fix
with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
    mock_client = mock_docker.from_env.return_value
    mock_container = mock_client.containers.run.return_value
    mock_container.wait.return_value = {"StatusCode": 0}
    mock_container.logs.side_effect = [b"Fix applied\n", b""]

    report_path = run_pipeline("data/incoming/sample.json")

assert Path(report_path).exists()
report_text = Path(report_path).read_text()
assert "## Sandbox Execution" in report_text
assert "**Status**: success" in report_text
assert "Fix applied" in report_text
```

---

## Docker SDK Mock Setup Pattern

```python
# tests/conftest.py additions
@pytest.fixture
def mock_docker_success():
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        mock_client = MagicMock()
        mock_docker.from_env.return_value = mock_client
        mock_container = MagicMock()
        mock_client.containers.run.return_value = mock_container
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.side_effect = [b"output\n", b""]
        yield mock_docker, mock_container

@pytest.fixture
def mock_docker_unavailable():
    with patch("autosentinel.nodes.execute_fix.docker") as mock_docker:
        mock_docker.from_env.side_effect = docker.errors.DockerException("daemon unavailable")
        yield mock_docker
```
