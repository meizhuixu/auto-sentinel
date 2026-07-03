"""Shared TypedDict models for the diagnostic pipeline."""

import operator
from typing import Annotated, Literal, Optional
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
    routing_decision: Optional[str]                       # LLM rationale (free text) from Supervisor
    specialist: Optional[Literal["code_fixer", "infra_sre"]]  # graph router short-key (T039)
    agent_trace: Annotated[list[str], operator.add]       # retained for Sprint 5 fan-out
    approval_required: bool
    # ── Sprint 5 (new) ──────────────────────────────────────────────────
    # trace_id: 32-char lowercase hex; stamped at FastAPI ingest, threaded
    # through the pipeline. Regex-validated inside LLMRequest (data-model.md §2),
    # NOT here — TypedDict cannot run validators. NotRequired so Sprint 1-4
    # AgentState literals (which omit it) keep type-checking.
    trace_id: NotRequired[str]
    # cost_accumulated: float (NOT Decimal) per data-model.md §8 — JSON
    # round-trip through PostgresSaver requires native JSON types; Decimal
    # needs a custom serialiser. CostGuardState.total_spent remains Decimal as
    # the source of truth; this is a mirror for in-state visibility. Amount is
    # in the CostGuard's currency (CNY in Sprint 5).
    cost_accumulated: NotRequired[float]
    security_classifier_model: NotRequired[str]
    # cost_exhausted: set True by the graph's _guarded wrapper when an LLM-call
    # agent raises CostGuardError; the post-node conditional edges route to
    # cost_exhausted_node (END) instead of the normal successor (T042/T043).
    cost_exhausted: NotRequired[bool]
    # ── Sprint 6 (006-fix-verification-integrity) ───────────────────────
    # fix_normalization: Verifier-side artifact normalization audit record
    # ({"outcome": "verbatim"|"wrapped"|"rejected", "reason": str|None}).
    # Plain dict (not a model) — must JSON-round-trip through PostgresSaver.
    fix_normalization: NotRequired[dict]
