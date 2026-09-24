"""Owner-scoped expense data access (docs/auth.md)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import CatalogItem, ExchangeRate, Expense
from app.models.enums import ExpenseCategory
from app.repositories.localization import localized


@dataclass
class ExpenseFilters:
    category: ExpenseCategory | None = None
    date_from: date | None = None
    date_to: date | None = None
    # Every column of the journal sorts (docs/ui.md).
    sort: str = "date"  # date | category | description | vendor | amount
    order: str = "desc"


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


@dataclass
class DailyTotal:
    day: date
    coins_uah: Decimal
    supporting_uah: Decimal


def _amount_uah() -> ColumnElement[Decimal]:
    return Expense.amount * func.coalesce(Expense.rate_uah, 1)


def _rate_on_expense_date(code: str) -> ColumnElement[Decimal]:
    return (
        select(ExchangeRate.rate_uah)
        .where(
            ExchangeRate.currency_code == code,
            ExchangeRate.effective_date <= Expense.expense_date,
        )
        .order_by(ExchangeRate.effective_date.desc())
        .limit(1)
        .scalar_subquery()
    )


def _amount_usd() -> ColumnElement[Decimal]:
    """The UAH amount converted by the USD rate on the expense's OWN date --
    what it cost then, not a live estimate (docs/business-rules.md,
    BR-6). NULL (no rate that far back) when there simply is none;
    SQL division by NULL yields NULL rather than raising."""
    return _amount_uah() / _rate_on_expense_date("USD")


def _amount_eur() -> ColumnElement[Decimal]:
    """Same as _amount_usd(), converted by the EUR rate instead."""
    return _amount_uah() / _rate_on_expense_date("EUR")


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

    def _order_by(self, filters: ExpenseFilters) -> list[Any]:
        descending = filters.order == "desc"
        columns: dict[str, Any] = {
            "date": Expense.expense_date,
            "category": Expense.category,
            # What the "Опис" column shows: the coin's name for a purchase,
            # the typed description for everything else.
            "description": func.coalesce(
                func.nullif(func.btrim(Expense.description), ""), _coin_title(self._locale)
            ),
            "vendor": Expense.vendor,
            "amount": _amount_uah(),
        }
        column = columns.get(filters.sort, columns["date"])
        ordering = column.desc().nulls_last() if descending else column.asc().nulls_last()
        # A stable tiebreaker, and the journal's own order within one day.
        return [ordering, Expense.id.desc()]

    async def list_page(
        self, filters: ExpenseFilters, *, limit: int, offset: int
    ) -> tuple[list[tuple[Expense, str | None, Decimal | None, Decimal | None]], int]:
        conditions = self._conditions(filters)
        total = (
            await self._session.execute(select(func.count(Expense.id)).where(*conditions))
        ).scalar_one()
        result = await self._session.execute(
            select(Expense, _coin_title(self._locale), _amount_usd(), _amount_eur())
            .outerjoin(CatalogItem, CatalogItem.id == Expense.catalog_item_id)
            .where(*conditions)
            .order_by(*self._order_by(filters))
            .limit(limit)
            .offset(offset)
        )
        rows = result.all()
        return [(row[0], row[1], row[2], row[3]) for row in rows], total

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

    async def summary(
        self, *, date_from: date | None = None, date_to: date | None = None
    ) -> list[CategoryTotal]:
        conditions = [Expense.owner_id == self._owner_id]
        if date_from is not None:
            conditions.append(Expense.expense_date >= date_from)
        if date_to is not None:
            conditions.append(Expense.expense_date <= date_to)
        result = await self._session.execute(
            select(
                Expense.category,
                func.count(Expense.id),
                func.coalesce(func.sum(_amount_uah()), 0),
            )
            .where(*conditions)
            .group_by(Expense.category)
        )
        return [
            CategoryTotal(category=row[0], count=int(row[1]), total_uah=Decimal(row[2]))
            for row in result
        ]

    async def monthly_totals(self, *, start: date, end: date | None = None) -> list[MonthlyTotal]:
        month_col = func.date_trunc("month", Expense.expense_date)
        coin_amount = case(
            (Expense.category == ExpenseCategory.COIN_PURCHASE, _amount_uah()), else_=0
        )
        supporting_amount = case(
            (Expense.category != ExpenseCategory.COIN_PURCHASE, _amount_uah()), else_=0
        )
        conditions = [Expense.owner_id == self._owner_id, Expense.expense_date >= start]
        if end is not None:
            conditions.append(Expense.expense_date <= end)
        result = await self._session.execute(
            select(
                month_col,
                func.coalesce(func.sum(coin_amount), 0),
                func.coalesce(func.sum(supporting_amount), 0),
            )
            .where(*conditions)
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

    async def daily_totals(self, *, start: date, end: date) -> list[DailyTotal]:
        coin_amount = case(
            (Expense.category == ExpenseCategory.COIN_PURCHASE, _amount_uah()), else_=0
        )
        supporting_amount = case(
            (Expense.category != ExpenseCategory.COIN_PURCHASE, _amount_uah()), else_=0
        )
        result = await self._session.execute(
            select(
                Expense.expense_date,
                func.coalesce(func.sum(coin_amount), 0),
                func.coalesce(func.sum(supporting_amount), 0),
            )
            .where(
                Expense.owner_id == self._owner_id,
                Expense.expense_date >= start,
                Expense.expense_date <= end,
            )
            .group_by(Expense.expense_date)
        )
        return [
            DailyTotal(day=row[0], coins_uah=Decimal(row[1]), supporting_uah=Decimal(row[2]))
            for row in result
        ]
