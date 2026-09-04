"""circ-titles — the official name of every circulation coin.

A circulation coin's name *is* its denomination — "1 копійка", "5 гривень" —
there is no design title the way a commemorative has one. That name is
already computed correctly everywhere the API renders a denomination
(app.reference_data.denominations.render_label, the CLDR plural rules the
handoff asked this step to hardcode a map for): reusing it rather than
re-deriving the same declension table here is what keeps "1 копійка" /
"25 копійок" right without a second place that can drift from the first.

`render_label` is also how title_en is built: "hryvnia" / "kopiika" are the
standard transliterations, not this pipeline's invention, so both slots are
marked `official` — the same status app/ukraine_pipeline/titles.py gives a
name the National Bank itself published. A human correction is the only
thing this step will not overwrite: a title (or just its English slot)
already marked `manual` is left exactly as it is, checked independently
because either slot can be corrected on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Denomination
from app.models.enums import CollectionGroup, TranslationSource
from app.reference_data.denominations import UNITS, render_label
from app.ukraine_pipeline.catalog import nbu_linked_ids


def title_uk(value: Decimal, unit: str) -> str:
    return render_label(value, unit, "uk")


def title_en(value: Decimal, unit: str) -> str:
    return render_label(value, unit, "en")


@dataclass
class TitlesOutcome:
    updated: int = 0
    unchanged: int = 0
    skipped_unknown_unit: int = 0
    skipped_nbu_linked: int = 0
    examples: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skippedUnknownUnit": self.skipped_unknown_unit,
            "skippedNbuLinked": self.skipped_nbu_linked,
        }


async def apply_titles(session: AsyncSession, *, country_id: int, dry_run: bool) -> TitlesOutcome:
    outcome = TitlesOutcome()
    rows = (
        await session.execute(
            select(CatalogItem, Denomination.value, Denomination.unit)
            .join(Denomination, Denomination.id == CatalogItem.denomination_id)
            .where(
                CatalogItem.country_id == country_id,
                CatalogItem.created_by.is_(None),
                CatalogItem.is_archived.is_(False),
                CatalogItem.collection_group == CollectionGroup.CIRCULATION,
            )
        )
    ).all()
    nbu_ids = await nbu_linked_ids(session, [item.id for item, _value, _unit in rows])

    for item, value, unit in rows:
        if item.id in nbu_ids:
            outcome.skipped_nbu_linked += 1
            continue
        if unit not in UNITS:
            outcome.skipped_unknown_unit += 1
            continue
        new_uk = title_uk(value, unit)
        new_en = title_en(value, unit)
        touch_uk = item.title_uk_source != TranslationSource.MANUAL
        touch_en = item.title_en_source != TranslationSource.MANUAL

        changed_uk = touch_uk and (item.title_original != new_uk or item.title_uk != new_uk)
        changed_en = touch_en and item.title_en != new_en
        if not changed_uk and not changed_en:
            outcome.unchanged += 1
            continue

        outcome.updated += 1
        if len(outcome.examples) < 15:
            outcome.examples.append({"itemId": item.id, "from": item.title_original, "to": new_uk})
        if dry_run:
            continue
        if changed_uk:
            item.title_original = new_uk
            item.original_lang = "uk"
            item.title_uk = new_uk
            item.title_uk_source = TranslationSource.OFFICIAL
        if changed_en:
            item.title_en = new_en
            item.title_en_source = TranslationSource.OFFICIAL

    if not dry_run:
        await session.flush()
    return outcome
