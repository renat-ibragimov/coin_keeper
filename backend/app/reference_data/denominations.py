"""Denominations as structure rather than as a string.

The legacy database stored a denomination as one Russian label ("5 копеек",
"200.000 карбованцев", "¼ доллара"). A label cannot be shown in another
language and cannot be sorted, so it is parsed once, in migration 0003, into
value + unit + currency, and the label is rendered per locale from there.

Plural rules are the CLDR ones: Ukrainian has one/few/many plus a form for
fractional amounts ("¼ долара"), English has one/other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

UAH = "UAH"
UAK = "UAK"
SUR = "SUR"
USD = "USD"

# Currencies the legacy catalogue needs that the initial migration did not
# create: the 1992-1996 karbovanets and the Soviet ruble.
EXTRA_CURRENCIES = (
    (UAK, "Ukrainian karbovanets", "крб", 0),
    (SUR, "Soviet ruble", "руб", 2),
)

LOCALE_UK = "uk"
LOCALE_EN = "en"

# Ukrainian groups thousands with a non-breaking space, English with a comma.
_UK_GROUP_SEPARATOR = " "


@dataclass(frozen=True, slots=True)
class Unit:
    """One denomination unit and everything needed to render and sort it.

    `minor_units` is what one of this unit is worth in the smallest unit of
    its currency: it is the sort key, and it is what turns "50 копійок" and
    "1 гривня" into comparable numbers.
    """

    code: str
    currency_code: str
    minor_units: Decimal
    # CLDR plural forms: Ukrainian one / few / many / other, English one / other.
    uk: tuple[str, str, str, str]
    en: tuple[str, str]


UNITS: dict[str, Unit] = {
    "kopiika": Unit(
        "kopiika",
        UAH,
        Decimal(1),
        ("копійка", "копійки", "копійок", "копійки"),
        ("kopiika", "kopiikas"),
    ),
    "hryvnia": Unit(
        "hryvnia",
        UAH,
        Decimal(100),
        ("гривня", "гривні", "гривень", "гривні"),
        ("hryvnia", "hryvnias"),
    ),
    "karbovanets": Unit(
        "karbovanets",
        UAK,
        Decimal(100),
        ("карбованець", "карбованці", "карбованців", "карбованця"),
        ("karbovanets", "karbovantsi"),
    ),
    "kopeck": Unit(
        "kopeck",
        SUR,
        Decimal(1),
        ("копійка", "копійки", "копійок", "копійки"),
        ("kopeck", "kopecks"),
    ),
    "poltinnik": Unit(
        "poltinnik",
        SUR,
        Decimal(50),
        ("полтинник", "полтинники", "полтинників", "полтинника"),
        ("poltinnik", "poltinniks"),
    ),
    "ruble": Unit(
        "ruble",
        SUR,
        Decimal(100),
        ("рубль", "рублі", "рублів", "рубля"),
        ("ruble", "rubles"),
    ),
    "chervonets": Unit(
        "chervonets",
        SUR,
        Decimal(1000),
        ("червінець", "червінці", "червінців", "червінця"),
        ("chervonets", "chervontsy"),
    ),
    "cent": Unit(
        "cent",
        USD,
        Decimal(1),
        ("цент", "центи", "центів", "цента"),
        ("cent", "cents"),
    ),
    "dime": Unit(
        "dime",
        USD,
        Decimal(10),
        ("дайм", "дайми", "даймів", "дайма"),
        ("dime", "dimes"),
    ),
    "dollar": Unit(
        "dollar",
        USD,
        Decimal(100),
        ("долар", "долари", "доларів", "долара"),
        ("dollar", "dollars"),
    ),
}

# Ukrainian also calls the Soviet ruble "карбованець", which is the name of the
# 1992-1996 Ukrainian currency as well. The unit here stays "рубль" on purpose:
# two units rendering to the same word would make the two currencies
# indistinguishable in a list.

_UNKNOWN_UNIT = "unknown"

# Word stems, matched as a prefix of the unit word. Order matters only in that
# no stem here is a prefix of another.
_UNIT_STEMS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("цент", "cent"), "cent"),
    (("дайм", "dime"), "dime"),
    (("доллар", "долар", "dollar"), "dollar"),
    (("гривн", "гривен", "гривень", "гривня", "гривні", "hryvn"), "hryvnia"),
    (("карбован", "krb", "крб", "karbovan"), "karbovanets"),
    (("полтинник", "poltinnik"), "poltinnik"),
    (("червон", "червін", "chervon"), "chervonets"),
    (("рубл", "ruble", "rouble"), "ruble"),
    (("копе", "копі", "kope", "kopi"), "kopeck"),
)

_VULGAR_FRACTIONS = {
    "¼": Decimal("0.25"),
    "½": Decimal("0.5"),
    "¾": Decimal("0.75"),
    "⅓": Decimal("1") / Decimal(3),
    "⅔": Decimal("2") / Decimal(3),
    "⅛": Decimal("0.125"),
}
_VULGAR_BY_VALUE = {
    Decimal("0.25"): "¼",
    Decimal("0.5"): "½",
    Decimal("0.75"): "¾",
    Decimal("0.125"): "⅛",
}

_LABEL_RE = re.compile(
    r"^\s*(?P<number>[\d\s.,  ]*)(?P<fraction>[¼½¾⅓⅔⅛])?\s*(?P<word>[^\d]+?)\s*$"
)
# "200.000" and "1.000.000" are thousands separators, not a decimal point.
_GROUPED_RE = re.compile(r"^\d{1,3}(\.\d{3})+$")


class DenominationParseError(ValueError):
    """The label does not describe a denomination we can represent."""


@dataclass(frozen=True, slots=True)
class ParsedDenomination:
    value: Decimal
    unit: str
    currency_code: str

    @property
    def minor_units(self) -> int:
        """The face value in the currency's smallest unit — the sort key."""
        return int(self.value * UNITS[self.unit].minor_units)


