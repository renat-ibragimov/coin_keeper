"""Owner-scoped expense data access (docs/07-auth.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Expense
from app.models.enums import ExpenseCategory


@dataclass
class ExpenseFilters:
    category: ExpenseCategory | None = None
    date_from: date | None = None
    date_to: date | None = None


@dataclass
class CategoryTotal:
    category: ExpenseCategory
    count: int
    total_uah: Decimal


def _amount_uah() -> ColumnElement[Decimal]:
    return Expense.amount * func.coalesce(Expense.rate_uah, 1)


class ExpenseRepository:
    def __init__(self, session: AsyncSession, *, owner_id: int) -> None:
        self._session = session
        self._owner_id = owner_id

    def _conditions(self, filters: ExpenseFilters) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [Expense.owner_id == self._owner_id]
        if filters.category is not None:
            conditions.append(Expense.category == filters.category)
        if filters.date_from is not None:
            conditions.append(Expense.expense_date >= filters.date_from)
        if filters.date_to is not None:
            conditions.append(Expense.expense_date <= filters.date_to)
        return conditions

    async def list_page(
        self, filters: ExpenseFilters, *, limit: int, offset: int
    ) -> tuple[list[Expense], int]:
        conditions = self._conditions(filters)
        total = (
            await self._session.execute(select(func.count(Expense.id)).where(*conditions))
        ).scalar_one()
        result = await self._session.execute(
            select(Expense)
            .where(*conditions)
            .order_by(Expense.expense_date.desc(), Expense.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def get(self, expense_id: int) -> Expense | None:
        result = await self._session.execute(
            select(Expense).where(Expense.id == expense_id, Expense.owner_id == self._owner_id)
        )
        return result.scalar_one_or_none()

    async def add(self, expense: Expense) -> Expense:
        self._session.add(expense)
        await self._session.flush()
        return expense

    async def delete(self, expense: Expense) -> None:
        await self._session.delete(expense)
        await self._session.flush()

    async def summary(self) -> list[CategoryTotal]:
        result = await self._session.execute(
            select(
                Expense.category,
                func.count(Expense.id),
                func.coalesce(func.sum(_amount_uah()), 0),
            )
            .where(Expense.owner_id == self._owner_id)
            .group_by(Expense.category)
        )
        return [
            CategoryTotal(category=row[0], count=int(row[1]), total_uah=Decimal(row[2]))
            for row in result
        ]
