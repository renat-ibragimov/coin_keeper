"""circ-reclassify — moving NBU-linked catalogue entries out of circulation.

`collection_group = 'circulation'` for Ukraine is not clean: the legacy Excel
import heuristic `groupFor` (docs/04-business-rules.md, rule 11) sorted every
coin whose face value was not "hryvnia >= 2" into circulation, whatever it
actually was. That caught real commemoratives — the jubilee 1-hryvnia coins
(2004-2016, face value exactly 1) and the 1995-1996 karbovanets commemoratives
(a different currency, no "hryvnia" in the value at all) — and left them
sitting among ordinary kopiika and hryvnia records ever since.

The fix does not re-derive groupFor's guess. It asks a source that actually
knows: the NBU numismatic catalogue (app/ukraine_recon/nbu.py, part B of the
pipeline) already links these same records, either through a
price_source_links row or a "nbu:<card id>" source_key
(OurItem.is_nbu_linked, app/ukraine_pipeline/catalog.py). A circulation record
the catalogue already references cannot be an ordinary circulation coin —
whatever groupFor guessed — so it moves to `collection_group='commemorative'`
and nothing else about it changes: title, series and links are the
catalogue's or a person's work, not this step's to touch.

Idempotent for free: once a record is `commemorative`, the next catalogue
reload (Runner._load_catalog) no longer offers it to `decide()`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem
from app.models.enums import CollectionGroup, TranslationSource
from app.ukraine_pipeline.catalog import OurItem


@dataclass
class ReclassifyOutcome:
    reclassified: list[dict[str, Any]] = field(default_factory=list)
    # Circulation records with an official title but no NBU link at all —
    # not moved, just surfaced: could be an honest circulation coin whose
    # name circ-titles already set to `official`, or a commemorative the
    # catalogue link is missing. Worth a person's look, not a guess here.
    official_without_nbu_link: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "reclassified": len(self.reclassified),
            "officialWithoutNbuLink": len(self.official_without_nbu_link),
        }


def decide(items: list[OurItem]) -> ReclassifyOutcome:
    outcome = ReclassifyOutcome()
    for item in items:
        if item.is_archived or item.collection_group != CollectionGroup.CIRCULATION:
            continue
        row = {"itemId": item.id, "title": item.title_original, "year": item.issue_year}
        if item.is_nbu_linked:
            outcome.reclassified.append(row)
        elif item.title_uk_source == TranslationSource.OFFICIAL:
            outcome.official_without_nbu_link.append(row)
    return outcome


async def apply_reclassify(
    session: AsyncSession, *, items: list[OurItem], dry_run: bool
) -> ReclassifyOutcome:
    outcome = decide(items)
    if not dry_run and outcome.reclassified:
        ids = [row["itemId"] for row in outcome.reclassified]
        await session.execute(
            update(CatalogItem)
            .where(CatalogItem.id.in_(ids))
            .values(collection_group=CollectionGroup.COMMEMORATIVE)
        )
        await session.flush()
    return outcome
