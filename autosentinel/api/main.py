"""FastAPI application: event gateway for asynchronous crash-log ingestion."""

import asyncio
import json
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request

from autosentinel.api.logging import get_logger
from autosentinel.api.models import AlertJobResponse, AlertPayload, ResumeRequest
from autosentinel.api.queue import AlertJob, worker

_logger = get_logger("event_gateway")
_INCOMING = Path("data/incoming")


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
    async def ingest_alert(payload: AlertPayload, request: Request) -> AlertJobResponse:
        # T045: one 32-char lowercase hex id serves as BOTH job_id and trace_id
        # (decision: trace_id == job_id). token_hex(16) satisfies LLMRequest's
        # ^[0-9a-f]{32}$ trace_id regex (uuid4's hyphenated 36-char form did not).
        job_id = secrets.token_hex(16)
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
