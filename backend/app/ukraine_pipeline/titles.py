"""titles — the official name of every linked coin.

The National Bank issues the coin, so the National Bank's wording is the name:
`title_original` and `title_uk` both take it, with the metal marker ("(с)",
"(н)") and the packaging phrase stripped, and `title_en` comes from the English
side of the same card. Both translated slots are marked `official`, because
nothing was translated — both were published by the issuer.

Wikipedia is used as a check, not as a source: where it disagrees beyond
quotation marks the pair goes into the report for a person to look at. The old
Russian name is not kept anywhere. There is no Russian slot, and the original
is now Ukrainian.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem
from app.models.enums import TranslationSource
from app.ukraine_pipeline.lexicon import Lexicon
from app.ukraine_pipeline.sources import NbuEnglish, Sources, nbu_title
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_WIKIPEDIA
from app.ukraine_recon.normalize import bare_title, normalize_title
from app.ukraine_recon.triangulate import Cluster

# Below this the two sources are telling different stories about the coin.
WIKIPEDIA_AGREEMENT = 80.0
MAX_DISAGREEMENTS = 100


@dataclass
class TitlesOutcome:
    updated: int = 0
    unchanged: int = 0
    without_nbu: int = 0
    with_english: int = 0
    disagreements: list[dict[str, Any]] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "updated": self.updated,
            "unchanged": self.unchanged,
            "withoutNbuCard": self.without_nbu,
            "withEnglish": self.with_english,
            "wikipediaDisagreements": len(self.disagreements),
        }


def official_titles(
    cluster: Cluster, english: dict[str, NbuEnglish]
) -> tuple[str, str | None] | None:
    """(Ukrainian, English) as the NBU publishes them, or None without a card."""
    record = cluster.record_of(SOURCE_NBU)
    if record is None:
        return None
    title_uk = nbu_title(record)
    if not title_uk:
        return None
    card = english.get(record.source_id)
    title_en = card.title if card is not None and card.title else None
    return title_uk, title_en


def wikipedia_disagreement(
    cluster: Cluster, title_uk: str, lexicon: Lexicon
) -> dict[str, Any] | None:
    """Wikipedia's wording, when it is not the same name in other punctuation."""
    record = cluster.record_of(SOURCE_WIKIPEDIA)
    if record is None or not record.title_uk:
        return None
    theirs = bare_title(record.title_uk)
    if normalize_title(theirs) == normalize_title(title_uk):
        return None
    if lexicon.score(title_uk, theirs) >= WIKIPEDIA_AGREEMENT:
        return None
    return {"nbu": title_uk, "wikipedia": theirs, "year": cluster.year}


async def apply_titles(
    session: AsyncSession,
    *,
    pairs: dict[int, Cluster],
    sources: Sources,
    lexicon: Lexicon,
    dry_run: bool,
) -> TitlesOutcome:
    """`pairs` is {catalog item id: its cluster}, from the bridge step."""
    outcome = TitlesOutcome()
    if not pairs:
        return outcome
    items = {
        item.id: item
        for item in (
            await session.execute(select(CatalogItem).where(CatalogItem.id.in_(pairs)))
        ).scalars()
    }

    for item_id, cluster in pairs.items():
        item = items.get(item_id)
        if item is None:
            continue
        official = official_titles(cluster, sources.nbu_english)
        if official is None:
            outcome.without_nbu += 1
            continue
        title_uk, title_en = official

        disagreement = wikipedia_disagreement(cluster, title_uk, lexicon)
        if disagreement is not None and len(outcome.disagreements) < MAX_DISAGREEMENTS:
            outcome.disagreements.append({"itemId": item_id, **disagreement})

        changed = item.title_original != title_uk or item.title_uk != title_uk
        if title_en and item.title_en != title_en:
            changed = True
        if not changed:
            outcome.unchanged += 1
            continue
        if len(outcome.examples) < 10:
            outcome.examples.append(
                {"itemId": item_id, "from": item.title_original, "to": title_uk}
            )
        outcome.updated += 1
        if title_en:
            outcome.with_english += 1
        if dry_run:
            continue
        item.title_original = title_uk
        item.original_lang = "uk"
        item.title_uk = title_uk
        item.title_uk_source = TranslationSource.OFFICIAL
        if title_en:
            item.title_en = title_en
            item.title_en_source = TranslationSource.OFFICIAL
    if not dry_run:
        await session.flush()
    return outcome
