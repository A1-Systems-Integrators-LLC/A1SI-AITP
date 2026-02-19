"""Structured JSON logging formatter for production observability."""

import json
import logging
import time
from contextvars import ContextVar

# Request ID propagation via contextvars (set by RequestIDMiddleware)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    """Emit log records as single-line JSON for machine parsing.

    Output format:
        {"ts": "2026-02-19T12:00:00Z", "level": "INFO", "logger": "trading",
         "msg": "Order created", "request_id": "abc123", ...extra}
    """

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Attach request ID if available
        rid = request_id_var.get("")
        if rid:
            entry["request_id"] = rid

        # Attach extra fields passed via logger.info("msg", extra={...})
        for key in ("request_id", "method", "path", "status", "duration_ms",
                     "user", "ip", "view"):
            val = getattr(record, key, None)
            if val is not None and key not in entry:
                entry[key] = val

        # Exception info
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)

    def formatTime(self, record, datefmt=None):  # noqa: N802
        """Use UTC time for structured logs."""
        ct = time.gmtime(record.created)
        if datefmt:
            return time.strftime(datefmt, ct)
        return time.strftime("%Y-%m-%dT%H:%M:%S", ct)
