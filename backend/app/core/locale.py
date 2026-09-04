"""The two interface languages and how a name is chosen between them.

Interface locales are 'uk' and 'en', Ukrainian by default (CLAUDE.md). Every
named catalog entity carries three slots, and the rule is the same everywhere:
the slot for the requested locale, and the issuer's original when that slot is
empty. There is no Russian slot to fall back to — for the Soviet part of the
catalogue Russian *is* the original.
"""

from __future__ import annotations

from typing import Final

LOCALE_UK: Final = "uk"
LOCALE_EN: Final = "en"
LOCALES: Final = (LOCALE_UK, LOCALE_EN)
DEFAULT_LOCALE: Final = LOCALE_UK


def normalize_locale(value: str | None) -> str:
    """'uk-UA', 'UK', 'en-GB;q=0.9' and nonsense all resolve to a known locale."""
    if not value:
        return DEFAULT_LOCALE
    for part in value.split(","):
        tag = part.split(";", 1)[0].strip().lower()
        primary = tag.split("-", 1)[0]
        if primary in LOCALES:
            return primary
    return DEFAULT_LOCALE


def pick_name(locale: str, *, uk: str | None, en: str | None, original: str) -> str:
    """name_{locale} → name_original."""
    translated = uk if locale == LOCALE_UK else en
    if translated and translated.strip():
        return translated.strip()
    return original
