"""Data access for the user's collection and its linked expenses.

Every query is scoped to the owner passed to the constructor — the isolation
rule lives here, not in the routes (docs/07-auth.md).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectionItem, Expense
from app.models.enums import ExpenseCategory


class CollectionRepository:
    def __init__(self, session: AsyncSession, *, owner_id: int) -> None:
        self._session = session
        self._owner_id = owner_id

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
