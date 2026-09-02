"""Series endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession
from app.api.errors import ProblemError
from app.schemas.series import SeriesCreate, SeriesOut, SeriesSummaryOut
from app.services.series import (
    DuplicateSeriesError,
    SeriesForbiddenError,
    SeriesNotFoundError,
    SeriesService,
    UnknownCountryError,
)

router = APIRouter(prefix="/series", tags=["series"])


@router.get("")
async def list_series(
    session: DbSession,
    user: CurrentUser,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[SeriesOut]:
    return await SeriesService(session, user).list_series(country_id)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_series(session: DbSession, user: CurrentUser, payload: SeriesCreate) -> SeriesOut:
    try:
        return await SeriesService(session, user).create(payload)
    except SeriesForbiddenError as exc:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "admin-required",
            "Forbidden",
            "Series are shared reference data; only an administrator can create them.",
        ) from exc
    except UnknownCountryError as exc:
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid-reference",
            "Request rejected",
            exc.detail,
        ) from exc
    except DuplicateSeriesError as exc:
        raise ProblemError(
            status.HTTP_409_CONFLICT, "series-exists", "Conflict", exc.detail
        ) from exc


@router.get("/{series_id}/summary")
async def series_summary(session: DbSession, user: CurrentUser, series_id: int) -> SeriesSummaryOut:
    try:
        return await SeriesService(session, user).summary(series_id)
    except SeriesNotFoundError as exc:
        raise ProblemError(
            status.HTTP_404_NOT_FOUND,
            "series-not-found",
            "Not found",
            "The series does not exist.",
        ) from exc
