"""Collection endpoints (docs/api.md)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Query, Request, status

from app.api.deps import (
    CollectionPhotoServiceDep,
    CurrentUser,
    DbSession,
    Pagination,
    RequestLocale,
)
from app.api.errors import ProblemError
from app.core.images import MAX_SOURCE_BYTES, ImageRejectedError
from app.models.enums import CollectionGroup, MediaRole, MetalKind
from app.repositories.collection import CollectionFilters
from app.schemas.catalog import CoinMaterial
from app.schemas.collection import (
    CollectionItemCreate,
    CollectionItemOut,
    CollectionItemPhotosOut,
    CollectionItemUpdate,
    CollectionPositionOut,
    CollectionSummaryOut,
    StorageLocationCreate,
    StorageLocationOut,
)
from app.schemas.common import Page
from app.schemas.reference import CountryOut, DenominationOut
from app.schemas.series import SeriesOut
from app.services.catalog import BadReferenceError, translate_title_in_background
from app.services.collection import (
    CatalogItemNotFoundError,
    CollectionItemNotFoundError,
    CollectionService,
    MissingRateError,
    UnknownCurrencyError,
)
from app.services.collection_photos import CollectionItemNotFoundError as PhotoItemNotFoundError
from app.services.media_urls import image_out
from app.services.storage_locations import (
    StorageLocationForbiddenError,
    StorageLocationNotFoundError,
)

PhotoRole = Literal["obverse", "reverse"]

router = APIRouter(prefix="/collection", tags=["collection"])


def _not_found(what: str) -> ProblemError:
    return ProblemError(status.HTTP_404_NOT_FOUND, f"{what}-not-found", "Not found", "Not found.")


def _unprocessable(problem_type: str, detail: str) -> ProblemError:
    return ProblemError(
        status.HTTP_422_UNPROCESSABLE_CONTENT, problem_type, "Request rejected", detail
    )


def _invalid_image_problem() -> ProblemError:
    return ProblemError(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "invalid-image",
        "Image rejected",
        "Upload a JPEG, PNG or WebP image up to 12 MB and no wider than 4000 px.",
    )


def _forbidden(problem_type: str, detail: str) -> ProblemError:
    return ProblemError(status.HTTP_403_FORBIDDEN, problem_type, "Forbidden", detail)


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
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    denomination_id: Annotated[list[int] | None, Query(alias="denominationId")] = None,
    group: Annotated[list[CollectionGroup] | None, Query()] = None,
    material_id: Annotated[list[int] | None, Query(alias="materialId")] = None,
    metal_kind: Annotated[list[MetalKind] | None, Query(alias="metalKind")] = None,
    grade: Annotated[str | None, Query(max_length=50)] = None,
    sort: Annotated[
        Literal[
            "release",
            "date",
            "title",
            "country",
            "series",
            "quantity",
            "total",
            "valuation",
            "grade",
        ],
        Query(),
    ] = "release",
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> Page[CollectionPositionOut]:
    filters = CollectionFilters(
        q=q,
        country_ids=country_id,
        series_ids=series_id,
        year=year,
        year_from=year_from,
        year_to=year_to,
        date_from=date_from,
        date_to=date_to,
        denomination_ids=denomination_id,
        groups=group,
        material_ids=material_id,
        metal_kinds=metal_kind,
        grade=grade,
        sort=sort,
        order=order,
    )
    items, total = await CollectionService(session, user, locale).list_positions(
        filters, limit=pagination.page_size, offset=pagination.offset
    )
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)


# Must stay registered before /{item_id} — otherwise FastAPI tries to parse
# "summary" as item_id and 404s instead of matching this route.
@router.get("/summary")
async def collection_summary(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    q: Annotated[str | None, Query(max_length=200)] = None,
    country_id: Annotated[list[int] | None, Query(alias="countryId")] = None,
    series_id: Annotated[list[int] | None, Query(alias="seriesId")] = None,
    year: Annotated[int | None, Query()] = None,
    year_from: Annotated[int | None, Query(alias="yearFrom")] = None,
    year_to: Annotated[int | None, Query(alias="yearTo")] = None,
    date_from: Annotated[date | None, Query(alias="dateFrom")] = None,
    date_to: Annotated[date | None, Query(alias="dateTo")] = None,
    denomination_id: Annotated[list[int] | None, Query(alias="denominationId")] = None,
    group: Annotated[list[CollectionGroup] | None, Query()] = None,
    material_id: Annotated[list[int] | None, Query(alias="materialId")] = None,
    metal_kind: Annotated[list[MetalKind] | None, Query(alias="metalKind")] = None,
    grade: Annotated[str | None, Query(max_length=50)] = None,
) -> CollectionSummaryOut:
    """The "Мої монети" KPI tiles for the filters currently applied."""
    filters = CollectionFilters(
        q=q,
        country_ids=country_id,
        series_ids=series_id,
        year=year,
        year_from=year_from,
        year_to=year_to,
        date_from=date_from,
        date_to=date_to,
        denomination_ids=denomination_id,
        groups=group,
        material_ids=material_id,
        metal_kinds=metal_kind,
        grade=grade,
    )
    return await CollectionService(session, user, locale).summary(filters)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_item(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    payload: CollectionItemCreate,
    background_tasks: BackgroundTasks,
) -> CollectionItemOut:
    try:
        created = await CollectionService(session, user, locale, background_tasks).create(payload)
    except CatalogItemNotFoundError as exc:
        raise _not_found("catalog-item") from exc
    except UnknownCurrencyError as exc:
        raise _unprocessable("unknown-currency", exc.detail) from exc
    except MissingRateError as exc:
        raise _unprocessable("exchange-rate-missing", exc.detail) from exc
    except BadReferenceError as exc:
        raise _unprocessable("invalid-reference", exc.detail) from exc
    if payload.new_catalog_item is not None:
        # The record is saved with the collector's own wording in both
        # language slots; the translated one arrives afterwards, and the
        # purchase is finished whether or not it ever does — the same
        # arrangement a new storage location gets (app/services/catalog.py).
        background_tasks.add_task(translate_title_in_background, created.catalog_item_id)
    return created


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


@router.get("/storage-locations")
async def list_storage_locations(
    session: DbSession, user: CurrentUser, locale: RequestLocale
) -> list[StorageLocationOut]:
    """The presets plus this owner's own, localized names only — a name here
    is a free-form suggestion, not an id the client has to track. `custom`
    marks the ones this owner can also delete."""
    return await CollectionService(session, user, locale).list_storage_locations()


@router.post("/storage-locations", status_code=status.HTTP_201_CREATED)
async def add_storage_location(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    payload: StorageLocationCreate,
    background_tasks: BackgroundTasks,
) -> StorageLocationOut:
    """Explicit "add to my list" from settings — the same find-or-create a
    purchase's own storageLocation field uses, so typing a name that already
    exists (a preset or one's own) just confirms it rather than duplicating."""
    return await CollectionService(session, user, locale, background_tasks).add_storage_location(
        payload.name
    )


@router.delete("/storage-locations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_storage_location(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    name: Annotated[str, Query(min_length=1, max_length=200)],
) -> None:
    try:
        await CollectionService(session, user, locale).delete_storage_location(name)
    except StorageLocationNotFoundError as exc:
        raise _not_found("storage-location") from exc
    except StorageLocationForbiddenError as exc:
        raise _forbidden(
            "storage-location-shared", "A preset is shared by every account and cannot be deleted."
        ) from exc


# NOTE: these five literal routes must stay registered before /{item_id} —
# otherwise FastAPI tries to parse "countries"/"series"/"denominations"/
# "materials"/"storage-locations" as item_id and 422s instead of matching the
# routes above.
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
    background_tasks: BackgroundTasks,
) -> CollectionItemOut:
    try:
        return await CollectionService(session, user, locale, background_tasks).update(
            item_id, payload
        )
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


