"""Collection endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination, RequestLocale
from app.api.errors import ProblemError
from app.models.enums import CollectionGroup
from app.repositories.collection import CollectionFilters
from app.schemas.catalog import CoinMaterial
from app.schemas.collection import (
    CollectionItemCreate,
    CollectionItemOut,
    CollectionItemUpdate,
    CollectionPositionOut,
)
from app.schemas.common import Page
from app.schemas.reference import CountryOut, DenominationOut
from app.schemas.series import SeriesOut
from app.services.collection import (
    CatalogItemNotFoundError,
    CollectionItemNotFoundError,
    CollectionService,
    MissingRateError,
    UnknownCurrencyError,
)

router = APIRouter(prefix="/collection", tags=["collection"])


def _not_found(what: str) -> ProblemError:
    return ProblemError(status.HTTP_404_NOT_FOUND, f"{what}-not-found", "Not found", "Not found.")


def _unprocessable(problem_type: str, detail: str) -> ProblemError:
    return ProblemError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, problem_type, "Request rejected", detail
    )


@router.get("")
async def list_collection(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200)] = None,
    country_id: Annotated[list[int] | None, Query(alias="countryId")] = None,
    series_id: Annotated[list[int] | None, Query(alias="seriesId")] = None,
    year: Annotated[int | None, Query()] = None,
    year_from: Annotated[int | None, Query(alias="yearFrom")] = None,
    year_to: Annotated[int | None, Query(alias="yearTo")] = None,
    denomination_id: Annotated[list[int] | None, Query(alias="denominationId")] = None,
    group: Annotated[list[CollectionGroup] | None, Query()] = None,
    material_id: Annotated[list[int] | None, Query(alias="materialId")] = None,
    grade: Annotated[str | None, Query(max_length=50)] = None,
    sort: Annotated[
        Literal["date", "title", "country", "series", "quantity", "total", "valuation", "grade"],
        Query(),
    ] = "title",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> Page[CollectionPositionOut]:
    filters = CollectionFilters(
        q=q,
        country_ids=country_id,
        series_ids=series_id,
        year=year,
        year_from=year_from,
        year_to=year_to,
        denomination_ids=denomination_id,
        groups=group,
        material_ids=material_id,
        grade=grade,
        sort=sort,
        order=order,
    )
    items, total = await CollectionService(session, user, locale).list_positions(
        filters, limit=pagination.page_size, offset=pagination.offset
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    session: DbSession, user: CurrentUser, locale: RequestLocale, payload: CollectionItemCreate
) -> CollectionItemOut:
    try:
        return await CollectionService(session, user, locale).create(payload)
    except CatalogItemNotFoundError as exc:
        raise _not_found("catalog-item") from exc
    except UnknownCurrencyError as exc:
        raise _unprocessable("unknown-currency", exc.detail) from exc
    except MissingRateError as exc:
        raise _unprocessable("exchange-rate-missing", exc.detail) from exc


@router.get("/countries")
async def list_owned_countries(
    session: DbSession, user: CurrentUser, locale: RequestLocale
) -> list[CountryOut]:
    """Countries the owner holds at least one purchase from — narrower than
    `GET /countries`, for the "Мої монети" filters panel (docs/03)."""
    return await CollectionService(session, user, locale).list_owned_countries()


@router.get("/series")
async def list_owned_series(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[SeriesOut]:
    return await CollectionService(session, user, locale).list_owned_series(country_id)


@router.get("/denominations")
async def list_owned_denominations(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[DenominationOut]:
    return await CollectionService(session, user, locale).list_owned_denominations(country_id)


@router.get("/materials")
async def list_owned_materials(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[CoinMaterial]:
    return await CollectionService(session, user, locale).list_owned_materials(country_id)


# NOTE: these four literal routes must stay registered before /{item_id} —
# otherwise FastAPI tries to parse "countries"/"series"/"denominations"/
# "materials" as item_id and 422s instead of matching the routes above.
@router.get("/{item_id}")
async def get_item(
    session: DbSession, user: CurrentUser, locale: RequestLocale, item_id: int
) -> CollectionItemOut:
    try:
        return await CollectionService(session, user, locale).get(item_id)
    except CollectionItemNotFoundError as exc:
        raise _not_found("collection-item") from exc


@router.patch("/{item_id}")
async def update_item(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    item_id: int,
    payload: CollectionItemUpdate,
) -> CollectionItemOut:
    try:
        return await CollectionService(session, user, locale).update(item_id, payload)
    except CollectionItemNotFoundError as exc:
        raise _not_found("collection-item") from exc
    except UnknownCurrencyError as exc:
        raise _unprocessable("unknown-currency", exc.detail) from exc
    except MissingRateError as exc:
        raise _unprocessable("exchange-rate-missing", exc.detail) from exc


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    session: DbSession, user: CurrentUser, locale: RequestLocale, item_id: int
) -> None:
    try:
        await CollectionService(session, user, locale).delete(item_id)
    except CollectionItemNotFoundError as exc:
        raise _not_found("collection-item") from exc
