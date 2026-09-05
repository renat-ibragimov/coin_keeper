"""circ-mintage — the mintage of a circulation coin's own year.

The Wikipedia table (app/ukraine_recon/wikipedia.py:parse_mintage_table) is
indexed by exactly (face value, unit, year), the same key circ-bridge already
uses, so every active circulation record with a known denomination is looked
up directly — no link needed first. By default only mintage_actual is
written, and only where it is empty: a figure already there, from the legacy
migration or a person, is trusted over the table, and a real disagreement is
reported rather than silently overwritten (docs/04-business-rules.md, rule
7). `--circ-refresh-mintage` (the `refresh` argument to `apply_mintage`) is
the escape hatch: it recomputes and overwrites every non-NBU-linked record's
mintage_actual from the table instead of only filling empty ones, the same
shape as `circ_photos.refresh_types` — see its module docstring for why
overwriting what this step's own population already holds is safe.
mintage_announced is not this step's to touch — the table gives one number,
not an announced/actual pair.

parse_mintage_table can return more than one MintageCell for the same
(value, unit, year): 1992 is split across two mint-name sections on the live
page (Italian mint, Luhansk plant), each naming its own row for that year.
Entries from every such row are added together — two mints striking the same
denomination the same year are both real coins of that year, not
alternatives — including a trial or collector-set-only entry, which adds in
just like any other: the table's own number for that year, whatever its
markers say about who it was struck for. Only entries the table itself marks
as one of two competing *designs* sharing a year label are mutually
exclusive rather than additive: the 2018 hryvnia changeover
("140 млн***** 20 тис****") carries a marker — **** the 2001 pattern, *****
2018 — that a record's own `subtype` (app/ukraine_pipeline/circ_types.py)
picks between. A record with no subtype set, or a set of patterned entries
none of which its subtype names, goes to `ambiguous` rather than a guess —
nothing is written for it at all, even a plain total from another mint the
same year: the same "do not guess" rule the rest of this step follows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Denomination
from app.models.enums import CollectionGroup
from app.ukraine_pipeline.catalog import nbu_linked_ids
from app.ukraine_pipeline.circ_types import SUBTYPE_1992, SUBTYPE_2018
from app.ukraine_recon.wikipedia import PATTERN_2001, PATTERN_2018, MintageCell, MintageEntry

_PATTERN_BY_SUBTYPE = {SUBTYPE_1992: PATTERN_2001, SUBTYPE_2018: PATTERN_2018}


@dataclass
class MintageOutcome:
    updated: int = 0
    unchanged: int = 0
    no_wikipedia_cell: int = 0
    skipped_nbu_linked: int = 0
    ambiguous: list[dict[str, Any]] = field(default_factory=list)
    discrepancies: list[dict[str, Any]] = field(default_factory=list)
    refreshed: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "updated": self.updated,
            "unchanged": self.unchanged,
            "noWikipediaCell": self.no_wikipedia_cell,
            "skippedNbuLinked": self.skipped_nbu_linked,
            "ambiguous": len(self.ambiguous),
            "discrepancies": len(self.discrepancies),
            "refreshed": len(self.refreshed),
        }


def usable_count(
    entries: tuple[MintageEntry, ...], *, subtype: str | None
) -> tuple[int | None, bool]:
    """(count, ambiguous) — count is None when there is nothing to write.

    `entries` is every entry from every MintageCell parsed for one (value,
    unit, year) key — one row's worth normally, but two when 1992's two
    mint-name sections both name the key (see parse_mintage_table). Entries
    with no pattern marker are added together regardless of their other
    markers: a trial or collector-set-only mintage is still the table's real
    number for that year, and two mints striking the same denomination the
    same year are two real production runs, not alternatives to choose
    between.

    Only entries the table marks as one of two competing *designs* sharing a
    year label (the 2018 hryvnia changeover) are mutually exclusive: the
    record's own `subtype` says which one is its own, and that one entry's
    count is added to the plain total. A record with no subtype, or whose
    subtype names none of the patterned entries, is ambiguous — nothing is
    written for it, not even the plain total from an unrelated mint.
    """
    countable = [entry for entry in entries if entry.count]
    plain = [entry for entry in countable if entry.pattern is None]
    patterned = [entry for entry in countable if entry.pattern is not None]
    total = sum(entry.count for entry in plain if entry.count is not None)
    if not patterned:
        return (total or None), False
    wanted = _PATTERN_BY_SUBTYPE.get(subtype or "")
    matches = [entry for entry in patterned if entry.pattern == wanted] if wanted else []
    if len(matches) != 1:
        return None, True
    matched_count = matches[0].count
    assert matched_count is not None  # filtered into `countable` above
    return total + matched_count, False


async def apply_mintage(
    session: AsyncSession,
    *,
    country_id: int,
    mintage: list[MintageCell],
    dry_run: bool,
    refresh: bool = False,
) -> MintageOutcome:
    outcome = MintageOutcome()
    index: dict[tuple[Decimal, str, int], list[MintageCell]] = {}
    for cell in mintage:
        index.setdefault((cell.value, cell.unit, cell.year), []).append(cell)

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
        cells = index.get((value, unit, item.issue_year))
        if cells is None:
            outcome.no_wikipedia_cell += 1
            continue
        entries = tuple(entry for cell in cells for entry in cell.entries)
        count, ambiguous = usable_count(entries, subtype=item.subtype)
        if ambiguous:
            outcome.ambiguous.append(
                {"itemId": item.id, "year": item.issue_year, "denomination": f"{value} {unit}"}
            )
            continue
        if count is None:
            outcome.unchanged += 1
            continue
        if item.mintage_actual is not None:
            if item.mintage_actual == count:
                outcome.unchanged += 1
                continue
            if not refresh:
                outcome.discrepancies.append(
                    {"itemId": item.id, "existing": item.mintage_actual, "wikipedia": count}
                )
                outcome.unchanged += 1
                continue
            outcome.refreshed.append({"itemId": item.id, "old": item.mintage_actual, "new": count})
            if not dry_run:
                item.mintage_actual = count
            continue

        outcome.updated += 1
        if dry_run:
            continue
        item.mintage_actual = count

    if not dry_run:
        await session.flush()
    return outcome
