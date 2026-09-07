"""Data access for the user's collection and its linked expenses.

Every query is scoped to the owner passed to the constructor — the isolation
rule lives here, not in the routes (docs/07-auth.md).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, exists, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import CatalogItem, CoinSeries, CollectionItem, Country, Denomination, Expense
from app.models.enums import CollectionGroup, ExpenseCategory, MetalKind
from app.repositories.catalog import catalog_search_condition, latest_price_uah_for
from app.repositories.localization import localized


@dataclass
class CollectionFilters:
    q: str | None = None
    country_id: int | None = None
    series_id: int | None = None
    year: int | None = None
    year_from: int | None = None
    year_to: int | None = None
    denomination_id: int | None = None
    group: CollectionGroup | None = None
    metal_kind: MetalKind | None = None
    grade: str | None = None
    sort: str = "date"  # date | title | total
    order: str = "desc"


@dataclass
class CollectionPositionRow:
    """One catalog item, aggregated over every purchase the owner made of it."""

    catalog_item: CatalogItem
    country: str
    series_name: str | None
    denomination: Denomination | None
    total_quantity: int
    total_spend_uah: Decimal
    market_value_uah: Decimal | None
    last_acquisition_date: date | None
    grades: list[str]


@dataclass
class CollectionRow:
    instance: CollectionItem
    catalog_item: CatalogItem
    country: str
    series_name: str | None
    denomination: Denomination | None
    market_price_uah: Decimal | None = None


def _total_uah() -> ColumnElement[Any]:
    return (
        func.coalesce(CollectionItem.purchase_price, 0)
        * func.coalesce(CollectionItem.purchase_rate_uah, 1)
        * CollectionItem.quantity
    )


class CollectionRepository:
    def __init__(
        self, session: AsyncSession, *, owner_id: int, locale: str = DEFAULT_LOCALE
    ) -> None:
        self._session = session
        self._owner_id = owner_id
        self._locale = locale

    # --------------------------------------------------------- positions

    def _owns_catalog_item(self, *, grade: str | None = None) -> ColumnElement[bool]:
        conditions: list[ColumnElement[bool]] = [
            CollectionItem.catalog_item_id == CatalogItem.id,
            CollectionItem.owner_id == self._owner_id,
        ]
        if grade is not None:
            conditions.append(CollectionItem.grade == grade)
        return exists(select(CollectionItem.id).where(*conditions))

    def _position_filter_conditions(self, filters: CollectionFilters) -> list[ColumnElement[bool]]:
        # A position is a catalog item the owner holds at least one purchase
        # of; the grade filter narrows that to items with a matching purchase
        # but never drops the position's other purchases from its aggregates
        # (docs/03-api-contract.md: grade filtering shows the whole position).
        conditions: list[ColumnElement[bool]] = [self._owns_catalog_item()]
        if filters.grade is not None:
            conditions.append(self._owns_catalog_item(grade=filters.grade))
        if filters.country_id is not None:
            conditions.append(CatalogItem.country_id == filters.country_id)
        if filters.series_id is not None:
            conditions.append(CatalogItem.series_id == filters.series_id)
        if filters.year is not None:
            conditions.append(CatalogItem.issue_year == filters.year)
        if filters.year_from is not None:
            conditions.append(CatalogItem.issue_year >= filters.year_from)
        if filters.year_to is not None:
            conditions.append(CatalogItem.issue_year <= filters.year_to)
        if filters.denomination_id is not None:
            conditions.append(CatalogItem.denomination_id == filters.denomination_id)
        if filters.group is not None:
            conditions.append(CatalogItem.collection_group == filters.group)
        if filters.metal_kind is not None:
            conditions.append(CatalogItem.metal_kind == filters.metal_kind)
        if filters.q:
            conditions.append(catalog_search_condition(filters.q))
        return conditions

    def _position_lateral(self) -> Any:
        """Purchase aggregates for one catalog item, correlated to it.

        Always sums every purchase of the item, regardless of the grade
        filter — a matching purchase pulls the whole position into the
        listing, not just itself.
        """
        return (
            select(
                func.coalesce(func.sum(CollectionItem.quantity), 0).label("total_quantity"),
                func.coalesce(func.sum(_total_uah()), 0).label("total_spend_uah"),
                func.max(CollectionItem.acquisition_date).label("last_acquisition_date"),
                func.array_agg(func.distinct(CollectionItem.grade))
                .filter(CollectionItem.grade.is_not(None))
                .label("grades"),
            )
            .where(
                CollectionItem.catalog_item_id == CatalogItem.id,
                CollectionItem.owner_id == self._owner_id,
            )
            .lateral("position_agg")
        )

    async def list_positions(
        self, filters: CollectionFilters, *, limit: int, offset: int
    ) -> tuple[list[CollectionPositionRow], int]:
        conditions = self._position_filter_conditions(filters)

        count_query = (
            select(func.count(CatalogItem.id))
            .join(Country, Country.id == CatalogItem.country_id)
            .where(*conditions)
        )
        total = (await self._session.execute(count_query)).scalar_one()

        agg = self._position_lateral()
        descending = filters.order == "desc"
        sort_columns: dict[str, Any] = {
            "date": agg.c.last_acquisition_date,
            "title": localized(
                self._locale,
                uk=CatalogItem.title_uk,
                en=CatalogItem.title_en,
                original=CatalogItem.title_original,
            ),
            "total": agg.c.total_spend_uah,
        }
        column = sort_columns.get(filters.sort, sort_columns["date"])
        ordering = column.desc().nulls_last() if descending else column.asc().nulls_last()

        query = (
            select(
                CatalogItem,
                localized(
                    self._locale,
                    uk=Country.name_uk,
                    en=Country.name_en,
                    original=Country.name_original,
                ).label("country"),
                localized(
                    self._locale,
                    uk=CoinSeries.name_uk,
                    en=CoinSeries.name_en,
                    original=CoinSeries.name_original,
                ).label("series_name"),
                Denomination,
                agg.c.total_quantity,
                agg.c.total_spend_uah,
                agg.c.last_acquisition_date,
                agg.c.grades,
                latest_price_uah_for(CatalogItem.id, self._owner_id).label("market_price_uah"),
            )
            .join(Country, Country.id == CatalogItem.country_id)
            .outerjoin(CoinSeries, CoinSeries.id == CatalogItem.series_id)
            .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
            .join(agg, true())
            .where(*conditions)
            .order_by(ordering, CatalogItem.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        return [self._to_position_row(row) for row in result], total

    @staticmethod
    def _to_position_row(row: Any) -> CollectionPositionRow:
        market_price = row.market_price_uah
        total_quantity = int(row.total_quantity or 0)
        return CollectionPositionRow(
            catalog_item=row.CatalogItem,
            country=row.country,
            series_name=row.series_name,
            denomination=row.Denomination,
            total_quantity=total_quantity,
            total_spend_uah=Decimal(row.total_spend_uah or 0),
            market_value_uah=(None if market_price is None else market_price * total_quantity),
            last_acquisition_date=row.last_acquisition_date,
            grades=sorted(set(row.grades or [])),
        )

    # ------------------------------------------------------- single items

    def _row_query(self) -> Any:
        return (
            select(
                CollectionItem,
                CatalogItem,
                localized(
                    self._locale,
                    uk=Country.name_uk,
                    en=Country.name_en,
                    original=Country.name_original,
                ).label("country"),
                localized(
                    self._locale,
                    uk=CoinSeries.name_uk,
                    en=CoinSeries.name_en,
                    original=CoinSeries.name_original,
                ).label("series_name"),
                Denomination,
                latest_price_uah_for(CatalogItem.id, self._owner_id).label("market_price_uah"),
            )
            .join(CatalogItem, CatalogItem.id == CollectionItem.catalog_item_id)
            .join(Country, Country.id == CatalogItem.country_id)
            .outerjoin(CoinSeries, CoinSeries.id == CatalogItem.series_id)
            .outerjoin(Denomination, Denomination.id == CatalogItem.denomination_id)
        )

    @staticmethod
    def _to_row(row: Any) -> CollectionRow:
        return CollectionRow(
            instance=row.CollectionItem,
            catalog_item=row.CatalogItem,
            country=row.country,
            series_name=row.series_name,
            denomination=row.Denomination,
            market_price_uah=row.market_price_uah,
        )

    async def get_row(self, item_id: int) -> CollectionRow | None:
        query = self._row_query().where(
            CollectionItem.id == item_id, CollectionItem.owner_id == self._owner_id
        )
        row = (await self._session.execute(query)).first()
        return None if row is None else self._to_row(row)

    async def list_for_item(self, catalog_item_id: int) -> Sequence[CollectionItem]:
        result = await self._session.execute(
            select(CollectionItem)
            .where(
                CollectionItem.owner_id == self._owner_id,
                CollectionItem.catalog_item_id == catalog_item_id,
            )
            .order_by(CollectionItem.acquisition_date.desc().nulls_last(), CollectionItem.id)
        )
        return result.scalars().all()

    async def get(self, item_id: int) -> CollectionItem | None:
        result = await self._session.execute(
            select(CollectionItem).where(
                CollectionItem.id == item_id,
                CollectionItem.owner_id == self._owner_id,
            )
        )
        return result.scalar_one_or_none()

    async def add(self, item: CollectionItem) -> CollectionItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def delete(self, item: CollectionItem) -> None:
        await self._session.delete(item)
        await self._session.flush()

    async def purchase_expense_for(self, collection_item_id: int) -> Expense | None:
        """The coin_purchase expense created together with the instance."""
        result = await self._session.execute(
            select(Expense).where(
                Expense.owner_id == self._owner_id,
                Expense.collection_item_id == collection_item_id,
                Expense.category == ExpenseCategory.COIN_PURCHASE,
            )
        )
        return result.scalars().first()
