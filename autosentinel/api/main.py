"""FastAPI application: event gateway for asynchronous crash-log ingestion."""

import asyncio
import json
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request

from autosentinel.api import results as results_store
from autosentinel.api.logging import get_logger
from autosentinel.api.models import (
    AlertJobResponse,
    AlertPayload,
    AlertStatusResponse,
    DiagnosisResult,
    FixResult,
    IncidentSearchResponse,
    IncidentSummary,
    ResumeRequest,
)
from autosentinel.api.queue import AlertJob, worker

_logger = get_logger("event_gateway")
_INCOMING = Path("data/incoming")

# M4 (FR-005): caller-supplied trace id must be the bare 32-hex OTel-compatible
# form enforced by LLMRequest (autosentinel/llm/protocol.py).
_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _INCOMING.mkdir(parents=True, exist_ok=True)
    queue: asyncio.Queue = asyncio.Queue()
    app.state.queue = queue
    app.state.loop = asyncio.get_running_loop()
    task = asyncio.create_task(worker(queue))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def create_app() -> FastAPI:
    app = FastAPI(title="AutoSentinel Event Gateway", lifespan=lifespan)

    @app.post("/api/v1/alerts", status_code=202, response_model=AlertJobResponse)
    async def ingest_alert(
        payload: AlertPayload,
        request: Request,
        x_trace_id: Optional[str] = Header(default=None, alias="X-Trace-Id"),
    ) -> AlertJobResponse:
        # T045: one 32-char lowercase hex id serves as BOTH job_id and trace_id
        # (decision: trace_id == job_id). token_hex(16) satisfies LLMRequest's
        # ^[0-9a-f]{32}$ trace_id regex (uuid4's hyphenated 36-char form did not).
        #
        # M4 (FR-005): an optional X-Trace-Id header lets the upstream caller
        # (devcontext-mcp) supply that id so one trace spans both services.
        # Chosen over W3C traceparent: the contract is a bare 32-hex trace id
        # with no span-context semantics. Collision behavior is documented:
        # resubmitting the same id overwrites data/incoming/{id}.json —
        # last write wins; callers own id uniqueness.
        if x_trace_id is None:
            job_id = secrets.token_hex(16)
        elif _TRACE_ID_RE.fullmatch(x_trace_id):
            job_id = x_trace_id
        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    "invalid X-Trace-Id: must be a 32-character lowercase hex "
                    "string matching ^[0-9a-f]{32}$"
                ),
            )
        trace_id = job_id
        queue: asyncio.Queue = request.app.state.queue

        log_file = _INCOMING / f"{job_id}.json"
        log_file.write_text(json.dumps(payload.model_dump()))

        _logger.info(
            "alert_received",
            extra={
                "correlation_id": job_id,
                "trace_id": job_id,
                "event": "alert_received",
                "event_payload": {
                    "service_name": payload.service_name,
                    "error_type": payload.error_type,
                },
            },
        )

        job = AlertJob(
            job_id=job_id,
            log_path=log_file,
            service_name=payload.service_name,
            enqueued_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            trace_id=trace_id,
        )
        await queue.put(job)

        _logger.info(
            "alert_queued",
            extra={
                "correlation_id": job_id,
                "trace_id": job_id,
                "event": "alert_queued",
                "event_payload": {
                    "service_name": payload.service_name,
                    "queue_depth": queue.qsize(),
                },
            },
        )

        return AlertJobResponse(
            job_id=job_id,
            status="accepted",
            message="Alert accepted for processing",
            trace_id=trace_id,
        )

    @app.get("/api/v1/alerts/{job_id}", response_model=AlertStatusResponse)
    async def get_alert_status(job_id: str) -> AlertStatusResponse:
        """M4 (FR-003): poll a submitted alert for its structured result.

        Resolution order: result sidecar (completed/failed) → incoming file
        (processing) → 404.
        """
        data = results_store.load_result(job_id)
        if data is not None:
            diagnosis = data.get("diagnosis")
            fix = data.get("fix")
            return AlertStatusResponse(
                job_id=job_id,
                trace_id=str(data.get("trace_id") or job_id),
                status=str(data.get("status") or "completed"),
                diagnosis=DiagnosisResult(**diagnosis) if diagnosis else None,
                fix=FixResult(**fix) if fix else None,
                report_path=data.get("report_path"),
            )
        if results_store.incoming_path(job_id).exists():
            # Accepted (202 semantics) but the worker has not finished; HTTP
            # 200 with an explicit status field, per the MCP-facing contract.
            return AlertStatusResponse(
                job_id=job_id, trace_id=job_id, status="processing"
            )
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")

    @app.get("/api/v1/incidents", response_model=IncidentSearchResponse)
    async def search_incidents(q: str, limit: int = 5) -> IncidentSearchResponse:
        """M4 (FR-004): keyword search over stored incidents.

        `limit` defaults to 5 and is clamped (not rejected) to 1..50 inside
        results_store.search_incidents.
        """
        matches = results_store.search_incidents(q, limit)
        return IncidentSearchResponse(
            incidents=[IncidentSummary(**match) for match in matches]
        )

    @app.post("/incidents/{incident_id}/resume", status_code=200)
    async def resume_incident(incident_id: str, body: ResumeRequest) -> dict:
        """T036: resume a pipeline suspended at the HIGH_RISK approval gate.

        Binds to the same env-gated checkpointer (T035) that persisted the
        interrupt, then replays from the checkpoint via Command(resume=...).
        The already-completed specialist nodes are NOT re-run (LangGraph
        resumes from the saved superstep); only post-interrupt nodes execute.
        """
        from langgraph.types import Command

        from autosentinel.multi_agent_graph import build_multi_agent_graph

        graph = build_multi_agent_graph()
        cfg = {"configurable": {"thread_id": incident_id}}

        # 404 when there is no suspended checkpoint for this incident.
        snapshot = graph.get_state(cfg)
        if not snapshot.values:
            raise HTTPException(
                status_code=404, detail=f"no resumable incident {incident_id!r}"
            )

        # Run the (potentially blocking) resume off the event loop.
        result = await asyncio.to_thread(
            graph.invoke, Command(resume=body.model_dump()), cfg
        )

        _logger.info(
            "incident_resumed",
            extra={
                "correlation_id": incident_id,
                "trace_id": result.get("trace_id", incident_id),
                "event": "incident_resumed",
                "event_payload": {"decision": body.decision},
            },
        )

        execution_result = result.get("execution_result") or {}
        return {
            "incident_id": incident_id,
            "trace_id": result.get("trace_id", incident_id),
            "decision": body.decision,
            "approval_required": result.get("approval_required"),
            "security_verdict": result.get("security_verdict"),
            "execution_status": execution_result.get("status"),
            "agent_trace": result.get("agent_trace", []),
            "report_path": result.get("report_path"),
        }

    return app


app = create_app()  # pragma: no cover
