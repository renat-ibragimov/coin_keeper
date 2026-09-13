"""Expense use cases — the related-spend side of the money screen.

coin_purchase expenses are owned by the purchase transaction
(app/services/collection.py): creating, editing or deleting them directly
through /expenses is refused, otherwise the 1:1 between instances and their
purchase expenses would silently break (docs/04-business-rules.md, rule 4).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE
from app.models import CoinSeries, Currency, Expense, User
from app.models.enums import ExpenseCategory, UserRole
from app.repositories.catalog import CatalogRepository
from app.repositories.expenses import DailyTotal, ExpenseFilters, ExpenseRepository, MonthlyTotal
from app.repositories.rates import RateRepository
from app.schemas.expenses import (
    ExpenseCategorySummary,
    ExpenseCreate,
    ExpenseMonthTotal,
    ExpenseOut,
    ExpensePeriodTotal,
    ExpensesChartOut,
    ExpensesSummaryOut,
    ExpenseUpdate,
)

# A day-by-day chart beyond this span would draw hundreds of bars with
# nothing to read; past it the chart switches to one bar per month.
DAILY_GRANULARITY_MAX_DAYS = 31


def _shift_month(day: date, months: int) -> date:
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    return date(year, month + 1, 1)


class ExpenseError(Exception):
    pass


class ExpenseNotFoundError(ExpenseError):
    """Absent or someone else's: 404."""


class CoinPurchaseManagedError(ExpenseError):
    """coin_purchase rows are managed through /collection: 409."""

    detail = (
        "coin_purchase expenses are created and removed together with "
        "collection items; use the /collection endpoints."
    )


