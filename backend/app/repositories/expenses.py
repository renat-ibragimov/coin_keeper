"""Owner-scoped expense data access (docs/07-auth.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import CatalogItem, Expense
from app.models.enums import ExpenseCategory
from app.repositories.localization import localized


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


@dataclass
class MonthlyTotal:
    month: date  # first day of the month
    coins_uah: Decimal
    supporting_uah: Decimal


def _amount_uah() -> ColumnElement[Decimal]:
    return Expense.amount * func.coalesce(Expense.rate_uah, 1)


def _coin_title(locale: str) -> ColumnElement[str]:
    return localized(
        locale,
        uk=CatalogItem.title_uk,
        en=CatalogItem.title_en,
        original=CatalogItem.title_original,
    )


class ExpenseRepository:
    def __init__(
        self, session: AsyncSession, *, owner_id: int, locale: str = DEFAULT_LOCALE
    ) -> None:
        self._session = session
        self._owner_id = owner_id
        self._locale = locale

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
    ) -> tuple[list[tuple[Expense, str | None]], int]:
        conditions = self._conditions(filters)
        total = (
            await self._session.execute(select(func.count(Expense.id)).where(*conditions))
        ).scalar_one()
        result = await self._session.execute(
            select(Expense, _coin_title(self._locale))
            .outerjoin(CatalogItem, CatalogItem.id == Expense.catalog_item_id)
            .where(*conditions)
            .order_by(Expense.expense_date.desc(), Expense.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = result.all()
        return [(row[0], row[1]) for row in rows], total

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

    async def monthly_totals(self, *, start: date) -> list[MonthlyTotal]:
        month_col = func.date_trunc("month", Expense.expense_date)
        coin_amount = case(
            (Expense.category == ExpenseCategory.COIN_PURCHASE, _amount_uah()), else_=0
        )
        supporting_amount = case(
            (Expense.category != ExpenseCategory.COIN_PURCHASE, _amount_uah()), else_=0
        )
        result = await self._session.execute(
            select(
                month_col,
                func.coalesce(func.sum(coin_amount), 0),
                func.coalesce(func.sum(supporting_amount), 0),
            )
            .where(Expense.owner_id == self._owner_id, Expense.expense_date >= start)
            .group_by(month_col)
        )
        return [
            MonthlyTotal(
                month=row[0].date(),
                coins_uah=Decimal(row[1]),
                supporting_uah=Decimal(row[2]),
            )
            for row in result
        ]
