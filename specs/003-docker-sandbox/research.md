# Research: Sprint 3 - Secure Docker Sandbox Execution

## Decision 1: Graph Rewiring Strategy

**Decision**: Insert `execute_fix` between `analyze_error` and `format_report` with an unconditional edge from `execute_fix` to `format_report`.

**Rationale**: The `execute_fix` node must ALWAYS pass control to `format_report` — even on Docker failure (FR-007). This means there is no conditional routing out of `execute_fix`. Instead, `execute_fix` catches all its own errors, stores them in state, and returns normally. The graph becomes:

```
START → parse_log →(parse_error? END)→ analyze_error →(analysis_error? END)→ execute_fix → format_report → END
```

Change to `_route_after_analyze`: return `"execute_fix"` instead of `"format_report"`.

**Alternatives considered**:
- Conditional edge from `execute_fix` to `END` on Docker failure: Rejected — violates FR-007 which requires the report to always be produced even when Docker is unavailable.

---

## Decision 2: DiagnosticState Extension

**Decision**: Add three new `Optional` fields to `DiagnosticState`: `fix_script`, `execution_result`, and `execution_error`. Initialize all three to `None` in `run_pipeline()` and in all conftest fixtures.

**Rationale**: Mirrors the existing pattern (`parse_error`, `analysis_error`) for error signalling. Keeps `execution_result` as the structured success payload and `execution_error` as the plain-string error path (Docker unavailable, container crash before execution).

**New fields**:
| Field | Type | Set by | Purpose |
|-------|------|--------|---------|
| `fix_script` | `Optional[str]` | `analyze_error` | Mock-generated Python script string |
| `execution_result` | `Optional[ExecutionResult]` | `execute_fix` | Structured outcome of sandbox run |
| `execution_error` | `Optional[str]` | `execute_fix` | Docker-level error (unavailable, start failure) |

**Alternatives considered**:
- Fold `execution_error` into `execution_result.status`: Makes FR-007 routing logic inconsistent with the `parse_error`/`analysis_error` precedent already established in the codebase.

---

## Decision 3: Docker SDK Usage Pattern

**Decision**: Use `docker.from_env()` + `client.containers.run(..., detach=True)` + `container.wait(timeout=5)` + `container.remove(force=True)` in a try/finally block.

**Rationale**: `detach=True` gives us a `Container` object we can explicitly wait on and destroy, regardless of outcome. The `finally` block guarantees `container.remove(force=True)` is called — satisfying SC-001 (zero dangling containers). Stdout and stderr are captured separately via `container.logs(stdout=True, stderr=False)` / `container.logs(stdout=False, stderr=True)`.

```python
import time
import docker

client = docker.from_env()
container = client.containers.run(
    "python:3.10-alpine",
    ["python", "-c", fix_script],
    detach=True,
    mem_limit="64m",
    network_mode="none",
    read_only=False,   # scripts may write to /tmp
)
start = time.monotonic()
try:
    result = container.wait(timeout=5)   # {"StatusCode": N}
    duration_ms = int((time.monotonic() - start) * 1000)
    stdout = container.logs(stdout=True, stderr=False).decode(errors="replace")
    stderr = container.logs(stdout=False, stderr=True).decode(errors="replace")
    status = "success" if result["StatusCode"] == 0 else "failure"
    return_code = result["StatusCode"]
except requests.exceptions.ReadTimeout:
    duration_ms = int((time.monotonic() - start) * 1000)
    container.kill()
    status, return_code, stdout, stderr = "timeout", None, "", ""
finally:
    container.remove(force=True)
```

**Timeout exception**: `container.wait(timeout=N)` uses `requests` under the hood; timeout raises `requests.exceptions.ReadTimeout`.

**Alternatives considered**:
- `client.containers.run(..., detach=False)` (blocking): Does not provide a `Container` handle for cleanup; cannot guarantee force-destroy.
- `asyncio.wait_for` wrapper: `execute_fix` runs synchronously in the LangGraph node; no async needed in Sprint 3.

---

## Decision 4: Mock fix_script Generation in analyze_error

**Decision**: Append a `fix_script` string to the return dict of `_mock_classify()` — one simple Python print-statement script per error category — and include `fix_script` in `analyze_error`'s return dict.

**Rationale**: The simplest change that satisfies FR-002 without modifying the `AnalysisResult` TypedDict (which has a defined schema used elsewhere). `fix_script` is returned as a top-level key in `analyze_error`'s return dict, not nested inside `AnalysisResult`.

```python
# In analyze_error():
result = _mock_classify(...)
return {
    "analysis_result": result,
    "analysis_error": None,
    "fix_script": _MOCK_FIX_SCRIPTS[result["error_category"]],
}
```

**Alternatives considered**:
- Add `fix_script` to `AnalysisResult` TypedDict: Changes an established schema; affects format_report, Sprint 1 tests, and Sprint 2 API tests. Unnecessary coupling.

---

## Decision 5: Testing Strategy — Mocking Docker SDK

**Decision**: Patch `autosentinel.nodes.execute_fix.docker` at the module level with `unittest.mock.patch`. The `client.containers.run()` call returns a `MagicMock` container; `container.wait()` and `container.logs()` are configured per test.

**Rationale**: Tests must not require a running Docker daemon (they run in CI without Docker). Patching at the node module's namespace ensures `docker.from_env()` is fully intercepted. Timeout is simulated by making `container.wait()` raise `requests.exceptions.ReadTimeout`.

**Test matrix**:
| Scenario | Mock setup |
|----------|-----------|
| Success (exit 0) | `container.wait()` returns `{"StatusCode": 0}` |
| Failure (exit 1) | `container.wait()` returns `{"StatusCode": 1}` |
| Timeout | `container.wait()` raises `requests.exceptions.ReadTimeout` |
| Docker unavailable | `docker.from_env()` raises `docker.errors.DockerException` |
| Script is None (skipped) | State has `fix_script=None`; no docker call made |

**Alternatives considered**:
- `pytest-docker` / real container in tests: Requires Docker daemon in CI; slow; flaky. Rejected.
- Patching `docker.from_env` globally in conftest: Makes test isolation harder; prefer per-test patches.

---

## Decision 6: New Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `docker>=7.0` | already installed | Python Docker SDK — `docker.from_env()`, `Container` API |

No new packages needed beyond what was already installed.