class UnknownCurrencyError(ExpenseError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.detail = f"Unknown currency code: {code}."


class MissingRateError(ExpenseError):
    def __init__(self, currency: str, on_date: str) -> None:
        super().__init__(currency)
        self.detail = (
            f"No exchange rate is stored for {currency} on or before {on_date}. "
            "Enter the expense in UAH or pick a date covered by the rate table."
        )


class BadReferenceError(ExpenseError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ExpenseService:
    def __init__(self, session: AsyncSession, user: User, locale: str = DEFAULT_LOCALE) -> None:
        self._session = session
        self._user = user
        self._repo = ExpenseRepository(session, owner_id=user.id, locale=locale)
        self._catalog = CatalogRepository(
            session, user_id=user.id, is_admin=user.role == UserRole.ADMIN
        )
        self._rates = RateRepository(session)

    async def list_expenses(
        self, filters: ExpenseFilters, *, limit: int, offset: int
    ) -> tuple[list[ExpenseOut], int]:
        rows, total = await self._repo.list_page(filters, limit=limit, offset=offset)
        items = [
            self._out(
                expense,
                coin_title=title if expense.category == ExpenseCategory.COIN_PURCHASE else None,
                amount_usd=amount_usd,
                amount_eur=amount_eur,
            )
            for expense, title, amount_usd, amount_eur in rows
        ]
        return items, total

    async def create(self, payload: ExpenseCreate) -> ExpenseOut:
        if payload.category == ExpenseCategory.COIN_PURCHASE:
            raise CoinPurchaseManagedError
        await self._check_references(payload.catalog_item_id, payload.series_id)
        rate = await self._resolve_rate(payload.currency, payload.expense_date)
        expense = Expense(
            owner_id=self._user.id,
            category=payload.category,
            amount=payload.amount,
            currency_code=payload.currency,
            rate_uah=rate,
            expense_date=payload.expense_date,
            catalog_item_id=payload.catalog_item_id,
            series_id=payload.series_id,
            vendor=payload.vendor,
            description=payload.description,
        )
        await self._repo.add(expense)
        return self._out(
            expense,
            amount_usd=await self._amount_usd_for(expense),
            amount_eur=await self._amount_eur_for(expense),
        )

    async def update(self, expense_id: int, payload: ExpenseUpdate) -> ExpenseOut:
        expense = await self._get_editable(expense_id)
        changes = payload.model_dump(exclude_unset=True)
        if changes.get("category") == ExpenseCategory.COIN_PURCHASE:
            raise CoinPurchaseManagedError
        if "catalog_item_id" in changes or "series_id" in changes:
            await self._check_references(
                changes.get("catalog_item_id", expense.catalog_item_id),
                changes.get("series_id", expense.series_id),
            )
        rate_needed = "currency" in changes or "expense_date" in changes
        if "currency" in changes:
            expense.currency_code = changes.pop("currency")
        for field_name, value in changes.items():
            setattr(expense, field_name, value)
        if rate_needed:
            expense.rate_uah = await self._resolve_rate(expense.currency_code, expense.expense_date)
        await self._session.flush()
        return self._out(
            expense,
            amount_usd=await self._amount_usd_for(expense),
            amount_eur=await self._amount_eur_for(expense),
        )

    async def delete(self, expense_id: int) -> None:
        expense = await self._get_editable(expense_id)
        await self._repo.delete(expense)

    async def summary(self) -> ExpensesSummaryOut:
        totals = await self._repo.summary()
        categories = sorted(totals, key=lambda row: row.total_uah, reverse=True)
        coin = sum(
            (row.total_uah for row in totals if row.category == ExpenseCategory.COIN_PURCHASE),
            Decimal(0),
        )
        related = sum(
            (row.total_uah for row in totals if row.category != ExpenseCategory.COIN_PURCHASE),
            Decimal(0),
        )
        category_summaries = [
            ExpenseCategorySummary(category=row.category, count=row.count, total_uah=row.total_uah)
            for row in categories
        ]

        by_month = await self._monthly_series()
        this_month = by_month[-1].coins_uah + by_month[-1].supporting_uah
        prev_month = by_month[-2].coins_uah + by_month[-2].supporting_uah

        return ExpensesSummaryOut(
            categories=category_summaries,
            total_uah=coin + related,
            coin_spend_uah=coin,
            related_spend_uah=related,
            by_month=by_month,
            by_category=category_summaries,
            this_month_uah=this_month,
            prev_month_uah=prev_month,
        )

    async def chart_summary(self, date_from: date, date_to: date) -> ExpensesChartOut:
        span_days = (date_to - date_from).days
        granularity: Literal["day", "month"]
        if span_days <= DAILY_GRANULARITY_MAX_DAYS:
            by_period = await self._daily_series(date_from, date_to)
            granularity = "day"
        else:
            by_period = await self._monthly_range_series(date_from, date_to)
            granularity = "month"

        totals = await self._repo.summary(date_from=date_from, date_to=date_to)
        by_category = [
            ExpenseCategorySummary(category=row.category, count=row.count, total_uah=row.total_uah)
            for row in sorted(totals, key=lambda row: row.total_uah, reverse=True)
        ]
        return ExpensesChartOut(
            granularity=granularity, by_period=by_period, by_category=by_category
        )

    # ------------------------------------------------------------- internals

    async def _daily_series(self, date_from: date, date_to: date) -> list[ExpensePeriodTotal]:
        """Every day in the range, oldest first, zero-filled where empty."""
        totals = {
            row.day: row for row in await self._repo.daily_totals(start=date_from, end=date_to)
        }
        empty = DailyTotal(day=date_from, coins_uah=Decimal(0), supporting_uah=Decimal(0))
        days = [
            date_from + timedelta(days=offset) for offset in range((date_to - date_from).days + 1)
        ]
        return [
            ExpensePeriodTotal(
                period=day.isoformat(),
                coins_uah=totals.get(day, empty).coins_uah,
                supporting_uah=totals.get(day, empty).supporting_uah,
            )
            for day in days
        ]

    async def _monthly_range_series(
        self, date_from: date, date_to: date
    ) -> list[ExpensePeriodTotal]:
        """Every calendar month touching the range, oldest first, zero-filled where empty."""
        start_month = date_from.replace(day=1)
        end_month = date_to.replace(day=1)
        totals = {
            row.month: row
            for row in await self._repo.monthly_totals(start=start_month, end=date_to)
        }
        months = []
        cursor = start_month
        while cursor <= end_month:
            months.append(cursor)
            cursor = _shift_month(cursor, 1)
        empty = MonthlyTotal(month=start_month, coins_uah=Decimal(0), supporting_uah=Decimal(0))
        return [
            ExpensePeriodTotal(
                period=month.strftime("%Y-%m"),
                coins_uah=totals.get(month, empty).coins_uah,
                supporting_uah=totals.get(month, empty).supporting_uah,
            )
            for month in months
        ]

    async def _monthly_series(self) -> list[ExpenseMonthTotal]:
        """Last 12 calendar months, oldest first, zero-filled where empty."""
        current_month = date.today().replace(day=1)
        start = _shift_month(current_month, -11)
        totals = {row.month: row for row in await self._repo.monthly_totals(start=start)}
        months = [_shift_month(start, offset) for offset in range(12)]
        empty = MonthlyTotal(month=current_month, coins_uah=Decimal(0), supporting_uah=Decimal(0))
        return [
            ExpenseMonthTotal(
                month=month.strftime("%Y-%m"),
                coins_uah=totals.get(month, empty).coins_uah,
                supporting_uah=totals.get(month, empty).supporting_uah,
            )
            for month in months
        ]

    async def _get_editable(self, expense_id: int) -> Expense:
        expense = await self._repo.get(expense_id)
        if expense is None:
            raise ExpenseNotFoundError
        if expense.category == ExpenseCategory.COIN_PURCHASE:
            raise CoinPurchaseManagedError
        return expense

    async def _resolve_rate(self, currency: str, on_date: date) -> Decimal:
        if await self._session.get(Currency, currency) is None:
            raise UnknownCurrencyError(currency)
        if currency == "UAH":
            return Decimal(1)
        rate = await self._rates.rate_on(currency, on_date)
        if rate is None:
            raise MissingRateError(currency, on_date.isoformat())
        return rate

    async def _check_references(self, catalog_item_id: int | None, series_id: int | None) -> None:
        if catalog_item_id is not None:
            item = await self._catalog.get_visible(catalog_item_id)
            if item is None:
                raise BadReferenceError("Unknown catalogItemId.")
        if series_id is not None and await self._session.get(CoinSeries, series_id) is None:
            raise BadReferenceError("Unknown seriesId.")

    async def _amount_usd_for(self, expense: Expense) -> Decimal | None:
        """The rate on the expense's OWN date, not today's -- what it cost
        then (docs/BACKLOG.md, NBU rates follow-up). None if NBU has no
        rate that far back, rather than a live-rate guess."""
        usd_rate = await self._rates.rate_on("USD", expense.expense_date)
        if usd_rate is None:
            return None
        amount_uah = expense.amount * (expense.rate_uah or Decimal(1))
        return amount_uah / usd_rate

    async def _amount_eur_for(self, expense: Expense) -> Decimal | None:
        """Same as _amount_usd_for(), converted by the EUR rate instead."""
        eur_rate = await self._rates.rate_on("EUR", expense.expense_date)
        if eur_rate is None:
            return None
        amount_uah = expense.amount * (expense.rate_uah or Decimal(1))
        return amount_uah / eur_rate

    @staticmethod
    def _out(
        expense: Expense,
        *,
        coin_title: str | None = None,
        amount_usd: Decimal | None = None,
        amount_eur: Decimal | None = None,
    ) -> ExpenseOut:
        return ExpenseOut(
            id=expense.id,
            category=expense.category,
            amount=expense.amount,
            currency_code=expense.currency_code,
            rate_uah=expense.rate_uah,
            amount_uah=expense.amount * (expense.rate_uah or Decimal(1)),
            amount_usd=amount_usd,
            amount_eur=amount_eur,
            expense_date=expense.expense_date,
            catalog_item_id=expense.catalog_item_id,
            collection_item_id=expense.collection_item_id,
            series_id=expense.series_id,
            vendor=expense.vendor,
            description=expense.description,
            coin_title=coin_title,
        )
