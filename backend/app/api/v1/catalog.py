"""Catalog endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination
from app.api.errors import ProblemError
from app.models.enums import CollectionGroup, MetalKind
from app.repositories.catalog import CatalogFilters
from app.schemas.catalog import (
    ArchiveRequest,
    ArchiveStateOut,
    CatalogCard,
    CatalogCollectionItemOut,
    CatalogItemCreate,
    CatalogItemUpdate,
    CatalogListItem,
    PriceHistoryItem,
)
from app.schemas.common import Page
from app.services.catalog import (
    ArchiveStateError,
    BadReferenceError,
    CatalogService,
    ItemHasReferencesError,
    ItemNotFoundError,
    NotApplicableToPersonalError,
    SharedRecordForbiddenError,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

SortField = Literal[
    "title", "country", "series", "year", "denomination", "owned", "purchase", "price"
]


def _not_found() -> ProblemError:
    return ProblemError(
        status.HTTP_404_NOT_FOUND,
        "catalog-item-not-found",
        "Not found",
        "The catalog item does not exist.",
    )


def _shared_forbidden() -> ProblemError:
    return ProblemError(
        status.HTTP_403_FORBIDDEN,
        "shared-catalog-read-only",
        "Forbidden",
        "The shared catalog is read-only; only an administrator can change it.",
    )


@router.get("")
async def list_catalog(
    session: DbSession,
    user: CurrentUser,
    pagination: Pagination,
    q: Annotated[str | None, Query(max_length=200)] = None,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
    series_id: Annotated[int | None, Query(alias="seriesId")] = None,
    year: Annotated[int | None, Query()] = None,
    year_from: Annotated[int | None, Query(alias="yearFrom")] = None,
    year_to: Annotated[int | None, Query(alias="yearTo")] = None,
    denomination_id: Annotated[int | None, Query(alias="denominationId")] = None,
    group: Annotated[CollectionGroup | None, Query()] = None,
    metal_kind: Annotated[MetalKind | None, Query(alias="metalKind")] = None,
    owned: Annotated[bool | None, Query()] = None,
    scope: Annotated[Literal["all", "shared", "own"], Query()] = "all",
    archived: Annotated[bool, Query()] = False,
    sort: Annotated[SortField, Query()] = "country",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> Page[CatalogListItem]:
    filters = CatalogFilters(
        q=q,
        country_id=country_id,
        series_id=series_id,
        year=year,
        year_from=year_from,
        year_to=year_to,
        denomination_id=denomination_id,
        group=group,
        metal_kind=metal_kind,
        owned=owned,
        scope=scope,
        archived=archived,
        sort=sort,
        order=order,
    )
    items, total = await CatalogService(session, user).list_catalog(
        filters, limit=pagination.page_size, offset=pagination.offset
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


@router.get("/{item_id}")
async def get_card(session: DbSession, user: CurrentUser, item_id: int) -> CatalogCard:
    try:
        return await CatalogService(session, user).get_card(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc


@router.get("/{item_id}/prices")
async def list_prices(
    session: DbSession, user: CurrentUser, item_id: int
) -> list[PriceHistoryItem]:
    try:
        return await CatalogService(session, user).list_prices(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc


@router.get("/{item_id}/collection-items")
async def list_own_instances(
    session: DbSession, user: CurrentUser, item_id: int
) -> list[CatalogCollectionItemOut]:
    try:
        return await CatalogService(session, user).list_own_instances(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    session: DbSession, user: CurrentUser, payload: CatalogItemCreate
) -> CatalogCard:
    try:
        return await CatalogService(session, user).create_item(payload)
    except SharedRecordForbiddenError as exc:
        raise ProblemError(
            status.HTTP_403_FORBIDDEN,
            "admin-required",
            "Forbidden",
            "Only an administrator can create shared catalog records.",
        ) from exc
    except BadReferenceError as exc:
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid-reference",
            "Request validation failed",
            exc.detail,
        ) from exc


@router.patch("/{item_id}")
async def update_item(
    session: DbSession, user: CurrentUser, item_id: int, payload: CatalogItemUpdate
) -> CatalogCard:
    try:
        return await CatalogService(session, user).update_item(item_id, payload)
    except ItemNotFoundError as exc:
        raise _not_found() from exc
    except SharedRecordForbiddenError as exc:
        raise _shared_forbidden() from exc
    except BadReferenceError as exc:
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid-reference",
            "Request validation failed",
            exc.detail,
        ) from exc


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(session: DbSession, user: CurrentUser, item_id: int) -> None:
    try:
        await CatalogService(session, user).delete_item(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc
    except SharedRecordForbiddenError as exc:
        raise _shared_forbidden() from exc
    except (ArchiveStateError, ItemHasReferencesError) as exc:
        raise ProblemError(
            status.HTTP_409_CONFLICT,
            "catalog-item-delete-conflict",
            "Conflict",
            exc.detail,
        ) from exc


@router.post("/{item_id}/archive")
async def archive_item(
    session: DbSession, user: CurrentUser, item_id: int, payload: ArchiveRequest
) -> ArchiveStateOut:
    reason = payload.reason.strip()
    if not reason:
        # The contract promises 400, not a validation 422, for an empty reason.
        raise ProblemError(
            status.HTTP_400_BAD_REQUEST,
            "archive-reason-required",
            "Bad request",
            "An archive reason is required.",
        )
    try:
        return await CatalogService(session, user).archive_item(item_id, reason)
    except ItemNotFoundError as exc:
        raise _not_found() from exc
    except NotApplicableToPersonalError as exc:
        raise ProblemError(
            status.HTTP_400_BAD_REQUEST,
            "archive-not-applicable",
            "Bad request",
            "Archiving applies to shared catalog records only.",
        ) from exc
    except SharedRecordForbiddenError as exc:
        raise _shared_forbidden() from exc
    except ArchiveStateError as exc:
        raise ProblemError(
            status.HTTP_409_CONFLICT, "archive-state", "Conflict", exc.detail
        ) from exc


@router.post("/{item_id}/unarchive")
async def unarchive_item(session: DbSession, user: CurrentUser, item_id: int) -> ArchiveStateOut:
    try:
        return await CatalogService(session, user).unarchive_item(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc
    except NotApplicableToPersonalError as exc:
        raise ProblemError(
            status.HTTP_400_BAD_REQUEST,
            "archive-not-applicable",
            "Bad request",
            "Archiving applies to shared catalog records only.",
        ) from exc
    except SharedRecordForbiddenError as exc:
        raise _shared_forbidden() from exc
    except ArchiveStateError as exc:
        raise ProblemError(
            status.HTTP_409_CONFLICT, "archive-state", "Conflict", exc.detail
        ) from exc
