"""Coin material as a reference row plus two numbers.

The legacy `catalog_items.material` is one free-text field written by the uCoin
importer. At its cleanest it reads "Цинк с медным покрытием, 2.5g, ø 19mm";
at its worst the importer glued the whole coin heading in front of it
("10 гривен, 2019 На страже жизни Цинк с никелевым покрытием"). The material
itself is always the *tail* of the string, which is why every pattern here is
matched at the end.

The parser yields three things: a composition code from the `materials`
dictionary, the mass in grams and the diameter in millimetres. What it does
not recognise it leaves alone — migration 0003 keeps such a row's `material`
text untouched and lists it in the report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation


@dataclass(frozen=True, slots=True)
class MaterialSeed:
    code: str
    name_uk: str
    name_en: str


# The dictionary is seeded from what the catalogue actually contains, not from
# an imagined list of alloys: about thirty values cover all 3063 items.
MATERIALS: tuple[MaterialSeed, ...] = (
    MaterialSeed("silver_350", "Срібло 350", "Silver .350"),
    MaterialSeed("silver_400", "Срібло 400", "Silver .400"),
    MaterialSeed("silver_500", "Срібло 500", "Silver .500"),
    MaterialSeed("silver_900", "Срібло 900", "Silver .900"),
    MaterialSeed("silver_925", "Срібло 925", "Silver .925"),
    MaterialSeed("silver_999", "Срібло 999", "Silver .999"),
    MaterialSeed("silver_gilded_925", "Срібло 925 із золотим покриттям", "Gilded silver .925"),
    MaterialSeed("silver_gilded_999", "Срібло 999 із золотим покриттям", "Gilded silver .999"),
    MaterialSeed("gold_900", "Золото 900", "Gold .900"),
    MaterialSeed("gold_999", "Золото 999", "Gold .999"),
    MaterialSeed("gold_1000", "Золото 1000", "Gold 1.000"),
    MaterialSeed("bimetal", "Біметал", "Bimetal"),
    MaterialSeed("nickel_silver", "Нейзильбер", "Nickel silver"),
    MaterialSeed("aluminium_bronze", "Алюмінієва бронза", "Aluminium bronze"),
    MaterialSeed("copper_nickel", "Мельхіор", "Copper-nickel"),
    MaterialSeed(
        "copper_nickel_plated_copper",
        "Мідь із мідно-нікелевим покриттям",
        "Copper-nickel plated copper",
    ),
    MaterialSeed(
        "manganese_brass_plated_copper",
        "Мідь із марганцево-латунним покриттям",
        "Manganese-brass plated copper",
    ),
    MaterialSeed("copper_zinc", "Мідь-цинк", "Copper-zinc"),
    MaterialSeed("copper_plated_zinc", "Цинк із мідним покриттям", "Copper plated zinc"),
    MaterialSeed("nickel_plated_zinc", "Цинк із нікелевим покриттям", "Nickel plated zinc"),
    MaterialSeed("zinc_plated_steel", "Сталь із цинковим покриттям", "Zinc plated steel"),
    MaterialSeed("nickel_plated_steel", "Сталь із нікелевим покриттям", "Nickel plated steel"),
    MaterialSeed("brass_plated_steel", "Сталь із латунним покриттям", "Brass plated steel"),
    MaterialSeed("stainless_steel", "Нержавіюча сталь", "Stainless steel"),
    MaterialSeed("nickel_brass", "Нікелева латунь", "Nickel brass"),
    MaterialSeed("brass", "Латунь", "Brass"),
    MaterialSeed("bronze", "Бронза", "Bronze"),
    MaterialSeed("copper", "Мідь", "Copper"),
    MaterialSeed("aluminium", "Алюміній", "Aluminium"),
)

MATERIAL_CODES = frozenset(material.code for material in MATERIALS)

# Alloy names as the two sources write them. Matched as a suffix, longest
# first, so "Copper-Nickel plated Copper" never resolves to plain "Copper".
_PHRASES: dict[str, tuple[str, ...]] = {
    "nickel_silver": ("нейзильбер", "медь-цинк-никель", "copper-zinc-nickel"),
    "bimetal": ("би-металл", "биметалл", "bi-metal", "bimetal"),
    "aluminium_bronze": ("алюминиевая бронза", "aluminium bronze", "aluminum bronze"),
    "copper_nickel": ("медно-никелевый сплав", "мельхиор", "copper-nickel"),
    "copper_nickel_plated_copper": (
        "медь с медно-никелевым покрытием",
        "copper-nickel plated copper",
    ),
    "manganese_brass_plated_copper": (
        "медь с марганцево-латунным покрытием",
        "manganese-brass plated copper",
    ),
    "copper_zinc": ("медь-цинк", "copper-zinc"),
    "copper_plated_zinc": ("цинк с медным покрытием", "copper plated zinc"),
    "nickel_plated_zinc": ("цинк с никелевым покрытием", "nickel plated zinc"),
    "zinc_plated_steel": ("сталь с цинковым покрытием", "zinc plated steel"),
    "nickel_plated_steel": ("сталь с никелевым покрытием", "nickel plated steel"),
    "brass_plated_steel": ("сталь с латунным покрытием", "brass plated steel"),
    "stainless_steel": ("нержавеющая сталь", "stainless steel"),
    "nickel_brass": ("никелевая латунь", "nickel brass"),
    "brass": ("латунь", "brass"),
    "bronze": ("бронза", "bronze"),
    "copper": ("медь", "copper"),
    "aluminium": ("алюминий", "aluminium", "aluminum"),
}
_PHRASE_INDEX: tuple[tuple[str, str], ...] = tuple(
    sorted(
        ((phrase, code) for code, phrases in _PHRASES.items() for phrase in phrases),
        key=lambda pair: -len(pair[0]),
    )
)

# "AgСеребро 0.925", "Silver 0.900", "AgСеребро с золотым покрытием 0.999".
# The Ag/Au prefix is a uCoin artefact; the fineness is what names the row.
_PRECIOUS_RE = re.compile(
    r"(?:ag|au)?\s*(?P<metal>серебро|золото|silver|gold)"
    r"(?P<gilded>\s+с\s+золотым\s+покрытием)?\s*(?P<fineness>[01]\.\d{3})$"
)
_PRECIOUS_METAL = {"серебро": "silver", "silver": "silver", "золото": "gold", "gold": "gold"}

_MASS_RE = re.compile(r",\s*(?P<mass>\d+(?:\.\d+)?)\s*g\b")
_DIAMETER_RE = re.compile(r",\s*ø\s*(?P<diameter>\d+(?:\.\d+)?)\s*mm\b")
_SPACES_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ParsedMaterial:
    composition: str | None
    weight_grams: Decimal | None
    diameter_mm: Decimal | None

    @property
    def is_empty(self) -> bool:
        return self.composition is None and self.weight_grams is None and self.diameter_mm is None


def parse_material(text: str | None) -> ParsedMaterial:
    """Composition code, mass and diameter out of one legacy material string."""
    if not text or not text.strip():
        return ParsedMaterial(None, None, None)

    mass = _first_decimal(_MASS_RE, text, "mass")
    diameter = _first_decimal(_DIAMETER_RE, text, "diameter")
    head = _DIAMETER_RE.sub("", _MASS_RE.sub("", text))
    return ParsedMaterial(_composition_of(head), mass, diameter)


def _composition_of(head: str) -> str | None:
    normalised = _SPACES_RE.sub(" ", head.casefold().replace("ё", "е")).strip()
    if not normalised:
        return None
    precious = _PRECIOUS_RE.search(normalised)
    if precious is not None:
        metal = _PRECIOUS_METAL[precious.group("metal")]
        gilded = "_gilded" if precious.group("gilded") else ""
        fineness = precious.group("fineness").replace(".", "").lstrip("0") or "0"
        code = f"{metal}{gilded}_{fineness}"
        return code if code in MATERIAL_CODES else None
    return next((code for phrase, code in _PHRASE_INDEX if normalised.endswith(phrase)), None)


def strip_material(text: str) -> str:
    """The same string without the material the parser recognises at its end.

    The uCoin importer glued the whole coin heading together —
    "1.000.000 карбованцев, 1996 Богдан Хмельницкий AgСеребро 0.925, 16.94g" —
    so the material has to come off before anything can compare the names.
    Nothing is removed when nothing is recognised.
    """
    if not text:
        return text
    trimmed = _DIAMETER_RE.sub("", _MASS_RE.sub("", text)).rstrip(" ,")
    # lower() keeps the length for the alphabets involved, so an index found
    # in the lowered copy is an index into the original.
    lowered = _SPACES_RE.sub(" ", trimmed.lower().replace("ё", "е"))
    precious = _PRECIOUS_RE.search(lowered)
    if precious is not None:
        return trimmed[: precious.start()].rstrip(" ,-–—")
    for phrase, _code in _PHRASE_INDEX:
        if lowered.endswith(phrase):
            return trimmed[: len(trimmed) - len(phrase)].rstrip(" ,-–—")
    return trimmed


def _first_decimal(pattern: re.Pattern[str], text: str, group: str) -> Decimal | None:
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return Decimal(match.group(group))
    except InvalidOperation:
        return None
