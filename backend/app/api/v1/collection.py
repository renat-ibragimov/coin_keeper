"""Collection endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination, RequestLocale
from app.api.errors import ProblemError
from app.repositories.collection import CollectionFilters
from app.schemas.collection import (
    CollectionItemCreate,
    CollectionItemOut,
    CollectionItemUpdate,
)
from app.schemas.common import Page
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
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
    series_id: Annotated[int | None, Query(alias="seriesId")] = None,
    sort: Annotated[Literal["date", "title", "total"], Query()] = "date",
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> Page[CollectionItemOut]:
    filters = CollectionFilters(
        q=q, country_id=country_id, series_id=series_id, sort=sort, order=order
    )
    items, total = await CollectionService(session, user, locale).list_collection(
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
