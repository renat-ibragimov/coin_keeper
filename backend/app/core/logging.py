"""Structured JSON logging to stdout (docs/infra.md)."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in _RESERVED:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


# Paths whose query string carries a secret: the Google callback's one-time
# authorization code and state.
_REDACTED_QUERY_PATHS = ("/api/v1/auth/google/callback",)


class RedactSecretQueries(logging.Filter):
    """Drops the query string of secret-carrying paths from uvicorn's access
    log, whose record args are (client, method, path, http_version, status)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            path = args[2]
            if path.startswith(_REDACTED_QUERY_PATHS) and "?" in path:
                record.args = (*args[:2], path.split("?", 1)[0] + "?[redacted]", *args[3:])
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    access = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactSecretQueries) for f in access.filters):
        access.addFilter(RedactSecretQueries())
