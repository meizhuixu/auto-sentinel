"""Result-sidecar access + incident keyword search (M4 MCP enabler).

The pipeline writes `output/{stem}-result.json` (see nodes/format_report.py,
FR-001) and the queue worker writes a `status="failed"` sidecar on pipeline
error (FR-002). This module is the read/search side consumed by the gateway
routes — filesystem paths are CWD-relative, matching the gateway's existing
`data/incoming/` convention.
"""

import json
from pathlib import Path
from typing import Optional

from autosentinel.api.logging import get_logger

_logger = get_logger("event_gateway")

_OUTPUT = Path("output")
_INCOMING = Path("data/incoming")

_RESULT_SUFFIX = "-result.json"


def result_path(job_id: str) -> Path:
    return _OUTPUT / f"{job_id}{_RESULT_SUFFIX}"


def load_result(job_id: str) -> Optional[dict]:
    """Return the parsed result sidecar for job_id, or None when absent.

    The sidecar is written by this codebase; a malformed file is a bug and
    is allowed to raise (surfaces as a 500) rather than masquerade as
    "processing".
    """
    path = result_path(job_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def incoming_path(job_id: str) -> Path:
    return _INCOMING / f"{job_id}.json"


def write_failed_result(
    job_id: str, *, trace_id: str, service_name: str, error: str
) -> None:
    """FR-002: persist a status="failed" sidecar. Best-effort — a sidecar
    write failure is logged and swallowed so it can never crash the worker."""
    payload = {
        "trace_id": trace_id or job_id,
        "status": "failed",
        "diagnosis": None,
        "fix": None,
        "service_name": service_name,
        "error_type": None,
        "error": error,
    }
    try:
        _OUTPUT.mkdir(parents=True, exist_ok=True)
        result_path(job_id).write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        _logger.warning(
            "result_sidecar_write_failed",
            extra={
                "correlation_id": job_id,
                "trace_id": trace_id or job_id,
                "event": "result_sidecar_write_failed",
                "event_payload": {"error": str(exc)},
            },
        )


def search_incidents(q: str, limit: int) -> list[dict]:
    """FR-004: case-insensitive keyword search over stored incidents.

    Corpus: every output/*-result.json plus, when present, the sibling
    data/incoming/{job_id}.json payload (message / stack_trace). Score =
    number of (term, field) hits; score 0 excluded; ties broken by id.
    `limit` is clamped to 1..50 (default handled by the route).
    """
    limit = max(1, min(50, limit))
    terms = q.lower().split()

    scored: list[tuple[int, str, str, str]] = []
    for path in sorted(_OUTPUT.glob(f"*{_RESULT_SUFFIX}")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # defensive: junk in output/ must not break search

        job_id = path.name[: -len(_RESULT_SUFFIX)]
        diagnosis = data.get("diagnosis") or {}
        fix = data.get("fix") or {}
        error_type = str(data.get("error_type") or "")
        service_name = str(data.get("service_name") or "")
        summary = str(diagnosis.get("summary") or "")
        fix_plan = str(fix.get("fix_plan") or "")

        haystack = [error_type, service_name, summary, fix_plan]
        incoming = incoming_path(job_id)
        if incoming.exists():
            payload = json.loads(incoming.read_text(encoding="utf-8"))
            haystack.append(str(payload.get("message") or ""))
            haystack.append(str(payload.get("stack_trace") or ""))

        score = sum(
            1 for term in terms for field in haystack if term in field.lower()
        )
        if score == 0:
            continue

        if error_type and service_name:
            title = f"{error_type} in {service_name}"
        elif summary:
            title = summary[:80]
        else:
            title = job_id
        resolution = fix_plan or summary

        scored.append((score, str(data.get("trace_id") or job_id), title, resolution))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [
        {"id": incident_id, "title": title, "resolution": resolution}
        for (_, incident_id, title, resolution) in scored[:limit]
    ]
