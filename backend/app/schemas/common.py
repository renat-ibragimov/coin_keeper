"""Shared wire types: money as strings, paginated envelopes (docs/03-api-contract.md)."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

from app.schemas.base import CamelModel

# Money travels as a string ("1923.00"), never a JSON number: a JS frontend
# would lose precision on large amounts.
Money = Annotated[
    Decimal,
    PlainSerializer(lambda v: f"{v:.2f}", return_type=str, when_used="json"),
]

# Exchange rates keep their full precision but drop trailing zeros.
Rate = Annotated[
    Decimal,
    PlainSerializer(lambda v: format(v.normalize(), "f"), return_type=str, when_used="json"),
]


class Page[ItemT](CamelModel):
    items: list[ItemT]
    total: int
    page: int
    page_size: int
