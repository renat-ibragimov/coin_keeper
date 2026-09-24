"""Reference data payloads: countries, denominations, currencies."""

from __future__ import annotations

from decimal import Decimal

from app.schemas.base import CamelModel


class CountryOut(CamelModel):
    """`name` is the country in the requested locale; the slots are all there
    too, so a form can search by any of them (docs/api.md)."""

    id: int
    code: str | None
    name: str
    name_original: str
    original_lang: str
    name_uk: str | None
    name_en: str | None
    collect_variants: bool
    is_active: bool
    # Whether the general catalog counts this country as "the catalogue"
    # (docs/business-rules.md, BR-13a) — GET /catalog hides everything of an
    # unconfirmed country, however much of it a user personally owns. The
    # series screens read this to explain that gap instead of just looking
    # broken (owner-reported, 2026-09-13).
    catalog_confirmed: bool
    sort_order: int
    min_year: int | None
    max_year: int | None


class DenominationOut(CamelModel):
    """Structure plus the label rendered for the requested locale."""

    id: int
    country_id: int
    currency_code: str
    value: Decimal
    unit: str
    label: str
    sort_order: int


class CurrencyOut(CamelModel):
    code: str
    name: str
    symbol: str | None
    decimal_places: int
