"""Shared TypedDict models for the diagnostic pipeline."""

import operator
from typing import Annotated, Optional
from typing_extensions import NotRequired, TypedDict


class ErrorLog(TypedDict):
    timestamp: str
    service_name: str
    error_type: str
    message: str
    stack_trace: Optional[str]


class AnalysisResult(TypedDict):
    error_category: str
    root_cause_hypothesis: str
    confidence: float
    remediation_steps: list[str]


class ExecutionResult(TypedDict):
    status: str           # "success" | "failure" | "timeout" | "error" | "skipped"
    return_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: int
    error: Optional[str]


class DiagnosticState(TypedDict):
    log_path: str
    error_log: Optional[ErrorLog]
    parse_error: Optional[str]
    analysis_result: Optional[AnalysisResult]
    analysis_error: Optional[str]
    fix_script: Optional[str]
    execution_result: Optional[ExecutionResult]
    execution_error: Optional[str]
    report_text: Optional[str]
    report_path: Optional[str]


class AgentState(TypedDict):
    # ── Sprint 1–3 (unchanged) ──────────────────────────────────────────
    log_path: str
    error_log: Optional[ErrorLog]
    parse_error: Optional[str]
    analysis_result: Optional[AnalysisResult]
    analysis_error: Optional[str]
    fix_script: Optional[str]
    execution_result: Optional[ExecutionResult]
    execution_error: Optional[str]
    report_text: Optional[str]
    report_path: Optional[str]
    # ── Sprint 4 (new) ──────────────────────────────────────────────────
    error_category: Optional[str]                         # CODE | INFRA | CONFIG | SECURITY
    fix_artifact: Optional[str]                           # produced by specialist agent
    security_verdict: Optional[str]                       # SAFE | CAUTION | HIGH_RISK
    routing_decision: Optional[str]                       # human-readable routing log
    agent_trace: Annotated[list[str], operator.add]       # retained for Sprint 5 fan-out
    approval_required: bool
    # ── Sprint 5 (new) ──────────────────────────────────────────────────
    # trace_id: 32-char lowercase hex; stamped at FastAPI ingest, threaded
    # through the pipeline. Regex-validated inside LLMRequest (data-model.md §2),
    # NOT here — TypedDict cannot run validators. NotRequired so Sprint 1-4
    # AgentState literals (which omit it) keep type-checking.
    trace_id: NotRequired[str]
    # cost_accumulated_usd: float (NOT Decimal) per data-model.md §8 — JSON
    # round-trip through PostgresSaver requires native JSON types; Decimal
    # needs a custom serialiser. CostGuardState.total_spent_usd remains
    # Decimal as the source of truth; this is a mirror for in-state visibility.
    cost_accumulated_usd: NotRequired[float]
    security_classifier_model: NotRequired[str]
