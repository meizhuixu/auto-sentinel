"""parse_log node — reads and validates a JSON error log file."""

import json
from pathlib import Path

from autosentinel.models import DiagnosticState, ErrorLog

_REQUIRED_FIELDS = ("timestamp", "service_name", "error_type", "message")


def parse_log(state: DiagnosticState) -> dict:
    """Read and validate the JSON log file at state['log_path']."""
    log_path = Path(state["log_path"])
    try:
        raw = log_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {
            "error_log": None,
            "parse_error": f"Log file not found: {log_path}",
        }

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "error_log": None,
            "parse_error": f"Invalid JSON in {log_path.name}: {exc}",
        }

    missing = [f for f in _REQUIRED_FIELDS if not data.get(f)]
    if missing:
        return {
            "error_log": None,
            "parse_error": (
                f"Missing required fields in {log_path.name}: {', '.join(missing)}"
            ),
        }

    error_log = ErrorLog(
        timestamp=data["timestamp"],
        service_name=data["service_name"],
        error_type=data["error_type"],
        message=data["message"],
        stack_trace=data.get("stack_trace"),
    )
    return {"error_log": error_log, "parse_error": None}
