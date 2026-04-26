"""Shared TypedDict models for the diagnostic pipeline."""

from typing import Optional
from typing_extensions import TypedDict


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
