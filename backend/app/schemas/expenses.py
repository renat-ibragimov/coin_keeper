"""Expense payloads (docs/03-api-contract.md)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.models.enums import ExpenseCategory
from app.schemas.base import CamelModel
from app.schemas.common import Money, Rate


class ExpenseOut(CamelModel):
    id: int
    category: ExpenseCategory
    amount: Money
    currency_code: str
    rate_uah: Rate | None
    amount_uah: Money
    expense_date: date
    catalog_item_id: int | None
    collection_item_id: int | None
    series_id: int | None
    vendor: str | None
    description: str | None


class ExpenseCreate(CamelModel):
    category: ExpenseCategory
    amount: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    expense_date: date
    catalog_item_id: int | None = None
    series_id: int | None = None
    vendor: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=4000)


class ExpenseUpdate(CamelModel):
    category: ExpenseCategory | None = None
    amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    expense_date: date | None = None
    catalog_item_id: int | None = None
    series_id: int | None = None
    vendor: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=4000)


class ExpenseCategorySummary(CamelModel):
    category: ExpenseCategory
    count: int
    total_uah: Money


class ExpensesSummaryOut(CamelModel):
    categories: list[ExpenseCategorySummary]
    total_uah: Money
    coin_spend_uah: Money
    related_spend_uah: Money
