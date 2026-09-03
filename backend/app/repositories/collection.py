"""Data access for the user's collection and its linked expenses.

Every query is scoped to the owner passed to the constructor — the isolation
rule lives here, not in the routes (docs/07-auth.md).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, CoinSeries, CollectionItem, Country, Denomination, Expense
from app.models.enums import ExpenseCategory
from app.repositories.catalog import catalog_search_condition, latest_price_uah_for


@dataclass
class CollectionFilters:
    q: str | None = None
    country_id: int | None = None
    series_id: int | None = None
    sort: str = "date"  # date | title | total
    order: str = "desc"


@dataclass
class CollectionRow:
    instance: CollectionItem
    catalog_item: CatalogItem
    country: str
    series_name: str | None
    denomination: str | None
    market_price_uah: Decimal | None = None


def _total_uah() -> ColumnElement[Any]:
    return (
        func.coalesce(CollectionItem.purchase_price, 0)
        * func.coalesce(CollectionItem.purchase_rate_uah, 1)
        * CollectionItem.quantity
    )


class CollectionRepository:
    def __init__(self, session: AsyncSession, *, owner_id: int) -> None:
        self._session = session
        self._owner_id = owner_id

    async def list_page(
        self, filters: CollectionFilters, *, limit: int, offset: int
    ) -> tuple[list[CollectionRow], int]:
        conditions: list[ColumnElement[bool]] = [CollectionItem.owner_id == self._owner_id]
        if filters.country_id is not None:
            conditions.append(CatalogItem.country_id == filters.country_id)
        if filters.series_id is not None:
            conditions.append(CatalogItem.series_id == filters.series_id)
        if filters.q:
            conditions.append(catalog_search_condition(filters.q))

        base_joins = (
            select(func.count(CollectionItem.id))
            .join(CatalogItem, CatalogItem.id == CollectionItem.catalog_item_id)
            .join(Country, Country.id == CatalogItem.country_id)
            .where(*conditions)
        )
        total = (await self._session.execute(base_joins)).scalar_one()

        descending = filters.order == "desc"
        sort_columns: dict[str, Any] = {
            "date": CollectionItem.acquisition_date,
            "title": func.coalesce(CatalogItem.title_uk, CatalogItem.title_original),
            "total": _total_uah(),
        }
        column = sort_columns.get(filters.sort, sort_columns["date"])
        ordering = column.desc().nulls_last() if descending else column.asc().nulls_last()

        query = (
            self._row_query()
            .where(*conditions)
            .order_by(ordering, CollectionItem.id)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(query)
        return [self._to_row(row) for row in result], total

    def _row_query(self) -> Any:
        return (
            select(
                CollectionItem,
                CatalogItem,
                Country.name_original.label("country"),
                CoinSeries.name_original.label("series_name"),
                Denomination.label_original.label("denomination"),
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
            denomination=row.denomination,
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
