"""repair-gaps — filling in what an earlier run of the gaps step left empty.

The first version of `gaps` wrote a name, a year and little else: it read the
face value with a parser that did not know the National Bank writes "1 грн"
rather than "1 гривня", and it read the metal with a parser that knows the
Russian alloy names of uCoin and not the Ukrainian ones of the issuer. The 96
records it created came out with no denomination, no metal kind and, where the
card carried no tag, no series.

This step goes back over them by source key — every record it made carries
"nbu:<card id>" — and fills those columns from the same cluster the record was
made from, through the same `read_cluster` the creating step now uses.

**Only empty columns are written.** A value a person has since corrected stays:
the issuer is the source for a column nobody has filled, not an authority over
one somebody has. Running it twice changes nothing the second time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Material
from app.models.enums import MetalKind, TranslationSource
from app.ukraine_pipeline.gaps import (
    SOURCE_KEY_PREFIX,
    CoinFields,
    ensure_denomination,
    read_cluster,
)
from app.ukraine_pipeline.series import ensure_series, series_by_name
from app.ukraine_pipeline.sources import Sources
from app.ukraine_recon.models import SOURCE_NBU

MAX_EXAMPLES = 20
# Columns filled straight from the card, with nothing to look up first:
# our column name against the one the card was read into.
PLAIN_COLUMNS = (
    ("issue_date", "issue_date"),
    ("mintage_announced", "mintage"),
    ("mintage_actual", "mintage_actual"),
    ("weight_grams", "weight_grams"),
    ("diameter_mm", "diameter_mm"),
    ("edge", "edge"),
)


@dataclass
class RepairOutcome:
    examined: int = 0
    updated: int = 0
    unchanged: int = 0
    # column name -> how many records got it
    filled: dict[str, int] = field(default_factory=dict)
    # Source keys whose card the sources no longer carry: an issue withdrawn
    # from the catalogue, or a run narrowed by --since-year.
    without_card: list[str] = field(default_factory=list)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "examined": self.examined,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "filled": dict(sorted(self.filled.items())),
            "withoutCard": len(self.without_card),
        }


async def repair_gaps(
    session: AsyncSession,
    *,
    country_id: int,
    sources: Sources,
    dry_run: bool,
) -> RepairOutcome:
    outcome = RepairOutcome()
    items = (
        (
            await session.execute(
                select(CatalogItem).where(
                    CatalogItem.country_id == country_id,
                    CatalogItem.created_by.is_(None),
                    CatalogItem.source_key.like(f"{SOURCE_KEY_PREFIX}%"),
                )
            )
        )
        .scalars()
        .all()
    )
    if not items:
        return outcome
    materials = {
        code: material_id
        for material_id, code in (await session.execute(select(Material.id, Material.code))).all()
    }
    series_cache = await series_by_name(session, country_id)
    denomination_cache: dict[tuple[str, str, Decimal], int] = {}

    for item in items:
        outcome.examined += 1
        card_id = (item.source_key or "").removeprefix(SOURCE_KEY_PREFIX)
        cluster = sources.cluster_of(SOURCE_NBU, card_id)
        fields = read_cluster(cluster, sources.nbu_english) if cluster is not None else None
        if fields is None:
            outcome.without_card.append(item.source_key or "")
            continue

        filled = _fill_plain(item, fields)
        if item.denomination_id is None and fields.denomination is not None:
            item.denomination_id = await ensure_denomination(
                session,
                country_id=country_id,
                parsed=fields.denomination,
                cache=denomination_cache,
            )
            filled.append("denomination_id")
        if item.series_id is None and fields.series_uk:
            series = await ensure_series(
                session,
                country_id=country_id,
                name_uk=fields.series_uk,
                name_en=fields.series_en,
                cache=series_cache,
            )
            item.series_id = series.id
            filled.append("series_id")
        if item.composition_id is None and materials.get(fields.composition_code or ""):
            item.composition_id = materials[fields.composition_code or ""]
            filled.append("composition_id")

        if not filled:
            outcome.unchanged += 1
            continue
        outcome.updated += 1
        for column in filled:
            outcome.filled[column] = outcome.filled.get(column, 0) + 1
        if len(outcome.examples) < MAX_EXAMPLES:
            outcome.examples.append(
                {"itemId": item.id, "sourceKey": item.source_key, "filled": filled}
            )

    if not dry_run:
        await session.flush()
    return outcome


def _fill_plain(item: CatalogItem, fields: CoinFields) -> list[str]:
    """The columns that need nothing looked up. Returns what was written."""
    filled: list[str] = []
    if item.metal_kind is MetalKind.UNKNOWN and fields.metal_kind is not MetalKind.UNKNOWN:
        item.metal_kind = fields.metal_kind
        filled.append("metal_kind")
    if item.material is None and fields.material:
        item.material = fields.material
        filled.append("material")
    if item.title_en is None and fields.title_en:
        item.title_en = fields.title_en
        item.title_en_source = TranslationSource.OFFICIAL
        filled.append("title_en")
    for column, attribute in PLAIN_COLUMNS:
        value = getattr(fields, attribute)
        if value is not None and getattr(item, column) is None:
            setattr(item, column, value)
            filled.append(column)
    return filled
