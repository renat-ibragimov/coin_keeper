"""Completeness endpoints: completeness grouped by an arbitrary catalog field
(docs/03-api-contract.md)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, DbSession, Pagination, RequestLocale
from app.api.errors import ProblemError
from app.schemas.catalog import CatalogListItem
from app.schemas.common import Page
from app.schemas.completeness import CompletenessGroupBy, CompletenessGroupOut
from app.services.completeness import (
    CompletenessInvalidRequestError,
    CompletenessNotFoundError,
    CompletenessService,
)

router = APIRouter(prefix="/completeness", tags=["completeness"])


def _resolve_group(value: int | None, unassigned: bool) -> tuple[int | None, bool]:
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
    value: Annotated[int | None, Query()] = None,
    unassigned: Annotated[bool, Query()] = False,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> CompletenessGroupOut:
    value, unassigned = _resolve_group(value, unassigned)
    try:
        return await CompletenessService(session, user, locale).group(
            group_by, value=value, unassigned=unassigned, country_id=country_id
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
    value: Annotated[int | None, Query()] = None,
    unassigned: Annotated[bool, Query()] = False,
    country_id: Annotated[int | None, Query(alias="countryId")] = None,
) -> Page[CatalogListItem]:
    value, unassigned = _resolve_group(value, unassigned)
    try:
        items, total = await CompletenessService(session, user, locale).items(
            group_by,
            value=value,
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
