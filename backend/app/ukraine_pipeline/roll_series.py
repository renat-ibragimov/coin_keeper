"""roll-series — series for circulation-commemorative rolls the series step cannot see.

app/ukraine_pipeline/series.py canonicalises our series names against the
National Bank's own wording (app/ukraine_recon/series_map.json), read off an
NBU numismatic card's `series` field. A circulation-commemorative roll card
carries no such field: app/ukraine_pipeline/sources.py:roll_coin sets
`series=None` on purpose, because the text the souvenir listing does carry is
the roll's own category ("Сувенірна продукція"), not the coin's real series —
series_map.json's own entry for that category says as much. gaps.py will not
create a record from a roll cluster either (no metal, no series on the card),
so "Ми сильні. Ми разом. <область>" only ever entered the catalogue by hand,
series included.

Nothing here discovers the series name: it copies series_id off whichever
"Ми сильні. Ми разом.%" record already carries one — set by a person, once —
onto every sibling record still missing it, so a newly catalogued oblast only
needs its own record, not a repeat of that manual SQL.

Idempotent by construction: only a NULL series_id row is a candidate, so a
second run has nothing left to touch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem

TITLE_PREFIX = "Ми сильні. Ми разом."


@dataclass
class RollSeriesOutcome:
    series_id: int | None = None
    updated: list[dict[str, Any]] = field(default_factory=list)
    problem: str | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "seriesId": self.series_id,
            "updated": len(self.updated),
            "problem": self.problem,
        }


async def backfill_series(
    session: AsyncSession,
    *,
    country_id: int,
    dry_run: bool,
    title_prefix: str = TITLE_PREFIX,
) -> RollSeriesOutcome:
    """Give every unlinked "<title_prefix>%" record the series its siblings already have."""
    outcome = RollSeriesOutcome()
    like_pattern = f"{title_prefix}%"
    series_id = (
        await session.execute(
            select(CatalogItem.series_id)
            .where(
                CatalogItem.country_id == country_id,
                CatalogItem.created_by.is_(None),
                CatalogItem.title_original.like(like_pattern),
                CatalogItem.series_id.is_not(None),
            )
            .order_by(CatalogItem.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if series_id is None:
        outcome.problem = (
            f"no existing {title_prefix!r} record carries a series_id yet; nothing to copy"
        )
        return outcome
    outcome.series_id = series_id

    rows = (
        await session.execute(
            select(CatalogItem.id, CatalogItem.title_original)
            .where(
                CatalogItem.country_id == country_id,
                CatalogItem.created_by.is_(None),
                CatalogItem.title_original.like(like_pattern),
                CatalogItem.series_id.is_(None),
            )
            .order_by(CatalogItem.id)
        )
    ).all()
    outcome.updated = [{"itemId": item_id, "title": title} for item_id, title in rows]
    if not dry_run and outcome.updated:
        ids = [row["itemId"] for row in outcome.updated]
        await session.execute(
            update(CatalogItem).where(CatalogItem.id.in_(ids)).values(series_id=series_id)
        )
        await session.flush()
    return outcome
