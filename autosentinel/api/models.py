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


class AlertJobResponse(BaseModel):
    job_id: str
    status: str
    message: str
