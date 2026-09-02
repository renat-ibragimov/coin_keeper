"""Type conversions from the SQLite schema to the PostgreSQL one.

The mapping table is in docs/09-data-migration.md. Everything here is pure, so
the rules can be tested without a database.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

MONEY_PLACES = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")

# SQLite wrote timestamps two ways: ISO with a zone, and its own
# "YYYY-MM-DD HH:MM:SS" without one. The second kind is treated as UTC.
_NAIVE_FORMATS = ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S")


class ConversionError(ValueError):
    """The value cannot be represented in the target type."""


def to_bool(value: Any) -> bool:
    """SQLite stored flags as INTEGER 0/1."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "t", "yes"}
    msg = f"cannot read {value!r} as a boolean"
    raise ConversionError(msg)


def to_money(value: Any) -> Decimal | None:
    """REAL -> numeric(14,2). Rounds half up, the way money is rounded."""
    return _to_decimal(value, MONEY_PLACES)


def to_rate(value: Any) -> Decimal | None:
    """REAL -> numeric(14,6). Six places: NBU rates are fractional."""
    return _to_decimal(value, RATE_PLACES)


def _to_decimal(value: Any, places: Decimal) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        # str() first: Decimal(float) would carry the binary noise across.
        return Decimal(str(value)).quantize(places, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        msg = f"cannot read {value!r} as a number"
        raise ConversionError(msg) from exc


def to_date(value: Any) -> date | None:
    """TEXT -> date. Parsed strictly; empty becomes NULL."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        msg = f"cannot read {value!r} as a date"
        raise ConversionError(msg) from exc


def to_timestamptz(value: Any) -> datetime | None:
    """TEXT -> timestamptz. A value without a zone is taken as UTC."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).strip()
    if not text:
        return None

    normalised = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalised)
    except ValueError:
        parsed = None
    if parsed is None:
        for pattern in _NAIVE_FORMATS:
            try:
                # Naive on purpose; the zone is attached below.
                parsed = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
    if parsed is None:
        msg = f"cannot read {value!r} as a timestamp"
        raise ConversionError(msg)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def to_enum_value(value: Any, allowed: frozenset[str], *, default: str | None = None) -> str | None:
    """TEXT + CHECK -> ENUM. Values match once the case is normalised."""
    if value is None or str(value).strip() == "":
        return default
    candidate = str(value).strip().lower()
    if candidate not in allowed:
        if default is not None:
            return default
        msg = f"{value!r} is not one of {sorted(allowed)}"
        raise ConversionError(msg)
    return candidate


def to_jsonb(value: Any) -> tuple[dict[str, Any] | list[Any] | None, bool]:
    """TEXT -> jsonb. Returns (payload, was_invalid); invalid JSON becomes NULL.

    Invalid payloads are not an error worth stopping for — they are counted in
    the report instead (docs/09-data-migration.md).
    """
    if value is None or str(value).strip() == "":
        return None, False
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None, True
    if isinstance(parsed, dict | list):
        return parsed, False
    # A bare scalar is valid JSON but not a payload; keep it addressable.
    return {"value": parsed}, False