@router.put("/{item_id}/photos/{role}")
async def set_photo(
    request: Request,
    user: CurrentUser,
    service: CollectionPhotoServiceDep,
    item_id: int,
    role: PhotoRole,
) -> CollectionItemPhotosOut:
    """Raw image bytes, same shape as PUT /auth/me/avatar: one file, no
    envelope, and a repeated upload of the same bytes lands on the same key.

    Always a new `media_files` row bound to this collection item, never a
    write to the catalog's own media (docs/media.md) — the
    invariant lives in CollectionPhotoService, not here.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_SOURCE_BYTES:
        raise _invalid_image_problem()

    payload = await request.body()
    if len(payload) > MAX_SOURCE_BYTES:
        raise _invalid_image_problem()

    try:
        images = await service.set_photo(
            owner=user, item_id=item_id, role=MediaRole(role), payload=payload
        )
    except PhotoItemNotFoundError as exc:
        raise _not_found("collection-item") from exc
    except ImageRejectedError as exc:
        raise _invalid_image_problem() from exc
    return CollectionItemPhotosOut(
        obverse=image_out(images.obverse), reverse=image_out(images.reverse)
    )


@router.delete("/{item_id}/photos/{role}")
async def delete_photo(
    user: CurrentUser,
    service: CollectionPhotoServiceDep,
    item_id: int,
    role: PhotoRole,
) -> CollectionItemPhotosOut:
    """200 with the fresh images, not 204: the page repaints from the answer."""
    try:
        images = await service.remove_photo(owner=user, item_id=item_id, role=MediaRole(role))
    except PhotoItemNotFoundError as exc:
        raise _not_found("collection-item") from exc
    return CollectionItemPhotosOut(
        obverse=image_out(images.obverse), reverse=image_out(images.reverse)
    )
