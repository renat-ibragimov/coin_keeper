"""circ-bridge — the denomination + year bridge for circulation coins.

Circulation records need none of the fuzzy scoring app/ukraine_pipeline/
bridge.py does for commemoratives: the Wikipedia mintage table
(app/ukraine_recon/wikipedia.py:parse_mintage_table) is indexed by exactly
the same key our own records are, (face value, unit, year), so a match is
either exact or absent. What this step actually has to do is get every
circulation record into that key shape first.

Two passes:

1. **repair_denominations** — some circulation records came out of the uCoin
   Excel import with no structured face value at all, just a title like
   "25 копеек, 1994" (docs/05-integrations.md, section 9). The face value is
   parsed off the front of the title with the same
   app.reference_data.denominations.parse_label the schema migration used,
   and denomination_id is filled in — never guessed at a value the title does
   not state.
2. **decide** — every active, unarchived circulation record with a known face
   value and year is grouped by (value, unit, year). A key the Wikipedia
   table also has, held by exactly one of our records, is linked
   (price_source_links, source "Wikipedia", the article's own URL — there is
   one page, not one per coin, so every link names the same URL). A key held
   by two or more of our records is a duplicate in our own catalogue — the
   uCoin import kept more than one quality variant of the same coin — and
   goes to a review CSV in the same shape app/ukraine_pipeline/bridge.py
   already uses, so the same runbook step applies it.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, PriceSourceLink
from app.models.enums import MatchStatus
from app.reference_data.denominations import DenominationParseError, ParsedDenomination, parse_label
from app.ukraine_pipeline.catalog import LINK_SOURCES, OurItem, face_value
from app.ukraine_pipeline.gaps import ensure_denomination
from app.ukraine_recon.http import PoliteClient, SourceUnreachableError
from app.ukraine_recon.models import SOURCE_WIKIPEDIA
from app.ukraine_recon.wikipedia import PAGE_HRYVNIA, MintageCell, page_url, parse_mintage_table

CIRCULATION = "circulation"
WIKIPEDIA_URL = page_url(PAGE_HRYVNIA)
CSV_COLUMNS = ("decision", "itemId", "ourTitle", "ourYear", "denomination", "candidateCount")
YES = frozenset({"y", "yes", "1", "true", "+", "так"})

# "25 копеек, 1994" -> the label is everything before the first comma; a
# title with no comma is tried whole. Either way the actual parsing — which
# words are a kopiika versus a kopeck, what "грн" abbreviates to — is
# app.reference_data.denominations.parse_label's job, not this regex's.
_HEAD_RE = re.compile(r"^[^,]+")


@dataclass
class DenominationRepair:
    filled: list[dict[str, Any]] = field(default_factory=list)
    unparsed: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class BridgeOutcome:
    repaired: DenominationRepair = field(default_factory=DenominationRepair)
    linked: list[OurItem] = field(default_factory=list)
    # (item, how many of our records claim the same denomination + year) —
    # the count travels with the item so write_review_csv needs nothing
    # recomputed, and apply_review can move a chosen item into `linked`
    # without losing it.
    review: list[tuple[OurItem, int]] = field(default_factory=list)
    without_wikipedia_entry: list[OurItem] = field(default_factory=list)
    # NBU-catalogue-linked records circ-reclassify should have already moved
    # out of circulation; counted here too in case it was skipped for this
    # run (app/ukraine_pipeline/circ_reclassify.py).
    skipped_nbu_linked: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "denominationsFilled": len(self.repaired.filled),
            "denominationsUnparsed": len(self.repaired.unparsed),
            "linked": len(self.linked),
            "toReview": len(self.review),
            "withoutWikipediaEntry": len(self.without_wikipedia_entry),
            "skippedNbuLinked": self.skipped_nbu_linked,
        }


def parse_title_denomination(title: str) -> ParsedDenomination | None:
    head = _HEAD_RE.match(title)
    candidates = [head.group(0).strip()] if head else []
    if title.strip() not in candidates:
        candidates.append(title.strip())
    for candidate in candidates:
        try:
            return parse_label(candidate, country_code="UA")
        except DenominationParseError:
            continue
    return None


async def repair_denominations(
    session: AsyncSession, *, country_id: int, items: list[OurItem], dry_run: bool
) -> DenominationRepair:
    """Fill denomination_id from the title, for circulation records missing it.

    Mutates the OurItem objects in place with what was read, dry run or not:
    the rest of this step's matching needs the face value regardless of
    whether it is written to the database yet.
    """
    outcome = DenominationRepair()
    cache: dict[tuple[str, str, Decimal], int] = {}
    for item in items:
        if item.collection_group != CIRCULATION or item.denomination_id is not None:
            continue
        parsed = parse_title_denomination(item.title_original)
        if parsed is None:
            outcome.unparsed.append({"itemId": item.id, "title": item.title_original})
            continue
        outcome.filled.append(
            {"itemId": item.id, "title": item.title_original, "denomination": str(parsed.value)}
        )
        item.denomination = face_value(parsed.unit, parsed.value)
        item.denomination_unit = parsed.unit
        if dry_run:
            continue
        denomination_id = await ensure_denomination(
            session, country_id=country_id, parsed=parsed, cache=cache
        )
        item.denomination_id = denomination_id
        await session.execute(
            update(CatalogItem)
            .where(CatalogItem.id == item.id)
            .values(denomination_id=denomination_id)
        )
    if not dry_run:
        await session.flush()
    return outcome


def fetch_mintage_table(
    client: PoliteClient, *, log: Callable[[str], None], warn: Callable[[str], None]
) -> list[MintageCell]:
    """The one page every circ-* step reads its (denomination, year) facts from."""
    url = page_url(PAGE_HRYVNIA)
    try:
        result = client.get(url)
    except SourceUnreachableError as exc:
        warn(f"wikipedia mintage table unreachable: {exc}")
        return []
    if not result.ok:
        warn(f"wikipedia mintage table: HTTP {result.status} for {url}")
        return []
    cells = parse_mintage_table(result.text)
    log(f"wikipedia mintage table: {len(cells)} cells")
    return cells


def wikipedia_keys(mintage: list[MintageCell]) -> set[tuple[Decimal, str, int]]:
    """(value, unit, year) for every cell that says a coin actually exists.

    A cell that is only a trial strike (*) is a pattern piece, not a
    circulation-year issue, and is not grounds to link or create a record for
    that year — gaps.py draws the same line for the commemorative rolls.
    """
    keys: set[tuple[Decimal, str, int]] = set()
    for cell in mintage:
        for entry in cell.entries:
            if entry.trial or entry.unknown:
                continue
            if entry.count or entry.issued_no_count:
                keys.add((cell.value, cell.unit, cell.year))
                break
    return keys


async def run_bridge(
    session: AsyncSession,
    *,
    country_id: int,
    items: list[OurItem],
    mintage: list[MintageCell],
    dry_run: bool,
) -> BridgeOutcome:
    """The whole step: fill missing denominations, then link by year + value."""
    repaired = await repair_denominations(
        session, country_id=country_id, items=items, dry_run=dry_run
    )
    return decide(items, mintage, repaired=repaired)


def decide(
    items: list[OurItem], mintage: list[MintageCell], *, repaired: DenominationRepair | None = None
) -> BridgeOutcome:
    outcome = BridgeOutcome(repaired=repaired or DenominationRepair())
    wiki_keys = wikipedia_keys(mintage)

    by_key: dict[tuple[Decimal, str, int], list[OurItem]] = {}
    for item in items:
        if item.is_archived or item.collection_group != CIRCULATION:
            continue
        if item.is_nbu_linked:
            outcome.skipped_nbu_linked += 1
            continue
        if item.denomination is None or item.denomination_unit is None:
            continue
        key = (item.denomination, item.denomination_unit, item.issue_year)
        by_key.setdefault(key, []).append(item)

    for key, candidates in by_key.items():
        if key not in wiki_keys:
            outcome.without_wikipedia_entry.extend(candidates)
            continue
        if len(candidates) == 1:
            outcome.linked.append(candidates[0])
            continue
        for candidate in candidates:
            outcome.review.append((candidate, len(candidates)))
    return outcome


def write_review_csv(path: Path, outcome: BridgeOutcome) -> int:
    """One row per candidate; a person writes "yes" against the one to keep.

    Not app/ukraine_pipeline/bridge.py's own CSV shape: there is no cluster or
    score here; what a person is choosing between is which of two of our
    records for the same year and denomination is the real one. The
    "decision"/"itemId" columns and the yes/no vocabulary are the same, so
    the same runbook habit (put "yes" in the first column) applies unchanged.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for item, count in outcome.review:
            writer.writerow(
                {
                    "decision": "",
                    "itemId": item.id,
                    "ourTitle": item.title_original,
                    "ourYear": item.issue_year,
                    "denomination": f"{item.denomination} {item.denomination_unit}",
                    "candidateCount": count,
                }
            )
    return len(outcome.review)


