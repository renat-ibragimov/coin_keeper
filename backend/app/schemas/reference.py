"""Reference data payloads: countries, denominations, currencies."""

from __future__ import annotations

from decimal import Decimal

from app.schemas.base import CamelModel


class CountryOut(CamelModel):
    """`name` is the country in the requested locale; the slots are all there
    too, so a form can search by any of them (docs/03-api-contract.md)."""

    id: int
    code: str | None
    name: str
    name_original: str
    original_lang: str
    name_uk: str | None
    name_en: str | None
    collect_variants: bool
    is_active: bool
    sort_order: int


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
