"""Coin edge as a reference row, mirroring `materials.py`.

Seeded from what the confirmed (Ukrainian) catalogue actually contains: five
values, carried over from the legacy collection as bare English codes
(`reeded`, `plain_incuse_lettering`, ...) with no dictionary behind them at
all until now (docs/04-business-rules.md, rule 14).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EdgeTypeSeed:
    code: str
    name_uk: str
    name_en: str


EDGE_TYPES: tuple[EdgeTypeSeed, ...] = (
    EdgeTypeSeed("plain", "Гладкий", "Plain"),
    EdgeTypeSeed("reeded", "Рифлений", "Reeded"),
    EdgeTypeSeed("sector_reeded", "Секторне рифлення", "Sector reeded"),
    EdgeTypeSeed(
        "plain_incuse_lettering", "Гладкий із заглибленим написом", "Plain with incuse lettering"
    ),
    EdgeTypeSeed("not_specified", "Не вказано", "Not specified"),
)

EDGE_TYPE_CODES = frozenset(edge_type.code for edge_type in EDGE_TYPES)

# The legacy collection's own raw values, each already a valid code above —
# no phrase parsing needed, unlike materials, because every known raw value
# already is a code (docs/09-data-migration.md).
LEGACY_ALIASES: dict[str, str] = {code: code for code in EDGE_TYPE_CODES}


def resolve_edge_code(text: str | None) -> str | None:
    """The dictionary code for a raw `edge` value, or None if unrecognised."""
    if not text:
        return None
    return LEGACY_ALIASES.get(text.strip().casefold())
