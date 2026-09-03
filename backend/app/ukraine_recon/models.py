"""The one record format shared by the three sources."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from app.ukraine_recon.normalize import match_key

SOURCE_UA_COINS = "ua_coins"
SOURCE_NBU = "nbu"
SOURCE_WIKIPEDIA = "wikipedia"
SOURCES = (SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA)


@dataclass
class SourceRecord:
    source: str
    source_id: str
    title_uk: str | None
    denomination: Decimal | None
    year: int | None
    url: str
    title_ru: str | None = None
    denomination_label: str | None = None
    currency: str = "UAH"
    issue_date: str | None = None
    mintage: int | None = None
    mintage_actual: int | None = None
    metal: str | None = None
    series: str | None = None
    price: Decimal | None = None
    price_date: str | None = None
    kind: str = "coin"
    image_urls: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return match_key(self.denomination, self.year, self.title_uk or "")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for name in ("denomination", "price"):
            value = payload[name]
            payload[name] = None if value is None else str(value)
        return payload


def records_to_json(records: list[SourceRecord]) -> list[dict[str, Any]]:
    return [record.to_dict() for record in records]
