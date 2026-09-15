"""Series endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination, RequestLocale
from app.api.errors import ProblemError
from app.schemas.catalog import CatalogListItem
from app.schemas.common import Page
from app.schemas.series import SeriesCreate, SeriesOut, SeriesProgressOut, SeriesSummaryOut
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
    locale: RequestLocale,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
    scope: Annotated[Literal["mine", "catalog"], Query()] = "mine",
) -> list[SeriesOut]:
    """`scope=mine` (default) is the user's own collection — the "Серії"
    screen and the dashboard, unrestricted by which countries the catalogue
    project has confirmed. `scope=catalog` is `GET /catalog`'s own series
    filter: a harder, separate gate (§13a), only a `catalog_confirmed`
    country's series."""
    return await SeriesService(session, user, locale).list_series(
        country_id, confirmed_only=scope == "catalog"
    )


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_series(
    session: DbSession, user: CurrentUser, locale: RequestLocale, payload: SeriesCreate
) -> SeriesOut:
    try:
        return await SeriesService(session, user, locale).create(payload)
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


@router.get("/summary")
async def series_progress(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[SeriesProgressOut]:
    return await SeriesService(session, user, locale).list_progress(country_id)


@router.get("/{series_id}/summary")
async def series_summary(
    session: DbSession, user: CurrentUser, locale: RequestLocale, series_id: int
) -> SeriesSummaryOut:
    try:
        return await SeriesService(session, user, locale).summary(series_id)
    except SeriesNotFoundError as exc:
        raise ProblemError(
            status.HTTP_404_NOT_FOUND,
            "series-not-found",
            "Not found",
            "The series does not exist.",
        ) from exc


@router.get("/{series_id}/items")
async def series_items(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    pagination: Pagination,
    series_id: int,
) -> Page[CatalogListItem]:
    """The series detail screen's own tiles -- shared or personal, regardless
    of catalog_confirmed. Deliberately not `GET /catalog?seriesId=`: that
    endpoint is the catalogue browse experience and its harder gate (§13a)
    would hide a user's own coins of a country the catalogue project has not
    confirmed yet, same bug as summary() below would have if it used it."""
    try:
        items, total = await SeriesService(session, user, locale).list_items(
            series_id, limit=pagination.page_size, offset=pagination.offset
        )
    except SeriesNotFoundError as exc:
        raise ProblemError(
            status.HTTP_404_NOT_FOUND,
            "series-not-found",
            "Not found",
            "The series does not exist.",
        ) from exc
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)
