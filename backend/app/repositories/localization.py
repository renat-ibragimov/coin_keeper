"""The locale rule as a SQL expression.

The same rule as app.core.locale.pick_name, written so it can also be sorted
and searched on: a listing ordered by country has to order by the name the
reader sees, not by the original.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func
from sqlalchemy.sql import ColumnExpressionArgument

from app.core.locale import LOCALE_UK

# Postgres's default collation sorts by raw code point, not by alphabet: the
# four Ukrainian-only letters (U+0404, U+0406, U+0407, U+0490) sit in a lower
# code point range than the rest of Cyrillic (which starts at U+0410), so a
# plain ORDER BY put every name starting with one of those letters ahead of
# the whole regular Cyrillic alphabet — right after digit-led names, well
# before names that should sort first — and left the rest looking sorted
# only within one starting letter. Postgres ships ICU collations built in (no
# OS locale data needed, confirmed present on this image via pg_collation):
# uk-x-icu and en-x-icu sort the way a reader of that language expects.
_ICU_COLLATION = {LOCALE_UK: "uk-x-icu", "en": "en-x-icu"}


def localized(
    locale: str,
    *,
    uk: ColumnExpressionArgument[str | None],
    en: ColumnExpressionArgument[str | None],
    original: ColumnExpressionArgument[str],
) -> ColumnElement[str]:
    translated = uk if locale == LOCALE_UK else en
    expr = func.coalesce(func.nullif(func.btrim(translated), ""), original)
    return expr.collate(_ICU_COLLATION.get(locale, "und-x-icu"))
