"""Completeness endpoints: completeness grouped by an arbitrary catalog field
(docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination, RequestLocale
from app.api.errors import ProblemError
from app.models.enums import MetalKind
from app.schemas.catalog import CatalogListItem
from app.schemas.common import Page
from app.schemas.completeness import CompletenessGroupBy, CompletenessGroupOut
from app.services.completeness import (
    CompletenessInvalidRequestError,
    CompletenessNotFoundError,
    CompletenessService,
)

router = APIRouter(prefix="/completeness", tags=["completeness"])

# Every dimension but "metal" addresses a group by an integer id/year;
# "metal" addresses it by the MetalKind code itself ("precious"/"base"/
# "unknown"). `value` therefore arrives as a raw query string and is parsed
# here rather than left to FastAPI's `int | str` union resolution, which
# Pydantic v2's smart-union mode does not resolve predictably for a plain
# numeric string (it can keep "5" as the string "5" instead of coercing it).
_STRING_VALUED: frozenset[CompletenessGroupBy] = frozenset({"metal"})


def _resolve_group(
    group_by: CompletenessGroupBy, value: str | None, unassigned: bool
) -> tuple[int | str | None, bool]:
    """Exactly one of `value`/`unassigned` identifies a group."""
    if unassigned and value is not None:
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "completeness-ambiguous-group",
            "Request rejected",
            "Pass either value or unassigned=true, not both.",
        )
    if not unassigned and value is None:
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "completeness-missing-group",
            "Request rejected",
            "One of value or unassigned=true is required.",
        )
    if not unassigned and value is not None and group_by not in _STRING_VALUED:
        try:
            return int(value), unassigned
        except ValueError as exc:
            raise ProblemError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "completeness-invalid-value",
                "Request rejected",
                "value must be an integer for this dimension.",
            ) from exc
    if (
        not unassigned
        and value is not None
        and group_by == "metal"
        and value not in {kind.value for kind in MetalKind}
    ):
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "completeness-invalid-value",
            "Request rejected",
            "value must be one of the metal kind codes for this dimension.",
        )
    return value, unassigned


@router.get("/summary")
async def completeness_summary(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    group_by: Annotated[CompletenessGroupBy, Query(alias="groupBy")],
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> list[CompletenessGroupOut]:
    return await CompletenessService(session, user, locale).summary(group_by, country_id)


@router.get("/group")
async def completeness_group(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    group_by: Annotated[CompletenessGroupBy, Query(alias="groupBy")],
    value: Annotated[str | None, Query()] = None,
    unassigned: Annotated[bool, Query()] = False,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> CompletenessGroupOut:
    resolved_value, unassigned = _resolve_group(group_by, value, unassigned)
    try:
        return await CompletenessService(session, user, locale).group(
            group_by, value=resolved_value, unassigned=unassigned, country_id=country_id
        )
    except CompletenessInvalidRequestError as exc:
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "completeness-invalid-request",
            "Request rejected",
            exc.detail,
        ) from exc
    except CompletenessNotFoundError as exc:
        raise ProblemError(
            status.HTTP_404_NOT_FOUND,
            "completeness-group-not-found",
            "Not found",
            "The group has no items.",
        ) from exc


@router.get("/items")
async def completeness_items(
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    pagination: Pagination,
    group_by: Annotated[CompletenessGroupBy, Query(alias="groupBy")],
    value: Annotated[str | None, Query()] = None,
    unassigned: Annotated[bool, Query()] = False,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> Page[CatalogListItem]:
    resolved_value, unassigned = _resolve_group(group_by, value, unassigned)
    try:
        items, total = await CompletenessService(session, user, locale).items(
            group_by,
            value=resolved_value,
            unassigned=unassigned,
            country_id=country_id,
            limit=pagination.page_size,
            offset=pagination.offset,
        )
    except CompletenessInvalidRequestError as exc:
        raise ProblemError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "completeness-invalid-request",
            "Request rejected",
            exc.detail,
        ) from exc
    return Page(items=items, total=total, page=pagination.page, page_size=pagination.page_size)
