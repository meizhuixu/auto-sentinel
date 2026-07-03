"""format_report node — renders markdown report and writes to output/.

M4 MCP enabler (specs/m4-mcp-enabler FR-001): alongside the markdown report,
a machine-readable sidecar `output/{stem}-result.json` is written so the
event gateway can serve GET /api/v1/alerts/{job_id} without parsing markdown.
The AgentState → sidecar field mapping is deterministic and documented in
specs/m4-mcp-enabler/spec.md — no LLM calls happen here.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def _sandbox_section(state) -> str:
    execution_error = state.get("execution_error")
    execution_result = state.get("execution_result")

    if execution_error:
        return f"""## Sandbox Execution

**Status**: error
**Reason**: {execution_error}
"""

    if execution_result is None:
        return ""

    if execution_result["status"] == "skipped":
        return """## Sandbox Execution

**Status**: skipped (no fix script generated)
"""

    return f"""## Sandbox Execution

**Status**: {execution_result['status']}
**Return code**: {execution_result['return_code']}
**Duration**: {execution_result['duration_ms']}ms

### Output

```
{execution_result['stdout']}```

### Errors

```
{execution_result['stderr']}```
"""


def _security_section(state) -> str:
    verdict = state.get("security_verdict")
    if verdict is None:
        return ""

    if state.get("approval_required"):
        verdict_display = "🚨 HIGH RISK — executed after human approval"
    elif verdict == "CAUTION":
        verdict_display = "⚠ CAUTION"
    else:
        verdict_display = verdict

    routing = state.get("routing_decision") or "N/A"
    trace = ", ".join(state.get("agent_trace") or [])

    return f"""## Security Review

**Verdict**: {verdict_display}
**Routing**: {routing}
**Agents**: {trace}
"""


def _analysis_section(state) -> str:
    analysis = state.get("analysis_result")
    if analysis is None:
        return ""

    confidence_pct = f"{analysis['confidence'] * 100:.0f}%"
    steps = "\n".join(
        f"{i}. {step}" for i, step in enumerate(analysis["remediation_steps"], 1)
    )
    return f"""## Root Cause Analysis

**Category**: {analysis['error_category']}
**Confidence**: {confidence_pct}

{analysis['root_cause_hypothesis']}

## Remediation Steps

{steps}

"""


# ── M4 sidecar mapping (specs/m4-mcp-enabler/spec.md, "Honest field-mapping") ──

# Multi-agent DiagnosisAgent categories. SECURITY has no slot in the MCP
# category vocabulary (runtime|build|infra|config|unknown) — mapped to
# "unknown" rather than disguised as runtime.
_ERROR_CATEGORY_MAP = {
    "CODE": "runtime",
    "INFRA": "infra",
    "CONFIG": "config",
    "SECURITY": "unknown",
}

# Supervisor route fallback (used when DiagnosisAgent output is absent).
_SPECIALIST_MAP = {"code_fixer": "runtime", "infra_sre": "infra"}

# v1 single-agent analyze_error categories.
_V1_CATEGORY_MAP = {
    "connectivity": "infra",
    "resource_exhaustion": "infra",
    "configuration": "config",
    "application_logic": "runtime",
}

_RISK_MAP = {"SAFE": "low", "CAUTION": "medium", "HIGH_RISK": "high"}


def _derive_category(state) -> str:
    category = state.get("error_category")
    if category in _ERROR_CATEGORY_MAP:
        return _ERROR_CATEGORY_MAP[category]
    specialist = state.get("specialist")
    if specialist in _SPECIALIST_MAP:
        return _SPECIALIST_MAP[specialist]
    analysis = state.get("analysis_result")
    if analysis:
        return _V1_CATEGORY_MAP.get(analysis.get("error_category"), "unknown")
    return "unknown"


def _derive_severity(state) -> str:
    """No agent grades incident severity today; "medium" is the documented
    deterministic fallback. The only graded signal in state is the security
    gate — HIGH_RISK / approval_required upgrade to "high"."""
    if state.get("security_verdict") == "HIGH_RISK" or state.get("approval_required"):
        return "high"
    return "medium"


def _derive_summary(state) -> str:
    analysis = state.get("analysis_result")
    if analysis and analysis.get("root_cause_hypothesis"):
        return analysis["root_cause_hypothesis"]
    routing = state.get("routing_decision")
    if routing:
        return routing
    log = state["error_log"]
    return f"{log['error_type']} in {log['service_name']}: {log['message']}"


def _derive_fix(state) -> dict:
    analysis = state.get("analysis_result")
    if analysis and analysis.get("remediation_steps"):
        fix_plan = "\n".join(analysis["remediation_steps"])
    else:
        # Specialist agents emit an executable fix script, not a plan text —
        # surfaced verbatim as the closest honest "plan".
        fix_plan = state.get("fix_artifact") or state.get("fix_script") or ""
    return {
        "fix_plan": fix_plan,
        "risk_level": _RISK_MAP.get(state.get("security_verdict"), "medium"),
        # The pipeline never produces a unified diff (fix_artifact is an
        # executable script); always empty rather than a fake diff. DEBT.md.
        "code_diff": "",
    }


def _write_result_sidecar(state, source_stem: str, output_dir: Path, report_path: Path) -> None:
    log = state["error_log"]
    result = {
        # API runs: state trace_id == job_id == incoming-file stem. CLI v1
        # runs carry no trace_id — the log stem is the honest identifier.
        "trace_id": state.get("trace_id") or source_stem,
        "status": "completed",
        "diagnosis": {
            "category": _derive_category(state),
            "severity": _derive_severity(state),
            "summary": _derive_summary(state),
        },
        "fix": _derive_fix(state),
        "service_name": log["service_name"],
        "error_type": log["error_type"],
        "report_path": str(report_path.resolve()),
    }
    sidecar_path = output_dir / f"{source_stem}-result.json"
    sidecar_path.write_text(json.dumps(result, indent=2), encoding="utf-8")


def format_report(state) -> dict:
    """Format analysis into a markdown report and write to output/."""
    log = state["error_log"]
    source_stem = Path(state["log_path"]).stem
    generated_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    analysis_block = _analysis_section(state)
    sandbox = _sandbox_section(state)
    security = _security_section(state)

    report = f"""# Diagnostic Report: {log['service_name']}

**Generated**: {generated_at}
**Source log**: {state['log_path']}

## Error Summary

- **Service**: {log['service_name']}
- **Error type**: {log['error_type']}
- **Timestamp**: {log['timestamp']}
- **Message**: {log['message']}

{analysis_block}{sandbox}{security}---
*Report generated by AutoSentinel Core Diagnostic Engine*
"""

    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{source_stem}-report.md"
    report_path.write_text(report, encoding="utf-8")

    _write_result_sidecar(state, source_stem, output_dir, report_path)

    return {"report_text": report, "report_path": str(report_path.resolve())}
