"""circ-mintage — the mintage of a circulation coin's own year.

The Wikipedia table (app/ukraine_recon/wikipedia.py:parse_mintage_table) is
indexed by exactly (face value, unit, year), the same key circ-bridge already
uses, so every active circulation record with a known denomination is looked
up directly — no link needed first. Only mintage_actual is written, and only
where it is empty: a figure already there, from the legacy migration or a
person, is trusted over the table, and a real disagreement is reported rather
than silently overwritten (docs/04-business-rules.md, rule 7).
mintage_announced is not this step's to touch — the table gives one number,
not an announced/actual pair.

The one cell that can name two numbers is the 2018 hryvnia changeover
("140 млн***** 20 тис****", both patterns struck the same year): its two
entries carry the marker that says which — **** the 2001 pattern, *****
2018 — and are picked by the record's own `subtype`
(app/ukraine_pipeline/circ_types.py). A record with no subtype set, or a cell
whose two numbers cannot be told apart this way, goes to `ambiguous` rather
than a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Denomination
from app.models.enums import CollectionGroup
from app.ukraine_pipeline.circ_types import SUBTYPE_1992, SUBTYPE_2018
from app.ukraine_recon.wikipedia import PATTERN_2001, PATTERN_2018, MintageCell

_PATTERN_BY_SUBTYPE = {SUBTYPE_1992: PATTERN_2001, SUBTYPE_2018: PATTERN_2018}


@dataclass
class MintageOutcome:
    updated: int = 0
    unchanged: int = 0
    no_wikipedia_cell: int = 0
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    discrepancies: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "updated": self.updated,
            "unchanged": self.unchanged,
            "noWikipediaCell": self.no_wikipedia_cell,
            "ambiguous": len(self.ambiguous),
            "discrepancies": len(self.discrepancies),
        }


def usable_count(cell: MintageCell, *, subtype: str | None) -> tuple[int | None, bool]:
    """(count, ambiguous) — count is None when the cell gives nothing to write.

    A cell with one countable entry is unambiguous regardless of its markers:
    a trial or collector-set-only mintage is still the real number the table
    prints for that year. Only a cell with more than one countable entry
    needs the record's subtype to say which is meant.
    """
    usable = [entry for entry in cell.entries if entry.count]
    if not usable:
        return None, False
    if len(usable) == 1:
        return usable[0].count, False
    wanted = _PATTERN_BY_SUBTYPE.get(subtype or "")
    matches = [entry for entry in usable if entry.pattern == wanted] if wanted else []
    if len(matches) == 1:
        return matches[0].count, False
    return None, True


async def apply_mintage(
    session: AsyncSession, *, country_id: int, mintage: list[MintageCell], dry_run: bool
) -> MintageOutcome:
    outcome = MintageOutcome()
    index: dict[tuple[Decimal, str, int], MintageCell] = {
        (cell.value, cell.unit, cell.year): cell for cell in mintage
    }

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

    for item, value, unit in rows:
        cell = index.get((value, unit, item.issue_year))
        if cell is None:
            outcome.no_wikipedia_cell += 1
            continue
        count, ambiguous = usable_count(cell, subtype=item.subtype)
        if ambiguous:
            outcome.ambiguous.append(
                {"itemId": item.id, "year": item.issue_year, "denomination": f"{value} {unit}"}
            )
            continue
        if count is None:
            outcome.unchanged += 1
            continue
        if item.mintage_actual is not None:
            if item.mintage_actual != count:
                outcome.discrepancies.append(
                    {"itemId": item.id, "existing": item.mintage_actual, "wikipedia": count}
                )
            outcome.unchanged += 1
            continue

        outcome.updated += 1
        if dry_run:
            continue
        item.mintage_actual = count

    if not dry_run:
        await session.flush()
    return outcome