def read_review_csv(path: Path) -> set[int]:
    """Item ids marked yes: the record that keeps the (denomination, year)."""
    chosen: set[int] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() in YES:
                chosen.add(int(str(row["itemId"]).strip()))
    return chosen


def apply_review(outcome: BridgeOutcome, chosen: set[int]) -> BridgeOutcome:
    """Move the rows a person marked yes into `linked`; leave the rest for review."""
    for item, _count in outcome.review:
        if item.id in chosen:
            outcome.linked.append(item)
    outcome.review = [(item, count) for item, count in outcome.review if item.id not in chosen]
    return outcome


async def write_links(session: AsyncSession, items: list[OurItem]) -> int:
    """One price_source_links row per item, all pointing at the one article.

    Upserted the same way app/ukraine_pipeline/bridge.py writes its links: a
    second run updates matched_at in place instead of duplicating the row.
    """
    if not items:
        return 0
    now = datetime.now(UTC)
    rows = [
        {
            "catalog_item_id": item.id,
            "source": LINK_SOURCES[SOURCE_WIKIPEDIA],
            "external_id": WIKIPEDIA_URL,
            "match_status": MatchStatus.CONFIRMED,
            "matched_at": now,
        }
        for item in items
    ]
    statement = pg_insert(PriceSourceLink).values(rows)
    statement = statement.on_conflict_do_update(
        constraint="uq_price_source_links_catalog_item_id_source",
        set_={
            "external_id": statement.excluded.external_id,
            "match_status": statement.excluded.match_status,
            "matched_at": statement.excluded.matched_at,
        },
    )
    await session.execute(statement)
    return len(rows)
