"""Every issuing country, with the three name slots.

`name_original` is the endonym — what the issuer calls itself — and
`original_lang` says which language that is. Both come from CLDR for the
ISO 3166-1 countries; the historical issuers are written by hand, because
ISO 3166-3 carries no names and CLDR resolves those codes to the successor
state (SU answers "Russia", YU answers "Serbia").

Visibility follows docs/04-business-rules.md: `is_active` drives the storefront
(country chips, the default shared catalogue), while the personal-item form
offers every country regardless. Only Ukraine is seeded active; a country the
database already holds keeps whatever state it has.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

SEED_PATH = Path(__file__).with_name("countries.json")

UKRAINE_CODE = "UA"
USSR_CODE = "SUHH"
USA_CODE = "US"

# The storefront order: Ukraine first, everything else by its localised name.
UKRAINE_SORT_ORDER = 0
DEFAULT_SORT_ORDER = 100


@dataclass(frozen=True, slots=True)
class CountrySeed:
    code: str
    name_original: str
    original_lang: str
    name_uk: str
    name_en: str
    # Names the legacy database may hold for the same country. Matching on
    # these is what keeps the existing ids — and every row pointing at them.
    aliases: tuple[str, ...] = field(default=())

    @property
    def sort_order(self) -> int:
        return UKRAINE_SORT_ORDER if self.code == UKRAINE_CODE else DEFAULT_SORT_ORDER

    @property
    def is_active(self) -> bool:
        return self.code == UKRAINE_CODE

    def matches(self, name: str) -> bool:
        candidate = name.strip().casefold()
        known = (self.name_original, self.name_uk, self.name_en, *self.aliases)
        return any(candidate == value.casefold() for value in known)


@cache
def load_countries() -> tuple[CountrySeed, ...]:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    return tuple(
        CountrySeed(
            code=entry["code"],
            name_original=entry["nameOriginal"],
            original_lang=entry["originalLang"],
            name_uk=entry["nameUk"],
            name_en=entry["nameEn"],
            aliases=tuple(entry.get("aliases", ())),
        )
        for entry in payload["countries"]
    )


def find_by_name(name: str) -> CountrySeed | None:
    """The seed entry a stored country name refers to, or None."""
    return next((country for country in load_countries() if country.matches(name)), None)


def find_by_code(code: str) -> CountrySeed | None:
    return next((country for country in load_countries() if country.code == code), None)
