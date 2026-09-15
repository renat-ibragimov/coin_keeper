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
# an imagined list of alloys.
#
# Fineness is deliberately not part of it: the National Bank never states a
# fineness for silver or gold (its own "Матеріал" filter offers only the bare
# metal, `NBU_METALS` in app/ukraine_pipeline/sources.py), so a specific
# "Срібло 925" the legacy collection once carried was never something our
# only source of truth actually said — dropped in favour of the plain metal
# name rather than keep unverifiable precision (owner's call, 2026-09-12).
MATERIALS: tuple[MaterialSeed, ...] = (
    MaterialSeed("silver", "Срібло", "Silver"),
    MaterialSeed("silver_gilded", "Срібло із золотим покриттям", "Gilded silver"),
    MaterialSeed("gold", "Золото", "Gold"),
    MaterialSeed("zinc_alloy", "Сплав на основі цинку", "Zinc-based alloy"),
    MaterialSeed("not_specified", "Не вказано", "Not specified"),
    MaterialSeed("other_banknote", "Інший (банкнота)", "Other (banknote)"),
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

# Kept for migration 0007, which imports this name to reword bare metals that
# predate "silver"/"gold" becoming dictionary codes in their own right
# (2026-09-12) — a fresh replay resolves them through `MATERIAL_CODES` before
# this ever runs, so it is dead weight today, not a live translation path.
BARE_METAL_WORDS: dict[str, str] = {"silver": "срібло", "gold": "золото"}

# Stale English tokens the confirmed (Ukrainian) catalogue carries in the
# free-text `material` column from before this dictionary covered every
# category the National Bank's own "Матеріал" filter offers (`NBU_METALS` in
# app/ukraine_pipeline/sources.py) -- an early run left them and nothing since
# has revisited an already-filled column (docs/09-data-migration.md). Most
# already spell a code exactly (`_composition_of` resolves those on its own);
# these are the ones that do not.
LEGACY_RAW_ALIASES: dict[str, str] = {
    "bimetallic": "bimetal",
    "bimetallic_precious": "bimetal",
    "cupronickel": "copper_nickel",
    "banknote": "other_banknote",
}

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
    # A dictionary code standing in for the alloy's name: no coin catalogue
    # writes "nickel_silver", so an exact match is our own token coming back.
    if normalised in MATERIAL_CODES:
        return normalised
    if normalised in LEGACY_RAW_ALIASES:
        return LEGACY_RAW_ALIASES[normalised]
    precious = _PRECIOUS_RE.search(normalised)
    if precious is not None:
        # Fineness is not part of the dictionary (see MATERIALS above): a
        # stated "0.925" still just means the plain metal, gilded or not.
        metal = _PRECIOUS_METAL[precious.group("metal")]
        return f"{metal}_gilded" if precious.group("gilded") else metal
    return next((code for phrase, code in _PHRASE_INDEX if normalised.endswith(phrase)), None)


def plain_material(text: str | None) -> str | None:
    """Free-text material as it should be stored: nothing, or real wording.

    Only for text the parser could not resolve to a dictionary row -- kept
    exactly as the source wrote it.
    """
    stripped = (text or "").strip()
    return stripped or None


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
