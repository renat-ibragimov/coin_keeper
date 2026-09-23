"""Series endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import (
    ClientIp,
    CurrentUser,
    DbSession,
    OptionalCurrentUser,
    RequestLocale,
)
from app.api.errors import ProblemError
from app.api.public_rate_limit import enforce_public_read
from app.core import rate_limit
from app.schemas.series import SeriesCreate, SeriesOut, SeriesProgressOut
from app.services.series import (
    DuplicateSeriesError,
    SeriesForbiddenError,
    SeriesService,
    UnknownCountryError,
)

router = APIRouter(prefix="/series", tags=["series"])


@router.get("")
async def list_series(
    session: DbSession,
    user: OptionalCurrentUser,
    locale: RequestLocale,
    ip: ClientIp,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
    scope: Annotated[Literal["mine", "catalog"], Query()] = "mine",
) -> list[SeriesOut]:
    """`scope=mine` (default) is the user's own collection — the "Серії"
    screen and the dashboard, unrestricted by which countries the catalogue
    project has confirmed. `scope=catalog` is `GET /catalog`'s own series
    filter: a harder, separate gate (§13a), only a `catalog_confirmed`
    country's series."""
    await enforce_public_read(rate_limit.PUBLIC_REFERENCE, user, ip)
    if user is None:
        if scope != "catalog":
            raise ProblemError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "private-series-filter",
                "Invalid filter",
                "This filter requires an account.",
            )
        from app.repositories.series import SeriesRepository
        from app.services.series import _out

        series = await SeriesRepository(session, user_id=-1, locale=locale).list_series(
            country_id, confirmed_only=True
        )
        return [_out(item, locale) for item in series]
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
