"""circ-gaps — circulation coins the sources confirm and we do not have.

Where app/ukraine_pipeline/gaps.py reads a coin off an NBU numismatic card,
this step reads one off a cell of the Wikipedia mintage table
(app/ukraine_recon/wikipedia.py:parse_mintage_table): every (face value,
unit, year) the table says a coin was struck for, and that none of our own
active circulation records already occupies, becomes a new shared record.
Material, mass, diameter, edge and the design's own name come from the type
map (app/ukraine_pipeline/circ_types.py) — the one place that turns a
(denomination, year) into physical facts, so a year outside every type's
range (nothing in Ukraine's circulation coinage before 1992) is reported
rather than guessed at.

Idempotent the same way app/ukraine_pipeline/gaps.py is: the source_key
("wiki-circ:<value>-<unit>:<year>") is unique among shared records by the
schema itself, so a second run of this step inserts nothing new. It is also
guarded against creating a duplicate of a record circ-bridge could not link
automatically — the check is "does an active record already occupy this
(value, unit, year) at all", not "is it linked yet" — a pair still sitting in
circ-bridge's review CSV must not be doubled by a fresh record from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Material
from app.models.enums import CollectionGroup, TranslationSource
from app.reference_data.denominations import UNITS, ParsedDenomination
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.circ_bridge import wikipedia_keys
from app.ukraine_pipeline.circ_titles import title_en, title_uk
from app.ukraine_pipeline.circ_types import CoinType, type_for
from app.ukraine_pipeline.gaps import ensure_denomination
from app.ukraine_recon.wikipedia import MintageCell

SOURCE_KEY_PREFIX = "wiki-circ:"


def source_key(value: Decimal, unit: str, year: int) -> str:
    return f"{SOURCE_KEY_PREFIX}{format(value.normalize(), 'f')}-{unit}:{year}"


@dataclass
class GapsOutcome:
    created: list[dict[str, Any]] = field(default_factory=list)
    skipped_existing: int = 0
    skipped_no_type: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "created": len(self.created),
            "skippedAlreadyPresent": self.skipped_existing,
            "skippedNoType": len(self.skipped_no_type),
        }


def _existing_slots(items: Sequence[OurItem]) -> set[tuple[Decimal, str, int]]:
    return {
        (item.denomination, item.denomination_unit, item.issue_year)
        for item in items
        if not item.is_archived
        and item.collection_group == CollectionGroup.CIRCULATION
        and item.denomination is not None
        and item.denomination_unit is not None
    }


def _build_item(
    *,
    country_id: int,
    coin_type: CoinType,
    value: Decimal,
    unit: str,
    year: int,
    denomination_id: int | None,
    composition_id: int | None,
) -> CatalogItem:
    name_uk = title_uk(value, unit)
    return CatalogItem(
        country_id=country_id,
        denomination_id=denomination_id,
        collection_group=CollectionGroup.CIRCULATION,
        subtype=coin_type.subtype,
        title_original=name_uk,
        original_lang="uk",
        title_uk=name_uk,
        title_uk_source=TranslationSource.OFFICIAL,
        title_en=title_en(value, unit),
        title_en_source=TranslationSource.OFFICIAL,
        issue_year=year,
        composition_id=composition_id,
        metal_kind=coin_type.metal_kind,
        weight_grams=coin_type.weight_grams,
        diameter_mm=coin_type.diameter_mm,
        thickness_mm=coin_type.thickness_mm,
        edge=coin_type.edge,
        source_key=source_key(value, unit, year),
        created_by=None,
    )


async def create_missing(
    session: AsyncSession,
    *,
    country_id: int,
    items: Sequence[OurItem],
    mintage: list[MintageCell],
    dry_run: bool,
) -> GapsOutcome:
    outcome = GapsOutcome()
    materials = {
        code: material_id
        for material_id, code in (await session.execute(select(Material.id, Material.code))).all()
    }
    denomination_cache: dict[tuple[str, str, Decimal], int] = {}
    existing_slots = _existing_slots(items)
    existing_keys = set(
        (
            await session.execute(
                select(CatalogItem.source_key).where(
                    CatalogItem.created_by.is_(None),
                    CatalogItem.source_key.like(f"{SOURCE_KEY_PREFIX}%"),
                )
            )
        )
        .scalars()
        .all()
    )

    for value, unit, year in sorted(wikipedia_keys(mintage)):
        if (value, unit, year) in existing_slots:
            outcome.skipped_existing += 1
            continue
        key = source_key(value, unit, year)
        if key in existing_keys:
            outcome.skipped_existing += 1
            continue
        coin_type = type_for(value, unit, year)
        if coin_type is None:
            outcome.skipped_no_type.append({"value": str(value), "unit": unit, "year": year})
            continue

        outcome.created.append(
            {
                "sourceKey": key,
                "title": title_uk(value, unit),
                "year": year,
                "subtype": coin_type.subtype,
            }
        )
        if not dry_run:
            denomination_id = await ensure_denomination(
                session,
                country_id=country_id,
                parsed=ParsedDenomination(
                    value=value, unit=unit, currency_code=UNITS[unit].currency_code
                ),
                cache=denomination_cache,
            )
            session.add(
                _build_item(
                    country_id=country_id,
                    coin_type=coin_type,
                    value=value,
                    unit=unit,
                    year=year,
                    denomination_id=denomination_id,
                    composition_id=materials.get(coin_type.composition_code or ""),
                )
            )
        existing_keys.add(key)

    if not dry_run:
        await session.flush()
    return outcome
