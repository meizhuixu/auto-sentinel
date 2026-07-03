"""Pydantic request/response models for the event gateway API."""

from typing import Optional

from pydantic import BaseModel


class AlertPayload(BaseModel):
    model_config = {"extra": "ignore"}

    service_name: str
    error_type: str
    message: str
    timestamp: str
    stack_trace: Optional[str] = None


class ResumeRequest(BaseModel):
    """Body for POST /incidents/{incident_id}/resume (T036)."""

    model_config = {"extra": "ignore"}

    decision: str  # "approve" | "reject"
    reviewer_notes: str = ""


class AlertJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
    # Sprint 5 (T045): the incident id doubles as the trace_id (one 32-char
    # lowercase hex value, == job_id), surfaced so callers can correlate the
    # incident with its Langfuse trace.
    trace_id: str


# ── M4 MCP enabler (specs/m4-mcp-enabler) ──────────────────────────────────
# Read-path models render whatever the result sidecar holds, so fields are
# plain `str` — the sidecar writer (nodes/format_report.py) enforces the
# vocabulary (category: runtime|build|infra|config|unknown; severity:
# low|medium|high|critical; risk_level: low|medium|high).


class DiagnosisResult(BaseModel):
    category: str
    severity: str
    summary: str


class FixResult(BaseModel):
    fix_plan: str
    risk_level: str
    code_diff: str  # unified diff; always "" today (see DEBT.md)


class AlertStatusResponse(BaseModel):
    """Body for GET /api/v1/alerts/{job_id} (FR-003)."""

    job_id: str
    trace_id: str
    status: str  # "processing" | "completed" | "failed"
    diagnosis: Optional[DiagnosisResult] = None
    fix: Optional[FixResult] = None
    report_path: Optional[str] = None


class IncidentSummary(BaseModel):
    id: str  # == trace_id
    title: str
    resolution: str


class IncidentSearchResponse(BaseModel):
    """Body for GET /api/v1/incidents (FR-004)."""

    incidents: list[IncidentSummary]
