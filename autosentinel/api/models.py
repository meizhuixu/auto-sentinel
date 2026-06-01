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