def parse_label(label: str, *, country_code: str | None = None) -> ParsedDenomination:
    """Turn "5 копеек" into (5, kopeck, SUR). Raises when it cannot.

    `country_code` decides between the two coins spelled the same way: the
    Ukrainian копійка and the Soviet копейка. Everything else is unambiguous.
    """
    match = _LABEL_RE.match(label)
    if match is None:
        msg = f"cannot read {label!r} as a denomination"
        raise DenominationParseError(msg)

    value = _parse_number(match.group("number"), match.group("fraction"), label)
    unit = _parse_unit(match.group("word"), country_code)
    return ParsedDenomination(value=value, unit=unit, currency_code=UNITS[unit].currency_code)


def _parse_number(number: str | None, fraction: str | None, label: str) -> Decimal:
    text = re.sub(r"[\s  ]", "", number or "")
    whole = Decimal(0)
    if text:
        if _GROUPED_RE.match(text):
            text = text.replace(".", "")
        elif "." in text or "," in text:
            msg = f"cannot read the number in {label!r}"
            raise DenominationParseError(msg)
        try:
            whole = Decimal(text)
        except InvalidOperation as exc:
            msg = f"cannot read the number in {label!r}"
            raise DenominationParseError(msg) from exc
    value = whole + (_VULGAR_FRACTIONS[fraction] if fraction else Decimal(0))
    if value <= 0:
        msg = f"a denomination must be positive: {label!r}"
        raise DenominationParseError(msg)
    return value


def _parse_unit(word: str, country_code: str | None) -> str:
    candidate = word.strip().casefold().replace("ё", "е")
    for stems, unit in _UNIT_STEMS:
        if any(candidate.startswith(stem) for stem in stems):
            if unit == "kopeck" and country_code in ("UA", "XUNR"):
                return "kopiika"
            return unit
    msg = f"unknown denomination unit {word.strip()!r}"
    raise DenominationParseError(msg)


# ------------------------------------------------------------------- rendering
def render_label(value: Decimal, unit: str, locale: str) -> str:
    """The denomination as the locale writes it: "5 копійок", "5 kopecks"."""
    known = UNITS.get(unit)
    if known is None:
        return format_number(value, locale)
    word = _uk_form(known, value) if locale == LOCALE_UK else _en_form(known, value)
    return f"{format_number(value, locale)} {word}"


def format_number(value: Decimal, locale: str) -> str:
    """Grouped integer, with ¼ ½ ¾ written as the glyph the labels used."""
    whole = int(value)
    remainder = value - whole
    glyph = _VULGAR_BY_VALUE.get(remainder.normalize()) if remainder else None
    if remainder and glyph is None:
        # Not one of the coin fractions; write it out rather than lose it.
        text = format(value.normalize(), "f")
        return text.replace(".", ",") if locale == LOCALE_UK else text
    grouped = _group(whole, locale) if whole or glyph is None else ""
    return f"{grouped}{glyph or ''}"


def _group(whole: int, locale: str) -> str:
    separator = _UK_GROUP_SEPARATOR if locale == LOCALE_UK else ","
    return f"{whole:,}".replace(",", separator)


def _uk_form(unit: Unit, value: Decimal) -> str:
    """CLDR plural categories for Ukrainian: one, few, many, other."""
    if value != int(value):
        return unit.uk[3]
    whole = int(value)
    if whole % 10 == 1 and whole % 100 != 11:
        return unit.uk[0]
    if whole % 10 in (2, 3, 4) and whole % 100 not in (12, 13, 14):
        return unit.uk[1]
    return unit.uk[2]


def _en_form(unit: Unit, value: Decimal) -> str:
    return unit.en[0] if value == 1 else unit.en[1]
