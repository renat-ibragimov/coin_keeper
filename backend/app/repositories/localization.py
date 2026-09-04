"""The locale rule as a SQL expression.

The same rule as app.core.locale.pick_name, written so it can also be sorted
and searched on: a listing ordered by country has to order by the name the
reader sees, not by the original.
"""

from __future__ import annotations

from sqlalchemy import ColumnElement, func
from sqlalchemy.sql import ColumnExpressionArgument

from app.core.locale import LOCALE_UK


def localized(
    locale: str,
    *,
    uk: ColumnExpressionArgument[str | None],
    en: ColumnExpressionArgument[str | None],
    original: ColumnExpressionArgument[str],
) -> ColumnElement[str]:
    translated = uk if locale == LOCALE_UK else en
    return func.coalesce(func.nullif(func.btrim(translated), ""), original)
