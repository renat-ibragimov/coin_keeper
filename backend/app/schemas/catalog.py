"""Catalog payloads (docs/03-api-contract.md)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field, model_validator

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


class CoinEdgeType(CamelModel):
    id: int
    code: str
    name: str


class CoinQualityType(CamelModel):
    id: int
    code: str
    name: str


class CoinImageOut(CamelModel):
    """One side of a coin at the sizes stored for it, plus who to credit."""

    preview: str | None
    medium: str | None
    large: str | None
    attribution: str | None


class CoinDescriptions(CamelModel):
    """The coin-collector parser's text for the requested locale
    (docs/02-data-model.md). Any of the three may still be null — the parser
    writes the key regardless of whether it found text for it."""

    general: str | None
    obverse: str | None
    reverse: str | None


class CatalogListItem(CamelModel):
    id: int
    country: str
    series_name: str | None
    denomination: CoinDenomination | None
    # What the collector typed when the dictionary had nothing to offer for
    # their country; shown in place of `denomination` (docs/04, §14).
    denomination_text: str | None
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
    purchase_total_usd: Money | None
    purchase_total_eur: Money | None
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
    edge_type: CoinEdgeType | None
    edge: str | None
    orientation: str | None
    quality_type: CoinQualityType | None
    quality: str | None
    catalog_km: str | None
    catalog_uc: str | None
    catalog_numista: str | None
    notes: str | None
    description: CoinDescriptions | None
    designers: list[str]
    sculptors: list[str]
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CatalogItemCreate(CamelModel):
    country_id: int
    series_id: int | None = None
    series_text: str | None = Field(default=None, max_length=200)
    denomination_id: int | None = None
    denomination_text: str | None = Field(default=None, max_length=200)
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
    edge_type_id: int | None = None
    edge: str | None = Field(default=None, max_length=200)
    orientation: str | None = Field(default=None, max_length=100)
    quality_type_id: int | None = None
    quality: str | None = Field(default=None, max_length=200)
    catalog_km: str | None = Field(default=None, max_length=100)
    catalog_uc: str | None = Field(default=None, max_length=100)
    catalog_numista: str | None = Field(default=None, max_length=100)
    catalog_number: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)
    # Admin only: create the record in the shared catalog instead of a
    # personal item. Regular users get a 403 (docs/03-api-contract.md).
    shared: bool = False


class NewCatalogItemIn(CamelModel):
    """A personal catalog item entered by hand on the "Додати" form.

    A subset of CatalogItemCreate, not that schema itself, and the three
    differences are the point (docs/03-api-contract.md, `POST /collection`):

    * no `shared` — this record is always personal. The shared catalog is
      read-only for everyone but an admin editing it deliberately, and the
      purchase form is not that place (CLAUDE.md).
    * no `originalLang` and no title translations — the language is detected
      and the two translated slots filled by the background translation job,
      marked `llm`, exactly as a storage location's are. A client cannot
      claim `official` or `manual` wording by the back door.
    * `material` is mandatory in one of its two shapes (owner, 2026-09-14):
      either a dictionary row (`compositionId`) or free text, because for
      most issuers the dictionary holds nothing to pick. Edge and quality
      keep the same two-shaped pair as the full schema, but the form only
      ever sends their dictionary halves.
    """

    country_id: int
    series_id: int | None = None
    series_text: str | None = Field(default=None, max_length=200)
    denomination_id: int | None = None
    denomination_text: str | None = Field(default=None, max_length=200)
    collection_group: CollectionGroup
    title_original: str = Field(min_length=1, max_length=500)
    # Required, unlike the rest of the coin's description: catalog_items.issue_year
    # is NOT NULL, and series completeness and every year filter are counted on
    # it (owner's call 2026-09-14 — a nullable year is a migration of its own).
    issue_year: int = Field(ge=1, le=2200)
    issue_date: date | None = None
    # One "Тираж" field on the form: what a catalogue publishes is the
    # announced figure, and the actual one is a later correction nobody has
    # at the moment of buying a coin.
    mintage_announced: int | None = Field(default=None, ge=0)
    composition_id: int | None = None
    material: str | None = Field(default=None, max_length=200)
    metal_kind: MetalKind = MetalKind.UNKNOWN
    weight_grams: Decimal | None = Field(default=None, ge=0)
    diameter_mm: Decimal | None = Field(default=None, ge=0)
    thickness_mm: Decimal | None = Field(default=None, ge=0)
    shape: str | None = Field(default=None, max_length=100)
    edge_type_id: int | None = None
    edge: str | None = Field(default=None, max_length=200)
    quality_type_id: int | None = None
    quality: str | None = Field(default=None, max_length=200)
    # One number, not three: a collector has the number and no reason to know
    # whose catalogue it belongs to (owner, 2026-09-14). The three named
    # columns stay on CatalogItemCreate, where the pipeline fills them.
    catalog_number: str | None = Field(default=None, max_length=100)
    # The coin described in the collector's own words, in the language of the
    # request. Stored in `descriptions` under that locale, in the shape
    # docs/02-data-model.md fixes — not in `notes`, which is a note about the
    # record rather than a description of the coin.
    description: str | None = Field(default=None, max_length=4000)
    description_obverse: str | None = Field(default=None, max_length=4000)
    description_reverse: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def check_material(self) -> NewCatalogItemIn:
        if self.composition_id is None and not (self.material or "").strip():
            msg = "Either compositionId or material text is required."
            raise ValueError(msg)
        return self


class CatalogItemUpdate(CamelModel):
    country_id: int | None = None
    series_id: int | None = None
    series_text: str | None = Field(default=None, max_length=200)
    denomination_id: int | None = None
    denomination_text: str | None = Field(default=None, max_length=200)
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
    edge_type_id: int | None = None
    edge: str | None = Field(default=None, max_length=200)
    orientation: str | None = Field(default=None, max_length=100)
    quality_type_id: int | None = None
    quality: str | None = Field(default=None, max_length=200)
    catalog_km: str | None = Field(default=None, max_length=100)
    catalog_uc: str | None = Field(default=None, max_length=100)
    catalog_numista: str | None = Field(default=None, max_length=100)
    catalog_number: str | None = Field(default=None, max_length=100)
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
    total_usd: Money | None
    total_eur: Money | None
    storage_location: str | None
    notes: str | None
