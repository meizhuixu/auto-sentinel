"""asyncio.Queue, AlertJob, and the background worker coroutine."""

import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from autosentinel import run_pipeline
from autosentinel.api.logging import get_logger

_logger = get_logger("event_gateway")


@dataclass
class AlertJob:
    job_id: str
    log_path: Path
    service_name: str
    enqueued_at: str


async def worker(queue: asyncio.Queue) -> None:
    """Consume AlertJob items and run the diagnostic pipeline in a thread.

    CancelledError propagates naturally so the caller can detect cancellation.
    """
    while True:
        job: AlertJob = await queue.get()
        start = time.monotonic()
        _logger.info(
            "processing_started",
            extra={
                "correlation_id": job.job_id,
                "trace_id": job.job_id,
                "event": "processing_started",
                "event_payload": {
                    "service_name": job.service_name,
                    "log_path": str(job.log_path),
                },
            },
        )
        try:
            report_path = await asyncio.to_thread(run_pipeline, job.log_path)
            duration_ms = int((time.monotonic() - start) * 1000)
            _logger.info(
                "processing_completed",
                extra={
                    "correlation_id": job.job_id,
                    "trace_id": job.job_id,
                    "event": "processing_completed",
                    "event_payload": {
                        "service_name": job.service_name,
                        "report_path": str(report_path),
                        "duration_ms": duration_ms,
                    },
                },
            )
        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            _logger.error(
                "processing_failed",
                extra={
                    "correlation_id": job.job_id,
                    "trace_id": job.job_id,
                    "event": "processing_failed",
                    "event_payload": {
                        "service_name": job.service_name,
                        "error": str(exc),
                        "duration_ms": duration_ms,
                    },
                },
            )
        finally:
            queue.task_done()
