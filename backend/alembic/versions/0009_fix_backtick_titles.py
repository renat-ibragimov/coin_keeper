"""Fix backtick-corrupted quotation marks in catalog titles.

84 shared Ukrainian catalog items came out of the legacy migration (or a
later NBU pass) with a stray ASCII backtick standing in for a proper
Ukrainian quotation mark, in `title_original`/`title_uk` and sometimes
`title_en` too: "Криголам `Капітан Бєлоусов`" instead of
"Криголам «Капітан Бєлоусов»". 12 of them also corrupted `title_en` with a
backtick or a mismatched curly quote ("AN-225 `Mria'aircraft").

The fix data lives in the sibling `0009_fix_backtick_titles.json` (long
Ukrainian strings read better as data than as a Python literal): each entry
gives the row's `id` and, where that field changed, `old_title`/`new_title`
and `old_title_en`/`new_title_en` — captured straight from production so the
downgrade can put the exact original text back.

Five records had a *third*, spurious backtick with no partner (e.g.
"Пам'ятна медаль `Національний університет `Львівська політехніка`") --
resolved by dropping the extra mark rather than guessing a nesting, by
analogy with clean sibling records of the same shape elsewhere in the
catalogue. One record's quoted phrase opened the title itself; converting it
would have put a "«" ahead of the Cyrillic alphabet on the title sort, so its
quotes are dropped entirely instead of converted (owner's call, 2026-09-12).
The English side otherwise drops the marks rather than converting them,
matching how the rest of the catalogue's English titles read (no quotes
around a proper name at all).

`title_uk_source`/`title_en_source` move to 'manual' on every row touched,
the same as an admin edit through `PATCH /catalog/{id}` would record.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-12
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FIXTURE_PATH = Path(__file__).with_name("0009_fix_backtick_titles.json")


def _entries() -> list[dict[str, object]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


_SET_NEW_TITLE = sa.text(
    "UPDATE catalog_items SET title_original = :new_title, title_uk = :new_title, "
    "title_uk_source = 'manual' WHERE id = :id"
)
_SET_NEW_TITLE_EN = sa.text(
    "UPDATE catalog_items SET title_en = :new_title_en, title_en_source = 'manual' WHERE id = :id"
)
_SET_OLD_TITLE = sa.text(
    "UPDATE catalog_items SET title_original = :old_title, title_uk = :old_title WHERE id = :id"
)
_SET_OLD_TITLE_EN = sa.text("UPDATE catalog_items SET title_en = :old_title_en WHERE id = :id")


def upgrade() -> None:
    connection = op.get_bind()
    for entry in _entries():
        if "new_title" in entry:
            connection.execute(_SET_NEW_TITLE, {"id": entry["id"], "new_title": entry["new_title"]})
        if "new_title_en" in entry:
            connection.execute(
                _SET_NEW_TITLE_EN, {"id": entry["id"], "new_title_en": entry["new_title_en"]}
            )


def downgrade() -> None:
    connection = op.get_bind()
    for entry in _entries():
        if "old_title" in entry:
            connection.execute(_SET_OLD_TITLE, {"id": entry["id"], "old_title": entry["old_title"]})
        if "old_title_en" in entry:
            connection.execute(
                _SET_OLD_TITLE_EN, {"id": entry["id"], "old_title_en": entry["old_title_en"]}
            )
