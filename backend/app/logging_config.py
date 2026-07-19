"""Structured JSON logging with automatic redaction (PRD §9.6, rule #10).

Every log line is a single JSON object carrying a correlation id (request id) so a
whole PR review can be traced. A redaction filter runs on every record so secrets or
PII can never reach the log sink, even if a developer logs something careless.
"""

from __future__ import annotations

import contextvars
import datetime as dt
import json
import logging
from typing import Any

from app.core.security.redaction import redact_text, redact_value

# Correlation id for the current request/task, attached to every log line.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_RESERVED = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
    }
)


class RedactionFilter(logging.Filter):
    """Scrub secret patterns from the rendered message and structured extras."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact_text(record.getMessage())
        except Exception:
            record.msg = "<unrenderable log message>"
        record.args = ()
        for key, value in list(record.__dict__.items()):
            if key not in _RESERVED and not key.startswith("_"):
                record.__dict__[key] = redact_value(value)
        return True


class JsonFormatter(logging.Formatter):
    """Render a log record as one compact, redacted JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": dt.datetime.fromtimestamp(record.created, tz=dt.UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str = "INFO", service_name: str = "codeguardian") -> None:
    """Install the JSON formatter + redaction filter on the root logger."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Tame noisy third-party loggers; they still pass through redaction.
    for noisy in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel("WARNING")

    logging.getLogger(__name__).info("logging configured", extra={"service": service_name})
