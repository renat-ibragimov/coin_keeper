"""Completeness payloads: completeness grouped by an arbitrary catalog field,
generalizing the per-series summary (docs/api.md)."""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel
from app.schemas.common import Money

CompletenessGroupBy = Literal["series", "year", "denomination", "material", "edge", "quality"]


class CompletenessSummaryOut(CamelModel):
    total: int
    owned: int
    missing: int
    completion_percent: float
    purchase_total_uah: Money
    current_value_uah: Money
    unpriced_missing: int


class CompletenessGroupOut(CamelModel):
    """One group of the chosen dimension. `label`/`country_id`/`description`/
    `start_year`/`end_year`/`sort_order` are populated from the dimension's
    own dictionary where it has one (series, denomination, material) and left
    `None` where it does not (`year` needs no lookup, `unassigned` has no
    label of its own — the frontend renders it from `unassigned` + `groupBy`).
    """

    group_by: CompletenessGroupBy
    value: int | None
    unassigned: bool
    label: str | None
    country_id: int | None = None
    description: str | None = None
    start_year: int | None = None
    end_year: int | None = None
    sort_order: int | None = None
    summary: CompletenessSummaryOut
