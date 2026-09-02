"""Type conversions from SQLite to PostgreSQL (docs/09-data-migration.md)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.legacy_migration.convert import (
    ConversionError,
    to_bool,
    to_date,
    to_enum_value,
    to_jsonb,
    to_money,
    to_rate,
    to_timestamptz,
)


@pytest.mark.parametrize(
    ("value", "expected"), [(1, True), (0, False), (None, False), ("1", True), ("0", False)]
)
def test_integer_flags_become_booleans(value: object, expected: bool) -> None:
    assert to_bool(value) is expected


def test_money_keeps_two_places_and_rounds_half_up() -> None:
    assert to_money(42765.664) == Decimal("42765.66")
    assert to_money(0.005) == Decimal("0.01")
    assert to_money(None) is None


def test_rate_keeps_six_places() -> None:
    # NBU rates are fractional; two places would lose them.
    assert to_rate(41.1234564) == Decimal("41.123456")


def test_dates_parse_strictly_and_empty_becomes_null() -> None:
    assert to_date("2021-05-01") == date(2021, 5, 1)
    assert to_date("") is None
    with pytest.raises(ConversionError):
        to_date("01.05.2021")


def test_naive_timestamps_are_read_as_utc() -> None:
    """SQLite wrote some timestamps without a zone; the doc says treat as UTC."""
    assert to_timestamptz("2026-08-06 12:20:27") == datetime(2026, 8, 6, 12, 20, 27, tzinfo=UTC)


def test_zoned_timestamps_keep_their_zone() -> None:
    assert to_timestamptz("2026-08-06T12:20:27Z") == datetime(2026, 8, 6, 12, 20, 27, tzinfo=UTC)


def test_enum_values_are_lowercased() -> None:
    """A cheap guard: the legacy CHECK only ever allowed lower case."""
    allowed = frozenset({"circulation", "commemorative"})
    assert to_enum_value("Commemorative", allowed) == "commemorative"
    assert to_enum_value("  CIRCULATION  ", allowed) == "circulation"
    assert to_enum_value(None, allowed, default="circulation") == "circulation"
    with pytest.raises(ConversionError):
        to_enum_value("nonsense", allowed)


def test_invalid_json_becomes_null_and_is_reported() -> None:
    payload, invalid = to_jsonb("{not valid json")
    assert payload is None
    assert invalid is True

    payload, invalid = to_jsonb('{"text": "666"}')
    assert payload == {"text": "666"}
    assert invalid is False

    # A bare scalar is valid JSON but not a payload; keep it addressable.
    payload, invalid = to_jsonb('"UAH"')
    assert payload == {"value": "UAH"}
    assert invalid is False
