"""RFC 7807 problem responses (docs/03-api-contract.md)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

CONTENT_TYPE = "application/problem+json"
PROBLEM_BASE = "https://coinkeeper.app/problems"


class ProblemError(HTTPException):
    """An HTTPException carrying an RFC 7807 problem type."""

    def __init__(
        self,
        status_code: int,
        problem_type: str,
        title: str,
        detail: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.problem_type = problem_type
        self.title = title


def problem_response(
    status_code: int,
    problem_type: str,
    title: str,
    detail: str,
    headers: Mapping[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "type": f"{PROBLEM_BASE}/{problem_type}",
        "title": title,
        "status": status_code,
        "detail": detail,
    }
    if extra:
        payload.update(extra)
    return JSONResponse(payload, status_code=status_code, media_type=CONTENT_TYPE, headers=headers)


async def problem_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ProblemError)
    return problem_response(
        exc.status_code,
        exc.problem_type,
        exc.title,
        str(exc.detail),
        headers=exc.headers,
    )


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, HTTPException)
    return problem_response(
        exc.status_code,
        "http-error",
        _TITLES.get(exc.status_code, "Request failed"),
        str(exc.detail),
        headers=exc.headers,
    )


async def validation_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return problem_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation-error",
        "Request validation failed",
        "One or more fields are invalid.",
        extra={"errors": _serialise_errors(exc)},
    )


def _serialise_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {
            "field": ".".join(str(part) for part in error["loc"][1:]),
            "message": error["msg"],
        }
        for error in exc.errors()
    ]


_TITLES = {
    status.HTTP_400_BAD_REQUEST: "Bad request",
    status.HTTP_401_UNAUTHORIZED: "Not authenticated",
    status.HTTP_403_FORBIDDEN: "Forbidden",
    status.HTTP_404_NOT_FOUND: "Not found",
    status.HTTP_409_CONFLICT: "Conflict",
    status.HTTP_429_TOO_MANY_REQUESTS: "Too many requests",
}
