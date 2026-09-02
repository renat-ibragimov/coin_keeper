"""Series payloads (docs/03-api-contract.md)."""

from __future__ import annotations

from pydantic import Field

from app.schemas.base import CamelModel
from app.schemas.common import Money


class SeriesOut(CamelModel):
    id: int
    country_id: int
    name: str
    name_ru: str | None
    name_en: str | None
    description: str | None
    start_year: int | None
    end_year: int | None


class SeriesCreate(CamelModel):
    country_id: int
    name: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=4000)
    start_year: int | None = Field(default=None, ge=1, le=2200)
    end_year: int | None = Field(default=None, ge=1, le=2200)


class SeriesSummaryOut(CamelModel):
    total: int
    owned: int
    missing: int
    completion_percent: float
    purchase_total_uah: Money
    current_value_uah: Money
    unpriced_missing: int
