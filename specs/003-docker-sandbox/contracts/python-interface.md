# Python Interface Contracts: Sprint 3 - Secure Docker Sandbox Execution

## Module: `autosentinel.nodes.execute_fix`

### Function: `execute_fix(state: DiagnosticState) -> dict`

**Contract**: LangGraph node that executes the `fix_script` from `DiagnosticState` inside a Docker sandbox and returns partial state with the result.

**Input** (reads from state):

| Key | Type | Required | Notes |
|-----|------|----------|-------|
| `fix_script` | `Optional[str]` | No | If `None`, execution is skipped |

**Output** (returned partial state dict):

| Key | Type | Always set | Notes |
|-----|------|------------|-------|
| `execution_result` | `Optional[ExecutionResult]` | Yes | `None` when `execution_error` is set |
| `execution_error` | `Optional[str]` | Yes | `None` on success/skipped/timeout |

**Status mapping**:

| Condition | `execution_result.status` | `execution_error` |
|-----------|--------------------------|-------------------|
| `fix_script` is `None` | `"skipped"` | `None` |
| Container exits with code 0 | `"success"` | `None` |
| Container exits with non-zero code | `"failure"` | `None` |
| `container.wait()` raises `ReadTimeout` | `"timeout"` | `None` |
| `docker.from_env()` raises `DockerException` | `None` | error message string |
| Container fails to start | `None` | error message string |

**Guarantees**:
- NEVER raises an exception — all errors are captured into state
- ALWAYS calls `container.remove(force=True)` in a `finally` block
- `execution_result` and `execution_error` are mutually exclusive (one is always `None`)

---

## TypedDict: `ExecutionResult` (in `autosentinel.models`)

```python
class ExecutionResult(TypedDict):
    status: str           # "success" | "failure" | "timeout" | "error" | "skipped"
    return_code: Optional[int]   # None for timeout/error/skipped
    stdout: str
    stderr: str
    duration_ms: int
    error: Optional[str]  # Docker-level error message; None on success/failure
```

---

## Extended TypedDict: `DiagnosticState` (in `autosentinel.models`)

Three new optional fields added to the existing TypedDict:

```python
class DiagnosticState(TypedDict):
    # ... existing fields (Sprint 1) ...
    log_path: str
    error_log: Optional[ErrorLog]
    parse_error: Optional[str]
    analysis_result: Optional[AnalysisResult]
    analysis_error: Optional[str]
    report_text: Optional[str]
    report_path: Optional[str]
    # New in Sprint 3:
    fix_script: Optional[str]
    execution_result: Optional[ExecutionResult]
    execution_error: Optional[str]
```

---

## Function: `analyze_error` — extended return contract

The existing `analyze_error` node MUST be extended to include `fix_script` in its return dict.

**Extended output** (returned partial state dict):

| Key | Type | Notes |
|-----|------|-------|
| `analysis_result` | `Optional[AnalysisResult]` | Unchanged from Sprint 1 |
| `analysis_error` | `Optional[str]` | Unchanged from Sprint 1 |
| `fix_script` | `Optional[str]` | New in Sprint 3 — `None` only if `analysis_error` is set |

**Mock fix script mapping** (deterministic, by `error_category`):

| `error_category` | `fix_script` |
|-----------------|-------------|
| `connectivity` | `'print("Restarting connection pool for upstream dependency...")'` |
| `resource_exhaustion` | `'print("Triggering garbage collection and releasing memory buffers...")'` |
| `configuration` | `'print("Reloading environment variables from secrets store...")'` |
| `application_logic` | `'print("Flushing stale state and re-initialising application context...")'` |

---

## Graph Wiring Contract (`autosentinel.graph`)

The `_route_after_analyze` function MUST be updated:

```python
# Before (Sprint 1/2):
def _route_after_analyze(state: DiagnosticState) -> str:
    return END if state.get("analysis_error") else "format_report"

# After (Sprint 3):
def _route_after_analyze(state: DiagnosticState) -> str:
    return END if state.get("analysis_error") else "execute_fix"
```

A new unconditional edge is added:

```python
builder.add_node("execute_fix", execute_fix)
builder.add_edge("execute_fix", "format_report")   # always continues
```

---

## Module: `autosentinel.nodes.format_report` — extended template contract

The `format_report` node MUST append a "Sandbox Execution" section after "Remediation Steps".

**Template for normal execution** (`execution_result` is set):

```markdown
## Sandbox Execution

**Status**: {execution_result['status']}
**Return code**: {execution_result['return_code']}
**Duration**: {execution_result['duration_ms']}ms

### Output

```
{execution_result['stdout']}
```

### Errors

```
{execution_result['stderr']}
```
```

**Template when `execution_error` is set**:

```markdown
## Sandbox Execution

**Status**: error
**Reason**: {execution_error}
```

**Template when `execution_result.status == "skipped"`**:

```markdown
## Sandbox Execution

**Status**: skipped (no fix script generated)
```

**Reads from state**:
- `execution_result: Optional[ExecutionResult]`
- `execution_error: Optional[str]`
