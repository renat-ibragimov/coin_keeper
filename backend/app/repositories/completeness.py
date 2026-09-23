"""Completeness by an arbitrary catalog field.

Generalizes SeriesRepository.summary()/list_progress() (a per-series loop of
three queries) into three GROUP BY queries over any of the supported
dimensions, so N groups cost the same three queries regardless of how many
there are — unlike the series screen's per-series loop.

Completeness: both sides of the fraction over active items visible to the
user (docs/04-business-rules.md, rule 5). Money counts an instance of an
archived item too (rule 10) — the same split `SeriesRepository.summary()`
makes between the "active" and the "any state" predicate sets.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE, LOCALE_UK, pick_name
from app.models import (
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Denomination,
    EdgeType,
    Material,
    QualityType,
)
from app.reference_data.denominations import render_label
from app.repositories.catalog import has_visible_price, latest_price_uah_for
from app.repositories.series import SeriesRepository

CompletenessGroupBy = Literal[
    "series", "year", "denomination", "material", "edge", "quality", "metal"
]

# InstrumentedAttribute isn't accepted as ColumnElement[int | None] by mypy in
# a dict literal even though it is one at runtime -- Any keeps the mapping
# honest about what GROUP BY/label()/== actually need from it.
GROUP_BY_COLUMNS: dict[CompletenessGroupBy, Any] = {
    "series": CatalogItem.series_id,
    "year": CatalogItem.issue_year,
    "denomination": CatalogItem.denomination_id,
    "material": CatalogItem.composition_id,
    "edge": CatalogItem.edge_type_id,
    "quality": CatalogItem.quality_type_id,
    # A StrEnum column, not an int FK -- the only dimension whose group
    # value is a string ("precious"/"base"/"unknown"), never NULL.
    "metal": CatalogItem.metal_kind,
}


@dataclass
class CompletenessGroupData:
    value: int | str | None
    total: int
    owned: int
    purchase_total_uah: Decimal
    current_value_uah: Decimal
    unpriced_missing: int


@dataclass
class CompletenessLabel:
    label: str
    country_id: int | None = None
    description: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    sort_order: int | None = None


class CompletenessRepository:
    def __init__(
        self, session: AsyncSession, *, user_id: int, locale: str = DEFAULT_LOCALE
    ) -> None:
        self._session = session
        self._user_id = user_id
        self._locale = locale

    def _visible(self) -> ColumnElement[bool]:
        return or_(CatalogItem.created_by.is_(None), CatalogItem.created_by == self._user_id)

    # -------------------------------------------------------------- summary

    async def aggregate(
        self, group_by: CompletenessGroupBy, *, country_id: int | None = None
    ) -> list[CompletenessGroupData]:
        column = GROUP_BY_COLUMNS[group_by]

        active_conditions: list[ColumnElement[bool]] = [
            self._visible(),
            not_(CatalogItem.is_archived),
        ]
        if country_id is not None:
            active_conditions.append(CatalogItem.country_id == country_id)

        counts_query = (
            select(
                column.label("value"),
                func.count(CatalogItem.id.distinct()),
                func.count(CollectionItem.catalog_item_id.distinct()),
            )
            .select_from(CatalogItem)
            .outerjoin(
                CollectionItem,
                (CollectionItem.catalog_item_id == CatalogItem.id)
                & (CollectionItem.owner_id == self._user_id),
            )
            .where(*active_conditions)
            .group_by(column)
        )
        data: dict[int | str | None, CompletenessGroupData] = {}
        for count_row in (await self._session.execute(counts_query)).all():
            data[count_row.value] = CompletenessGroupData(
                value=count_row.value,
                total=int(count_row[1] or 0),
                owned=int(count_row[2] or 0),
                purchase_total_uah=Decimal(0),
                current_value_uah=Decimal(0),
                unpriced_missing=0,
            )

        # The money side goes over the user's instances of any state — an
        # instance of an archived item still counts (docs/04, rule 10).
        any_state_conditions: list[ColumnElement[bool]] = [self._visible()]
        if country_id is not None:
            any_state_conditions.append(CatalogItem.country_id == country_id)
        money_query = (
            select(
                column.label("value"),
                func.coalesce(
                    func.sum(
                        CollectionItem.quantity
                        * func.coalesce(CollectionItem.purchase_price, 0)
                        * func.coalesce(CollectionItem.purchase_rate_uah, 1)
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        CollectionItem.quantity
                        * func.coalesce(
                            latest_price_uah_for(CollectionItem.catalog_item_id, self._user_id), 0
                        )
                    ),
                    0,
                ),
            )
            .select_from(CollectionItem)
            .join(CatalogItem, CatalogItem.id == CollectionItem.catalog_item_id)
            .where(CollectionItem.owner_id == self._user_id, *any_state_conditions)
            .group_by(column)
        )
        for money_row in (await self._session.execute(money_query)).all():
            entry = data.get(money_row.value)
            if entry is None:
                entry = CompletenessGroupData(
                    value=money_row.value,
                    total=0,
                    owned=0,
                    purchase_total_uah=Decimal(0),
                    current_value_uah=Decimal(0),
                    unpriced_missing=0,
                )
                data[money_row.value] = entry
            entry.purchase_total_uah = Decimal(money_row[1])
            entry.current_value_uah = Decimal(money_row[2])

        unpriced_query = (
            select(column.label("value"), func.count(CatalogItem.id))
            .where(
                *active_conditions,
                ~select(CollectionItem.id)
                .where(
                    CollectionItem.catalog_item_id == CatalogItem.id,
                    CollectionItem.owner_id == self._user_id,
                )
                .exists(),
                not_(has_visible_price(CatalogItem.id, self._user_id)),
            )
            .group_by(column)
        )
        for unpriced_row in (await self._session.execute(unpriced_query)).all():
            entry = data.get(unpriced_row.value)
            if entry is not None:
                entry.unpriced_missing = int(unpriced_row[1] or 0)

        if group_by == "series":
            # A series with no counted item at all is still listed as a 0/0
            # row (the series screen's own behaviour, unlike year/denomination/
            # material which have no meaningful "every possible value").
            series_repo = SeriesRepository(
                self._session, user_id=self._user_id, locale=self._locale
            )
            for series in await series_repo.list_series(country_id):
                if series.id not in data:
                    data[series.id] = CompletenessGroupData(
                        value=series.id,
                        total=0,
                        owned=0,
                        purchase_total_uah=Decimal(0),
                        current_value_uah=Decimal(0),
                        unpriced_missing=0,
                    )

        return list(data.values())

    async def one(
        self,
        group_by: CompletenessGroupBy,
        *,
        value: int | str | None,
        unassigned: bool,
        country_id: int | None = None,
    ) -> CompletenessGroupData:
        column = GROUP_BY_COLUMNS[group_by]
        predicate = column.is_(None) if unassigned else column == value

        active_conditions: list[ColumnElement[bool]] = [
            self._visible(),
            not_(CatalogItem.is_archived),
            predicate,
        ]
        if country_id is not None:
            active_conditions.append(CatalogItem.country_id == country_id)

        counts = (
            await self._session.execute(
                select(
                    func.count(CatalogItem.id.distinct()),
                    func.count(CollectionItem.catalog_item_id.distinct()),
                )
                .select_from(CatalogItem)
                .outerjoin(
                    CollectionItem,
                    (CollectionItem.catalog_item_id == CatalogItem.id)
                    & (CollectionItem.owner_id == self._user_id),
                )
                .where(*active_conditions)
            )
        ).one()
        total, owned = int(counts[0] or 0), int(counts[1] or 0)

        any_state_conditions: list[ColumnElement[bool]] = [self._visible(), predicate]
        if country_id is not None:
            any_state_conditions.append(CatalogItem.country_id == country_id)
        money = (
            await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            CollectionItem.quantity
                            * func.coalesce(CollectionItem.purchase_price, 0)
                            * func.coalesce(CollectionItem.purchase_rate_uah, 1)
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(
                            CollectionItem.quantity
                            * func.coalesce(
                                latest_price_uah_for(CollectionItem.catalog_item_id, self._user_id),
                                0,
                            )
                        ),
                        0,
                    ),
                )
                .select_from(CollectionItem)
                .join(CatalogItem, CatalogItem.id == CollectionItem.catalog_item_id)
                .where(CollectionItem.owner_id == self._user_id, *any_state_conditions)
            )
        ).one()
        purchase_total, current_value = Decimal(money[0]), Decimal(money[1])

        unpriced_missing = (
            await self._session.execute(
                select(func.count(CatalogItem.id)).where(
                    *active_conditions,
                    ~select(CollectionItem.id)
                    .where(
                        CollectionItem.catalog_item_id == CatalogItem.id,
                        CollectionItem.owner_id == self._user_id,
                    )
                    .exists(),
                    not_(has_visible_price(CatalogItem.id, self._user_id)),
                )
            )
        ).scalar_one()

        return CompletenessGroupData(
            value=None if unassigned else value,
            total=total,
            owned=owned,
            purchase_total_uah=purchase_total,
            current_value_uah=current_value,
            unpriced_missing=int(unpriced_missing),
        )

    # --------------------------------------------------------------- labels

    async def labels(
        self, group_by: CompletenessGroupBy, values: list[int | str | None]
    ) -> dict[int | str, CompletenessLabel]:
        """Human labels and metadata for the given non-null group values."""
        if group_by == "metal":
            # A fixed, non-localized StrEnum, not a database dictionary -- the
            # frontend already has its own translations for these codes
            # (catalog.metalPrecious/metalBase), so the backend has nothing
            # to add here.
            return {}
        # Every remaining dimension is an int FK/year -- `metal` (the one
        # string-valued dimension) already returned above.
        ids = sorted({int(value) for value in values if value is not None})
        if not ids:
            return {}
        if group_by == "series":
            series_result = await self._session.execute(
                select(CoinSeries).where(CoinSeries.id.in_(ids))
            )
            return {
                series.id: CompletenessLabel(
                    label=pick_name(
                        self._locale,
                        uk=series.name_uk,
                        en=series.name_en,
                        original=series.name_original,
                    ),
                    country_id=series.country_id,
                    description=series.description,
                    start_year=series.start_year,
                    end_year=series.end_year,
                )
                for series in series_result.scalars()
            }
        if group_by == "denomination":
            denomination_result = await self._session.execute(
                select(Denomination).where(Denomination.id.in_(ids))
            )
            return {
                denomination.id: CompletenessLabel(
                    label=render_label(denomination.value, denomination.unit, self._locale),
                    country_id=denomination.country_id,
                    sort_order=denomination.sort_order,
                )
                for denomination in denomination_result.scalars()
            }
        if group_by == "material":
            material_result = await self._session.execute(
                select(Material).where(Material.id.in_(ids))
            )
            return {
                material.id: CompletenessLabel(
                    label=material.name_uk if self._locale == LOCALE_UK else material.name_en
                )
                for material in material_result.scalars()
            }
        if group_by == "edge":
            edge_result = await self._session.execute(select(EdgeType).where(EdgeType.id.in_(ids)))
            return {
                edge.id: CompletenessLabel(
                    label=edge.name_uk if self._locale == LOCALE_UK else edge.name_en
                )
                for edge in edge_result.scalars()
            }
        if group_by == "quality":
            quality_result = await self._session.execute(
                select(QualityType).where(QualityType.id.in_(ids))
            )
            return {
                quality.id: CompletenessLabel(
                    label=quality.name_uk if self._locale == LOCALE_UK else quality.name_en
                )
                for quality in quality_result.scalars()
            }
        # "year": the value itself is the label, no dictionary lookup needed.
        return {year: CompletenessLabel(label=str(year), sort_order=year) for year in ids}
