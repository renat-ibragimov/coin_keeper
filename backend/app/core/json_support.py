"""The one `default=` every report's `json.dumps` call shares.

A report dataclass writes counts and pre-formatted strings, but a `Decimal`
sum or holding can still reach `json.dumps` through a row a step forgot to
stringify (a duplicate-merge candidate's face value, say). Rather than chase
each leak at the source, every report's `write()` passes this as `default=`
so the write never fails — a stray `Decimal` becomes a string instead of a
`TypeError`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def json_default(value: Any) -> str:
    if isinstance(value, Decimal):
        return str(value)
    message = f"Object of type {type(value).__name__} is not JSON serializable"
    raise TypeError(message)
