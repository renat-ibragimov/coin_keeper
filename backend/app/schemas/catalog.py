"""Catalog payloads (docs/03-api-contract.md)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from app.models.enums import CollectionGroup, MetalKind, TranslationSource
from app.schemas.base import CamelModel
from app.schemas.common import Money, Rate


class CoinDenomination(CamelModel):
    """Face value as structure plus the label for the requested locale."""

    id: int
    value: Decimal
    unit: str
    currency_code: str
    label: str


class CoinMaterial(CamelModel):
    id: int
    code: str
    name: str


class CoinImageOut(CamelModel):
    """One side of a coin at the sizes stored for it, plus who to credit."""

    preview: str | None
    medium: str | None
    large: str | None
    attribution: str | None


class CatalogListItem(CamelModel):
    id: int
    country: str
    series_name: str | None
    denomination: CoinDenomination | None
    year: int
    # The name in the requested locale, and the slots it was chosen from.
    title: str
    title_original: str
    original_lang: str
    title_uk: str | None
    title_uk_source: TranslationSource | None
    title_en: str | None
    title_en_source: TranslationSource | None
    variety: str | None
    catalog_number: str | None
    collection_group: CollectionGroup
    metal_kind: MetalKind
    composition: CoinMaterial | None
    material: str | None
    market_price_uah: Money | None
    price_source: str | None
    price_observed_at: datetime | None
    quantity_owned: int
    purchase_total_uah: Money
    obverse_image: CoinImageOut | None
    reverse_image: CoinImageOut | None
    thumbnail_url: str | None
    is_own: bool
    is_archived: bool
    archive_reason: str | None
    source_url: str | None


class CatalogCard(CatalogListItem):
    country_id: int
    series_id: int | None
    denomination_id: int | None
    item_type: str
    subtype: str | None
    issue_date: date | None
    mintage_announced: int | None
    mintage_actual: int | None
    weight_grams: Rate | None
    diameter_mm: Rate | None
    thickness_mm: Rate | None
    shape: str | None
    edge: str | None
    orientation: str | None
    catalog_km: str | None
    catalog_uc: str | None
    catalog_numista: str | None
    notes: str | None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CatalogItemCreate(CamelModel):
    country_id: int
    series_id: int | None = None
    denomination_id: int | None = None
    collection_group: CollectionGroup
    subtype: str | None = None
    title_original: str = Field(min_length=1, max_length=500)
    original_lang: str = Field(default="uk", min_length=2, max_length=8)
    title_uk: str | None = Field(default=None, max_length=500)
    title_en: str | None = Field(default=None, max_length=500)
    issue_year: int = Field(ge=1, le=2200)
    issue_date: date | None = None
    mintage_announced: int | None = Field(default=None, ge=0)
    mintage_actual: int | None = Field(default=None, ge=0)
    composition_id: int | None = None
    material: str | None = Field(default=None, max_length=200)
    metal_kind: MetalKind = MetalKind.UNKNOWN
    weight_grams: Decimal | None = Field(default=None, ge=0)
    diameter_mm: Decimal | None = Field(default=None, ge=0)
    thickness_mm: Decimal | None = Field(default=None, ge=0)
    shape: str | None = Field(default=None, max_length=100)
    edge: str | None = Field(default=None, max_length=200)
    orientation: str | None = Field(default=None, max_length=100)
    catalog_km: str | None = Field(default=None, max_length=100)
    catalog_uc: str | None = Field(default=None, max_length=100)
    catalog_numista: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)
    # Admin only: create the record in the shared catalog instead of a
    # personal item. Regular users get a 403 (docs/03-api-contract.md).
    shared: bool = False


class CatalogItemUpdate(CamelModel):
    country_id: int | None = None
    series_id: int | None = None
    denomination_id: int | None = None
    collection_group: CollectionGroup | None = None
    subtype: str | None = None
    title_original: str | None = Field(default=None, min_length=1, max_length=500)
    original_lang: str | None = Field(default=None, min_length=2, max_length=8)
    # min_length=1 rather than the create schema's "may be absent": a translated
    # slot is either untouched (field omitted) or replaced with real text, never
    # set to an empty string (docs/03-api-contract.md, admin title editing).
    title_uk: str | None = Field(default=None, min_length=1, max_length=500)
    title_en: str | None = Field(default=None, min_length=1, max_length=500)
    issue_year: int | None = Field(default=None, ge=1, le=2200)
    issue_date: date | None = None
    mintage_announced: int | None = Field(default=None, ge=0)
    mintage_actual: int | None = Field(default=None, ge=0)
    composition_id: int | None = None
    material: str | None = Field(default=None, max_length=200)
    metal_kind: MetalKind | None = None
    weight_grams: Decimal | None = Field(default=None, ge=0)
    diameter_mm: Decimal | None = Field(default=None, ge=0)
    thickness_mm: Decimal | None = Field(default=None, ge=0)
    shape: str | None = Field(default=None, max_length=100)
    edge: str | None = Field(default=None, max_length=200)
    orientation: str | None = Field(default=None, max_length=100)
    catalog_km: str | None = Field(default=None, max_length=100)
    catalog_uc: str | None = Field(default=None, max_length=100)
    catalog_numista: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)


class ArchiveRequest(CamelModel):
    # Emptiness is checked in the route: the contract answers 400, not 422.
    reason: str = Field(max_length=1000)


class ArchiveStateOut(CamelModel):
    is_archived: bool
    archived_at: datetime | None = None
    archive_reason: str | None = None


class PriceHistoryItem(CamelModel):
    id: int
    source: str
    grade: str | None
    price: Money
    currency_code: str
    price_uah: Money | None
    observed_at: datetime
    source_url: str | None
    is_own: bool
    is_suspect: bool


class CatalogCollectionItemOut(CamelModel):
    id: int
    catalog_item_id: int
    quantity: int
    grade: str | None
    acquisition_date: date | None
    seller: str | None
    purchase_price: Money | None
    purchase_currency: str | None
    purchase_rate_uah: Rate | None
    total_uah: Money
    notes: str | None
