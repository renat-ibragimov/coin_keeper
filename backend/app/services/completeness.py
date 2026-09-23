"""Completeness use cases: completeness grouped by an arbitrary catalog field
(year, denomination, material, series), generalizing the per-series summary
(docs/03-api-contract.md)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import User
from app.repositories.catalog import CatalogFilters
from app.repositories.completeness import (
    CompletenessGroupBy,
    CompletenessGroupData,
    CompletenessLabel,
    CompletenessRepository,
)
from app.schemas.catalog import CatalogListItem
from app.schemas.completeness import CompletenessGroupOut, CompletenessSummaryOut
from app.services.catalog import CatalogService


class CompletenessError(Exception):
    pass


class CompletenessNotFoundError(CompletenessError):
    """The group has no catalog item visible to this user at all: 404."""


class CompletenessInvalidRequestError(CompletenessError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def _summary_out(data: CompletenessGroupData) -> CompletenessSummaryOut:
    percent = 0.0 if data.total == 0 else round(data.owned / data.total * 100, 1)
    return CompletenessSummaryOut(
        total=data.total,
        owned=data.owned,
        missing=max(0, data.total - data.owned),
        completion_percent=percent,
        purchase_total_uah=data.purchase_total_uah,
        current_value_uah=data.current_value_uah,
        unpriced_missing=data.unpriced_missing,
    )


class CompletenessService:
    def __init__(self, session: AsyncSession, user: User, locale: str = DEFAULT_LOCALE) -> None:
        self._session = session
        self._user = user
        self._locale = locale
        self._repo = CompletenessRepository(session, user_id=user.id, locale=locale)

    @staticmethod
    def _check_unassigned(group_by: CompletenessGroupBy, unassigned: bool) -> None:
        if unassigned and group_by == "year":
            raise CompletenessInvalidRequestError(
                "The 'year' dimension is never NULL and has no unassigned bucket."
            )

    async def summary(
        self, group_by: CompletenessGroupBy, country_id: int | None
    ) -> list[CompletenessGroupOut]:
        rows = await self._repo.aggregate(group_by, country_id=country_id)
        labels = await self._repo.labels(group_by, [row.value for row in rows])
        return [
            self._group_out(
                group_by, row, labels.get(row.value) if row.value is not None else None
            )
            for row in rows
        ]

    async def group(
        self,
        group_by: CompletenessGroupBy,
        *,
        value: int | None,
        unassigned: bool,
        country_id: int | None,
    ) -> CompletenessGroupOut:
        self._check_unassigned(group_by, unassigned)
        data = await self._repo.one(
            group_by, value=value, unassigned=unassigned, country_id=country_id
        )
        if data.total == 0:
            raise CompletenessNotFoundError
        info: CompletenessLabel | None = None
        if not unassigned:
            labels = await self._repo.labels(group_by, [value])
            info = labels.get(value) if value is not None else None
        return self._group_out(group_by, data, info)

    async def items(
        self,
        group_by: CompletenessGroupBy,
        *,
        value: int | None,
        unassigned: bool,
        country_id: int | None,
        limit: int,
        offset: int,
    ) -> tuple[list[CatalogListItem], int]:
        self._check_unassigned(group_by, unassigned)
        filters = CatalogFilters(sort="year", order="asc")
        if country_id is not None:
            filters.country_ids = [country_id]
        if group_by == "series":
            filters.series_id_is_null = unassigned
            if not unassigned:
                filters.series_ids = [value] if value is not None else []
        elif group_by == "year":
            filters.year = value
        elif group_by == "denomination":
            filters.denomination_id_is_null = unassigned
            if not unassigned:
                filters.denomination_ids = [value] if value is not None else []
        elif group_by == "material":
            filters.material_id_is_null = unassigned
            if not unassigned:
                filters.material_ids = [value] if value is not None else []
        return await CatalogService(self._session, self._user, self._locale).list_catalog(
            filters, limit=limit, offset=offset, require_confirmed=False
        )

    def _group_out(
        self,
        group_by: CompletenessGroupBy,
        data: CompletenessGroupData,
        info: CompletenessLabel | None,
    ) -> CompletenessGroupOut:
        return CompletenessGroupOut(
            group_by=group_by,
            value=data.value,
            unassigned=data.value is None,
            label=info.label if info else None,
            country_id=info.country_id if info else None,
            description=info.description if info else None,
            start_year=info.start_year if info else None,
            end_year=info.end_year if info else None,
            sort_order=info.sort_order if info else None,
            summary=_summary_out(data),
        )
