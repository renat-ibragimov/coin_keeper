"""Title normalisation and the matching key.

The normalisation is the one docs/05-integrations.md prescribes for UA-Coins
(lower case, NFKD, punctuation stripped, whitespace collapsed); every source
and our own catalogue go through the same function, so the key is comparable
across them.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

# Characters removed by the legacy normaliser (docs/05-integrations.md, section 4).
_PUNCTUATION = "’'`\"«»()[]{}.,:;!?–—-"
_PUNCTUATION_RE = re.compile("[" + re.escape(_PUNCTUATION) + "]")
_SPACES_RE = re.compile(r"\s+")
# Thin, non-breaking and narrow spaces that sites put inside numbers.
_NUMBER_JUNK_RE = re.compile(r"[\s   ]+")
_FIRST_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_DATE_RE = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4})")
# NBU appends a metal marker to titles: "(c)" silver, "(н)" nickel silver.
_NBU_SUFFIX_RE = re.compile(r"\s*\([a-zа-яіїєґ]{1,2}\)\s*$", re.IGNORECASE)
# A coin sold in packaging is the same coin; the NBU lists recent base-metal
# issues only that way.
_PACKAGING_RE = re.compile(
    r"\s*\(?\s*(?:у|в)\s+сувенірн(?:ому|ій)\s+(?:пакованні|упаковці)\s*\)?"
    r"|\s*\(?\s*в\s+сувенирной\s+упаковке\s*\)?",
    re.IGNORECASE,
)
# Latin letters typed inside Cyrillic words ("УHР", "рокiв"): the sites have
# them, and they break equality. Mapped when a Cyrillic letter is adjacent.
_HOMOGLYPHS = str.maketrans("aceiopxyhkmtb", "асеіорхункмтв")
_CYRILLIC = "а-яіїєґ"
_LATIN_IN_CYRILLIC_RE = re.compile(
    f"(?<=[{_CYRILLIC}])[aceiopxyhkmtb]|[aceiopxyhkmtb](?=[{_CYRILLIC}])"
)
_HOMOGLYPHS_UPPER = str.maketrans("ACEIOPXYHKMTB", "АСЕІОРХУНКМТВ")
_CYRILLIC_UPPER = "А-ЯІЇЄҐ"
_LATIN_IN_CYRILLIC_UPPER_RE = re.compile(
    f"(?<=[{_CYRILLIC_UPPER}])[ACEIOPXYHKMTB]|[ACEIOPXYHKMTB](?=[{_CYRILLIC_UPPER}])"
)


def fix_homoglyphs(value: str) -> str:
    """Latin letters typed inside a Cyrillic word, put back.

    The NBU writes "рокiв" and "УHР" with a Latin i and H. It is the same
    word; a search for "років" should find it. Only a Latin letter with a
    Cyrillic neighbour is touched, so "Морський дрон \"Sea Baby\"" is left
    exactly as it is.
    """
    lower = _LATIN_IN_CYRILLIC_RE.sub(lambda m: m.group(0).translate(_HOMOGLYPHS), value)
    return _LATIN_IN_CYRILLIC_UPPER_RE.sub(lambda m: m.group(0).translate(_HOMOGLYPHS_UPPER), lower)


def normalize_title(value: str) -> str:
    """Lower case, NFKD, punctuation to spaces, whitespace collapsed."""
    text = value.casefold()
    text = _LATIN_IN_CYRILLIC_RE.sub(lambda m: m.group(0).translate(_HOMOGLYPHS), text)
    text = unicodedata.normalize("NFKD", text)
    text = _PUNCTUATION_RE.sub(" ", text)
    return _SPACES_RE.sub(" ", text).strip()


def strip_source_suffix(value: str) -> str:
    """Drop the NBU metal marker ("... (c)") that no other source carries."""
    return _NBU_SUFFIX_RE.sub("", value).strip()


def strip_packaging(value: str) -> str:
    """ "Українська мова у сувенірному пакованні" is the coin "Українська мова"."""
    return _PACKAGING_RE.sub("", value).strip()


def bare_title(value: str) -> str:
    """Without the NBU marker and without the packaging phrase."""
    return strip_packaging(strip_source_suffix(value))


def titles_equivalent(left: str, right: str) -> bool:
    """The legacy rule: equal, or one is the other plus a space and more."""
    if not left or not right:
        return False
    return left == right or left.startswith(right + " ") or right.startswith(left + " ")


def denomination_value(value: str | None) -> Decimal | None:
    """First number in the text, comma accepted as the decimal separator."""
    if not value:
        return None
    match = _FIRST_NUMBER_RE.search(_NUMBER_JUNK_RE.sub("", value))
    if match is None:
        return None
    try:
        return Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:
        return None


def denomination_currency(value: str | None) -> str:
    """UAH unless the text says karbovanets (the 1995-1996 issues)."""
    if value and re.search(r"крб|карбован", value, re.IGNORECASE):
        return "UAK"
    return "UAH"


def parse_int(value: str | None) -> int | None:
    """An integer with thousands separators of any kind, or None."""
    if not value:
        return None
    digits = re.search(r"\d[\d\s   ]*", value)
    if digits is None:
        return None
    cleaned = _NUMBER_JUNK_RE.sub("", digits.group(0))
    return int(cleaned) if cleaned else None


def parse_mintage(value: str | None, *, thousands: bool = False) -> tuple[int | None, int | None]:
    """ "75/50" is announced/actual; a single number is announced only.

    ua-coins lists mintage in thousands, the NBU in pieces.
    """
    if not value:
        return None, None
    parts = [parse_int(part) for part in value.split("/", 1)]
    scale = 1000 if thousands else 1
    announced = parts[0] * scale if parts[0] is not None else None
    actual = parts[1] * scale if len(parts) > 1 and parts[1] is not None else None
    return announced, actual


def parse_date(value: str | None) -> date | None:
    """dd.mm.yyyy or dd.mm.yy (Wikipedia writes 26.11.96)."""
    if not value:
        return None
    match = _DATE_RE.search(value)
    if match is None:
        return None
    day, month, year = (int(part) for part in match.groups())
    if year < 100:
        year += 1900 if year >= 90 else 2000
    try:
        return date(year, month, day)
    except ValueError:
        return None


def match_key(denomination: Decimal | None, year: int | None, title: str) -> str:
    """Denomination + year + normalised title, the key of the whole reconnaissance."""
    value = "?" if denomination is None else format(denomination.normalize(), "f")
    return f"{value}|{year if year is not None else '?'}|{normalize_title(title)}"


_SET_RE = re.compile(r"\b(набір|набор|set)\b", re.IGNORECASE)
_SOUVENIR_RE = re.compile(
    r"сувенірн|сувенирн|пакованн|упаковк|ролик|футляр|буклет|souvenir",
    re.IGNORECASE,
)


def classify_kind(title: str) -> str:
    """coin, set or souvenir. Only coins take part in the year comparison.

    The NBU and ua-coins list a coin in souvenir packaging as a separate
    product; Wikipedia lists the coin once. Counting those rows as coins
    would make the sources disagree for no real reason.
    """
    if _SET_RE.search(title):
        return "set"
    if _SOUVENIR_RE.search(title):
        return "souvenir"
    return "coin"
