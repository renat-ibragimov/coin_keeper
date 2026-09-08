"""Collection payloads (docs/03-api-contract.md)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field

from app.models.enums import CollectionGroup
from app.schemas.base import CamelModel
from app.schemas.common import Money, Rate


class CollectionPositionOut(CamelModel):
    """One catalog item grouped from all of the owner's purchases of it.

    The grid and table listing shows positions, not individual purchases —
    those live in the per-purchase CollectionItemOut, reachable one at a
    time via GET/PATCH/DELETE /collection/{id} (docs/03-api-contract.md).
    """

    catalog_item_id: int
    title: str
    country: str
    series_name: str | None
    collection_group: CollectionGroup
    denomination: str | None
    year: int
    is_archived: bool
    archive_reason: str | None
    total_quantity: int
    total_spend_uah: Money
    market_value_uah: Money | None
    last_acquisition_date: date | None
    grades: list[str]
    thumbnail_url: str | None = None


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
