"""Structured JSON logging for the event gateway (Constitution Principle IV)."""

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "severity": record.levelname,
            "component": record.name.replace("autosentinel.", "", 1),
            "correlation_id": getattr(record, "correlation_id", ""),
            "trace_id": getattr(record, "trace_id", ""),
            "event": getattr(record, "event", record.getMessage()),
            "event_payload": getattr(record, "event_payload", {}),
        })


def get_logger(component: str) -> logging.Logger:
    logger = logging.getLogger(f"autosentinel.{component}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger
