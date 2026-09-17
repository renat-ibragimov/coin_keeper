"""Catalog endpoints (docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import (
    ClientIp,
    CurrentUser,
    DbSession,
    OptionalCurrentUser,
    Pagination,
    RequestLocale,
)
from app.api.errors import ProblemError
from app.api.public_rate_limit import enforce_public_read
from app.core import rate_limit
from app.models.enums import CollectionGroup
from app.repositories.catalog import CatalogFilters
from app.schemas.catalog import (
    ArchiveRequest,
    ArchiveStateOut,
    CatalogCard,
    CatalogCollectionItemOut,
    CatalogItemCreate,
    CatalogItemUpdate,
    CatalogListItem,
    CoinMaterial,
    PriceHistoryItem,
    PublicCatalogCard,
    PublicCatalogListItem,
)
from app.schemas.common import Page
from app.services.catalog import (
    ArchiveStateError,
    BadReferenceError,
    CatalogService,
    ItemHasReferencesError,
    ItemNotFoundError,
    NotApplicableToPersonalError,
    PublicCatalogService,
    SharedRecordForbiddenError,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])

SortField = Literal[
    "title", "country", "series", "year", "denomination", "material", "owned", "purchase", "price"
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


@router.get("", response_model=None)
async def list_catalog(
    session: DbSession,
    user: OptionalCurrentUser,
    locale: RequestLocale,
    pagination: Pagination,
    ip: ClientIp,
    q: Annotated[str | None, Query(max_length=200)] = None,
    country_id: Annotated[list[int] | None, Query(alias="countryId")] = None,
    series_id: Annotated[list[int] | None, Query(alias="seriesId")] = None,
    year: Annotated[int | None, Query()] = None,
    year_from: Annotated[int | None, Query(alias="yearFrom")] = None,
    year_to: Annotated[int | None, Query(alias="yearTo")] = None,
    denomination_id: Annotated[list[int] | None, Query(alias="denominationId")] = None,
    group: Annotated[list[CollectionGroup] | None, Query()] = None,
    material_id: Annotated[list[int] | None, Query(alias="materialId")] = None,
    owned: Annotated[bool | None, Query()] = None,
    scope: Annotated[Literal["all", "shared", "own"], Query()] = "all",
    archived: Annotated[bool, Query()] = False,
    sort: Annotated[SortField, Query()] = "title",
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
) -> Page[CatalogListItem] | Page[PublicCatalogListItem]:
    if user is None and (
        owned is not None
        or scope not in ("all", "shared")
        or archived
        or sort in ("owned", "purchase", "price")
    ):
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "private-catalog-filter",
            "Invalid filter",
            "This filter requires an account.",
        )
    await enforce_public_read(
        rate_limit.PUBLIC_SEARCH if q else rate_limit.PUBLIC_CATALOG, user, ip
    )
    filters = CatalogFilters(
        q=q,
        country_ids=country_id,
        series_ids=series_id,
        year=year,
        year_from=year_from,
        year_to=year_to,
        denomination_ids=denomination_id,
        groups=group,
        material_ids=material_id,
        owned=owned,
        scope=scope,
        archived=archived,
        sort=sort,
        order=order,
    )
    service = (
        CatalogService(session, user, locale) if user else PublicCatalogService(session, locale)
    )
    items, total = await service.list_catalog(
        filters, limit=pagination.page_size, offset=pagination.offset
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


# Must stay registered before /{item_id} — otherwise FastAPI tries to parse
# "lookup" as item_id and 422s instead of matching this route.
@router.get("/lookup")
async def lookup_catalog(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[CatalogListItem]:
    """The "Додати" form's typeahead: a handful of coins matching the text.

    The same rows `GET /catalog` returns and the same layer visibility —
    shared records plus the user's own personal items, active ones only —
    with the storefront rule switched off entirely (docs/04-business-rules.md,
    §13). The field sits under a country the collector just chose out of every
    issuer there has ever been, so a coin of a country the catalogue project
    has not confirmed still has to be findable by name; not finding it means a
    personal duplicate of a coin the catalog already holds.
    """
    filters = CatalogFilters(
        q=q,
        country_ids=[country_id] if country_id is not None else None,
        sort="year",
        order="desc",
    )
    items, _ = await CatalogService(session, user, locale).list_catalog(
        filters, limit=limit, offset=0, apply_storefront=False
    )
    return items


# Must stay registered before /{item_id} — otherwise FastAPI tries to parse
# "materials" as item_id and 422s instead of matching this route.
@router.get("/materials")
async def list_catalog_materials(
    session: DbSession,
    user: OptionalCurrentUser,
    locale: RequestLocale,
    ip: ClientIp,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[CoinMaterial]:
    """Materials the material filter offers on `GET /catalog` — only what a
    `catalog_confirmed` item actually uses (docs/04-business-rules.md, §14)."""
    await enforce_public_read(rate_limit.PUBLIC_REFERENCE, user, ip)
    return (
        await CatalogService(session, user, locale).list_confirmed_materials(country_id)
        if user
        else await PublicCatalogService(session, locale).list_confirmed_materials(country_id)
    )


@router.get("/{item_id}", response_model=None)
async def get_card(
    session: DbSession, user: OptionalCurrentUser, locale: RequestLocale, ip: ClientIp, item_id: int
) -> CatalogCard | PublicCatalogCard:
    await enforce_public_read(rate_limit.PUBLIC_CATALOG, user, ip)
    try:
        service = (
            CatalogService(session, user, locale) if user else PublicCatalogService(session, locale)
        )
        return await service.get_card(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc


@router.get("/{item_id}/prices")
async def list_prices(
    session: DbSession, user: CurrentUser, locale: RequestLocale, item_id: int
) -> list[PriceHistoryItem]:
    try:
        return await CatalogService(session, user, locale).list_prices(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc


@router.get("/{item_id}/collection-items")
async def list_own_instances(
    session: DbSession, user: CurrentUser, locale: RequestLocale, item_id: int
) -> list[CatalogCollectionItemOut]:
    try:
        return await CatalogService(session, user, locale).list_own_instances(item_id)
    except ItemNotFoundError as exc:
        raise _not_found() from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    session: DbSession, user: CurrentUser, locale: RequestLocale, payload: CatalogItemCreate
) -> CatalogCard:
    try:
        return await CatalogService(session, user, locale).create_item(payload)
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
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    item_id: int,
    payload: CatalogItemUpdate,
) -> CatalogCard:
    try:
        return await CatalogService(session, user, locale).update_item(item_id, payload)
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
async def delete_item(
    session: DbSession, user: CurrentUser, locale: RequestLocale, item_id: int
) -> None:
    try:
        await CatalogService(session, user, locale).delete_item(item_id)
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
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    item_id: int,
    payload: ArchiveRequest,
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
        return await CatalogService(session, user, locale).archive_item(item_id, reason)
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
async def unarchive_item(
    session: DbSession, user: CurrentUser, locale: RequestLocale, item_id: int
) -> ArchiveStateOut:
    try:
        return await CatalogService(session, user, locale).unarchive_item(item_id)
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
