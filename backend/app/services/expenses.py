"""Expense use cases — the related-spend side of the money screen.

coin_purchase expenses are owned by the purchase transaction
(app/services/collection.py): creating, editing or deleting them directly
through /expenses is refused, otherwise the 1:1 between instances and their
purchase expenses would silently break (docs/04-business-rules.md, rule 4).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CoinSeries, Currency, Expense, User
from app.models.enums import ExpenseCategory, UserRole
from app.repositories.catalog import CatalogRepository
from app.repositories.expenses import ExpenseFilters, ExpenseRepository
from app.repositories.rates import RateRepository
from app.schemas.expenses import (
    ExpenseCategorySummary,
    ExpenseCreate,
    ExpenseOut,
    ExpensesSummaryOut,
    ExpenseUpdate,
)


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
    def __init__(self, session: AsyncSession, user: User) -> None:
        self._session = session
        self._user = user
        self._repo = ExpenseRepository(session, owner_id=user.id)
        self._catalog = CatalogRepository(
            session, user_id=user.id, is_admin=user.role == UserRole.ADMIN
        )
        self._rates = RateRepository(session)

    async def list_expenses(
        self, filters: ExpenseFilters, *, limit: int, offset: int
    ) -> tuple[list[ExpenseOut], int]:
        expenses, total = await self._repo.list_page(filters, limit=limit, offset=offset)
        return [self._out(expense) for expense in expenses], total

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
        return self._out(expense)

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
        return self._out(expense)

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
        return ExpensesSummaryOut(
            categories=[
                ExpenseCategorySummary(
                    category=row.category, count=row.count, total_uah=row.total_uah
                )
                for row in categories
            ],
            total_uah=coin + related,
            coin_spend_uah=coin,
            related_spend_uah=related,
        )

    # ------------------------------------------------------------- internals

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

    @staticmethod
    def _out(expense: Expense) -> ExpenseOut:
        return ExpenseOut(
            id=expense.id,
            category=expense.category,
            amount=expense.amount,
            currency_code=expense.currency_code,
            rate_uah=expense.rate_uah,
            amount_uah=expense.amount * (expense.rate_uah or Decimal(1)),
            expense_date=expense.expense_date,
            catalog_item_id=expense.catalog_item_id,
            collection_item_id=expense.collection_item_id,
            series_id=expense.series_id,
            vendor=expense.vendor,
            description=expense.description,
        )
