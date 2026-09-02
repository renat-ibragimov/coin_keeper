"""Reference data payloads: countries, denominations, currencies."""

from __future__ import annotations

from app.schemas.base import CamelModel


class CountryOut(CamelModel):
    id: int
    code: str | None
    name: str
    name_ru: str | None
    name_en: str | None
    collect_variants: bool


class DenominationOut(CamelModel):
    id: int
    country_id: int
    currency_code: str | None
    value_minor_units: int | None
    label: str
    label_ru: str | None
    label_en: str | None
    sort_order: int


class CurrencyOut(CamelModel):
    code: str
    name: str
    symbol: str | None
    decimal_places: int
