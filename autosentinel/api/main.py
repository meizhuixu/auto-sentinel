"""FastAPI application: event gateway for asynchronous crash-log ingestion."""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request

from autosentinel.api.logging import get_logger
from autosentinel.api.models import AlertJobResponse, AlertPayload
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
        job_id = str(uuid.uuid4())
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
        )

    return app


app = create_app()  # pragma: no cover
