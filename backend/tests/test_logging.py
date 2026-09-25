"""Secrets never reach the access log (docs/auth.md, "Security events")."""

from __future__ import annotations

import logging

from app.core.logging import RedactSecretQueries


def _access_record(path: str) -> logging.LogRecord:
    return logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        __file__,
        0,
        '%s - "%s %s HTTP/%s" %d',
        ("203.0.113.7:5000", "GET", path, "1.1", 303),
        None,
    )


def test_the_google_callback_query_is_redacted() -> None:
    record = _access_record("/api/v1/auth/google/callback?state=abc&code=secret-code")
    RedactSecretQueries().filter(record)
    assert "secret-code" not in record.getMessage()
    assert "/api/v1/auth/google/callback?[redacted]" in record.getMessage()


def test_other_queries_are_left_alone() -> None:
    record = _access_record("/api/v1/catalog?page=2")
    RedactSecretQueries().filter(record)
    assert "/api/v1/catalog?page=2" in record.getMessage()
