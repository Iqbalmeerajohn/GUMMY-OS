"""Structured JSON logging (per CONVENTIONS.md §7).

A single stdout handler emits one JSON object per line — friendly to Render/Fly
log drains and easy to ship to a log aggregator later. No third-party dependency.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

# Attributes present on every LogRecord; everything else passed via ``extra=``
# is a structured field we want to surface in the JSON line (e.g. timing fields).
_RESERVED_LOG_ATTRS = set(logging.makeLogRecord({}).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    """Render log records as compact JSON lines.

    Any structured fields attached via ``logger.info(msg, extra={...})`` are
    merged into the JSON object, so timing/diagnostic data (e.g.
    ``total_turn_ms``) is queryable in the log drain, not buried in the message.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_LOG_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "info") -> None:
    """Install the JSON handler on the root logger and align uvicorn loggers."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Let uvicorn records flow through our root handler instead of its own.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
