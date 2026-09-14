"""Collection payloads (docs/03-api-contract.md)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import Field, model_validator

from app.models.enums import CollectionGroup, ExpenseCategory
from app.schemas.base import CamelModel
from app.schemas.catalog import NewCatalogItemIn
from app.schemas.common import Money, Rate


class StorageLocationOut(CamelModel):
    """A name, not an id: the client never tracks storage-location ids
    (docs/04-business-rules.md). `custom` is true for the owner's own entry —
    only those can be deleted; the four system presets cannot."""

    name: str
    custom: bool


class StorageLocationCreate(CamelModel):
    name: str = Field(min_length=1, max_length=200)


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
    storage_location: str | None
    notes: str | None
    # Catalog context the collection screen needs without a second request:
    # the visible thumbnail and the latest visible market price of the item.
    thumbnail_url: str | None = None
    market_price_uah: Money | None = None


class ExtraExpenseIn(CamelModel):
    """A supporting expense recorded together with the purchase it belongs to.

    Delivery, a holder, a grading fee — money spent on this coin at the moment
    it was bought, and having to reopen the money journal to write it down is
    how it ends up never written down (owner's call, 2026-09-14). What comes
    out is an ordinary manual expense linked to the coin: same category list,
    same `catalogItemId` link, edited and deleted in «Гроші» like any other,
    and deleting one leaves the coin alone.

    Date and vendor are not fields here — they come from the purchase, which
    is the point of recording the two together.
    """

    category: ExpenseCategory
    # `gt=0`, exactly as POST /expenses: a free coin is a fact, a free
    # delivery is a blank someone forgot to fill in.
    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def reject_coin_purchase(self) -> ExtraExpenseIn:
        if self.category == ExpenseCategory.COIN_PURCHASE:
            msg = "coin_purchase is written by the purchase itself, not listed beside it."
            raise ValueError(msg)
        return self


class CollectionItemCreate(CamelModel):
    """A purchase of a coin the catalog already has, or of one it does not
    (docs/03-api-contract.md, `POST /collection`).

    `newCatalogItem` is what the "Додати" form sends when the collector typed
    a name the catalog search did not find: the personal item, the instance
    and the coin_purchase expense are then created in one transaction, so a
    rejected purchase cannot leave an orphaned catalog record behind. Exactly
    one of the two fields is given — neither and both are 422.

    `extraExpenses` rides along the same transaction: the delivery and the
    coin are one act of spending, and either both are recorded or neither is.
    """

    catalog_item_id: int | None = None
    new_catalog_item: NewCatalogItemIn | None = None
    quantity: int = Field(default=1, ge=1)
    price: Decimal = Field(ge=0)
    currency: str = Field(min_length=3, max_length=3)
    purchase_date: date
    seller: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    grade: str | None = Field(default=None, max_length=50)
    storage_location: str | None = Field(default=None, max_length=200)
    # Capped because nothing sane needs more: the form offers one row at a
    # time and a purchase with a dozen side expenses is a data-entry accident.
    extra_expenses: list[ExtraExpenseIn] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def check_coin_reference(self) -> CollectionItemCreate:
        if (self.catalog_item_id is None) == (self.new_catalog_item is None):
            msg = "Give exactly one of catalogItemId or newCatalogItem."
            raise ValueError(msg)
        return self


class CollectionItemUpdate(CamelModel):
    quantity: int | None = Field(default=None, ge=1)
    price: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    purchase_date: date | None = None
    seller: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=4000)
    grade: str | None = Field(default=None, max_length=50)
    storage_location: str | None = Field(default=None, max_length=200)
