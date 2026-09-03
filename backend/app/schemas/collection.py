"""Collection payloads (docs/03-api-contract.md)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.schemas.base import CamelModel
from app.schemas.common import Money, Rate


class CollectionItemOut(CamelModel):
    id: int
    catalog_item_id: int
    title: str
    country: str
    series_name: str | None
    denomination: str | None
    year: int
    is_archived: bool
    archive_reason: str | None
    quantity: int
    grade: str | None
    purchase_date: date | None
    seller: str | None
    price: Money | None
    currency: str | None
    rate_uah: Rate | None
    total_uah: Money
    notes: str | None
    # Catalog context the collection screen needs without a second request:
    # the visible thumbnail and the latest visible market price of the item.
    thumbnail_url: str | None = None
    market_price_uah: Money | None = None


class CollectionItemCreate(CamelModel):
    catalog_item_id: int
    quantity: int = Field(default=1, ge=1)
    price: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    purchase_date: date
    seller: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    grade: str | None = Field(default=None, max_length=50)


class CollectionItemUpdate(CamelModel):
    quantity: int | None = Field(default=None, ge=1)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    purchase_date: date | None = None
    seller: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    grade: str | None = Field(default=None, max_length=50)
