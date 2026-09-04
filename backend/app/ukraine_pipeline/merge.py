"""merge — two of our records for one coin, made into one.

The first run of the gaps step created a record for every National Bank card
that no link pointed at, and some of those coins we already had: our own
"Пектораль" rows 1122-1125 and the new 3106-3109 from cards nbu:1307-1310 are
the same four coins under two spellings. The bridge could not tell, because
nothing in the titles separates the four from each other — the leopard, the
lion, the griffin and the man are in the card's prose, not in its name.

So this step does not decide. It lists the pairs — same year, same face value,
same series — with the National Bank's own description beside them and the
words the two sides share, and a person writes "yes" against the pairs that
are one coin. Only then does anything move.

What moves is everything that points at the old record: the owners' coins and
their photographs first, then purchases, sales, offers, price history and
links. The old record is archived with the merge as its reason, and deleted
only once nothing refers to it any more — the order docs/04-business-rules.md
lays down for the rare case where a shared record really does go.

The report states the instances and the money on both records before the move
and on the survivor after it. They have to add up; a merge that loses a coin
is a bug, not a merge.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CatalogItem,
    CatalogVariant,
    CollectionItem,
    Expense,
    MarketPriceSnapshot,
    MediaFile,
    PriceSourceLink,
    PurchaseOffer,
    Sale,
)
from app.ukraine_pipeline.bridge import YES
from app.ukraine_pipeline.catalog import OurItem, load_items
from app.ukraine_pipeline.gaps import SOURCE_KEY_PREFIX
from app.ukraine_pipeline.lexicon import Lexicon
from app.ukraine_pipeline.sources import Sources
from app.ukraine_recon.models import SOURCE_NBU
from app.ukraine_recon.normalize import normalize_title

CSV_COLUMNS = (
    "decision",
    "gapItemId",
    "gapTitle",
    "gapSourceKey",
    "ourItemId",
    "ourTitle",
    "year",
    "denomination",
    "series",
    "score",
    # The words our name and the National Bank's card have in common: on a
    # series of four coins with one name, this is what tells them apart.
    "sharedWords",
    "nbuDescription",
    "ourInstances",
    "ourQuantity",
    "ourPurchaseUah",
    "gapInstances",
    "gapQuantity",
    "gapPurchaseUah",
)
MAX_CANDIDATES_PER_GAP = 5
DESCRIPTION_CHARS = 400
# "лев" is three letters and is exactly the word that tells one Пектораль
# from another; the stem is what is compared, so a Ukrainian ending on the
# card's side does not hide it.
MEANINGFUL_WORD = 3
STEM = 5
_WORD_RE = re.compile(rf"[^\W\d_]{{{MEANINGFUL_WORD},}}", re.UNICODE)

# Everything that points at a catalog item, and the columns that must stay
# unique on the record it is moved to. A row that would collide is a copy of
# one the survivor already has, so it goes rather than blocking the merge.
REFERENCES: tuple[tuple[Any, tuple[str, ...]], ...] = (
    (CollectionItem, ()),
    (MediaFile, ()),
    (Expense, ()),
    (Sale, ()),
    (PurchaseOffer, ()),
    (CatalogVariant, ("name", "mint_mark")),
    (MarketPriceSnapshot, ("source", "grade", "observed_at")),
    (PriceSourceLink, ("source",)),
)


@dataclass
class Holdings:
    """What sits on one catalog record: coins, money, photographs."""

    instances: int = 0
    quantity: int = 0
    purchase_uah: Decimal = Decimal(0)
    media: int = 0

    def __add__(self, other: Holdings) -> Holdings:
        return Holdings(
            instances=self.instances + other.instances,
            quantity=self.quantity + other.quantity,
            purchase_uah=self.purchase_uah + other.purchase_uah,
            media=self.media + other.media,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "instances": self.instances,
            "quantity": self.quantity,
            "purchaseUah": str(self.purchase_uah),
            "media": self.media,
        }


@dataclass
class MergeOutcome:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    merged: list[dict[str, Any]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "candidates": len(self.candidates),
            "merged": len(self.merged),
            "movedInstances": sum(row["moved"]["instances"] for row in self.merged),
            "movedMedia": sum(row["moved"]["media"] for row in self.merged),
            "problems": len(self.problems),
        }


# ------------------------------------------------------------------- finding
def _slot(item: OurItem) -> tuple[int, str]:
    value = item.denomination
    return item.issue_year, "?" if value is None else format(value.normalize(), "f")


def _pairs(items: list[OurItem]) -> list[tuple[OurItem, OurItem]]:
    """(record the gaps step made, our older record) for every duplicate shape."""
    active = [item for item in items if not item.is_archived]
    made = [item for item in active if (item.source_key or "").startswith(SOURCE_KEY_PREFIX)]
    ours = [
        item
        for item in active
        if not item.links and not (item.source_key or "").startswith(SOURCE_KEY_PREFIX)
    ]
    by_slot: dict[tuple[int, str], list[OurItem]] = {}
    for item in ours:
        by_slot.setdefault(_slot(item), []).append(item)

    found: list[tuple[OurItem, OurItem]] = []
    for gap in made:
        year, value = _slot(gap)
        candidates = list(by_slot.get((year, value), []))
        if value != "?":
            # A record whose face value we never recorded is a candidate for
            # any face value of that year — the likeliest duplicate of all.
            candidates.extend(by_slot.get((year, "?"), []))
        series = normalize_title(gap.series_name) if gap.series_name else None
        for candidate in candidates:
            theirs = normalize_title(candidate.series_name) if candidate.series_name else None
            if series and theirs and series != theirs:
                continue
            found.append((gap, candidate))
    return found


def nbu_description(sources: Sources, source_key: str | None) -> str:
    """The card's prose, shortened to what fits in a spreadsheet cell."""
    card_id = (source_key or "").removeprefix(SOURCE_KEY_PREFIX)
    cluster = sources.cluster_of(SOURCE_NBU, card_id) if card_id else None
    record = cluster.record_of(SOURCE_NBU) if cluster is not None else None
    paragraphs = (record.extra.get("description") if record is not None else None) or []
    text = " ".join(str(paragraph) for paragraph in paragraphs).strip()
    return text[:DESCRIPTION_CHARS]


def shared_words(title: str, description: str) -> list[str]:
    """Words of our title that the card's prose also uses.

    Compared by stem, so "леопард" in our title still meets "леопарда" in the
    card's prose.
    """
    ours = set(_WORD_RE.findall(normalize_title(title)))
    theirs = normalize_title(description)
    return sorted(word for word in ours if word[:STEM] in theirs)


async def find_pairs(
    session: AsyncSession,
    *,
    country_id: int,
    sources: Sources,
    lexicon: Lexicon,
) -> MergeOutcome:
    outcome = MergeOutcome()
    items = await load_items(session, country_id)
    per_gap: dict[int, int] = {}

    for gap, ours in _pairs(items):
        if per_gap.get(gap.id, 0) >= MAX_CANDIDATES_PER_GAP:
            continue
        per_gap[gap.id] = per_gap.get(gap.id, 0) + 1
        description = nbu_description(sources, gap.source_key)
        gap_holdings = await holdings_of(session, gap.id)
        our_holdings = await holdings_of(session, ours.id)
        outcome.candidates.append(
            {
                "decision": "",
                "gapItemId": gap.id,
                "gapTitle": gap.title_original,
                "gapSourceKey": gap.source_key or "",
                "ourItemId": ours.id,
                "ourTitle": ours.title_original,
                "year": gap.issue_year,
                "denomination": gap.denomination or "",
                "series": gap.series_name or ours.series_name or "",
                "score": round(lexicon.score(ours.title_original, gap.title_original), 1),
                "sharedWords": " ".join(shared_words(ours.title_original, description)),
                "nbuDescription": description,
                "ourInstances": our_holdings.instances,
                "ourQuantity": our_holdings.quantity,
                "ourPurchaseUah": str(our_holdings.purchase_uah),
                "gapInstances": gap_holdings.instances,
                "gapQuantity": gap_holdings.quantity,
                "gapPurchaseUah": str(gap_holdings.purchase_uah),
            }
        )
    outcome.candidates.sort(key=lambda row: (-float(row["score"]), row["gapItemId"]))
    return outcome


def write_merge_csv(path: Path, outcome: MergeOutcome) -> int:
    """One row per pair; a person writes "yes" in the first column."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(outcome.candidates)
    return len(outcome.candidates)


def read_merge_csv(path: Path) -> list[tuple[int, int]]:
    """[(record that survives, record that goes)] out of the rows marked yes.

    Opened as utf-8-sig for the same reason the bridge's file is: Excel writes
    a BOM back. A record named twice is refused — merging is not reversible,
    and two answers for one coin means the file was not read, only filled in.
    """
    chosen: list[tuple[int, int]] = []
    seen: set[int] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() not in YES:
                continue
            keep = int(str(row["gapItemId"]).strip())
            drop = int(str(row["ourItemId"]).strip())
            if keep == drop:
                message = f"merge file pairs record #{keep} with itself"
                raise ValueError(message)
            if keep in seen or drop in seen:
                message = f"merge file names record #{keep if keep in seen else drop} twice"
                raise ValueError(message)
            seen.update((keep, drop))
            chosen.append((keep, drop))
    return chosen


# ------------------------------------------------------------------- applying
async def holdings_of(session: AsyncSession, item_id: int) -> Holdings:
    instances, quantity, purchase = (
        await session.execute(
            select(
                func.count(CollectionItem.id),
                func.coalesce(func.sum(CollectionItem.quantity), 0),
                func.coalesce(
                    func.sum(
                        CollectionItem.quantity
                        * func.coalesce(CollectionItem.purchase_price, 0)
                        * func.coalesce(CollectionItem.purchase_rate_uah, 1)
                    ),
                    0,
                ),
            ).where(CollectionItem.catalog_item_id == item_id)
        )
    ).one()
    media = (
        await session.execute(
            select(func.count(MediaFile.id)).where(MediaFile.catalog_item_id == item_id)
        )
    ).scalar_one()
    return Holdings(
        instances=int(instances),
        quantity=int(quantity),
        purchase_uah=Decimal(purchase).quantize(Decimal("0.01")),
        media=int(media),
    )


def _rows_of(model: Any, item_id: int, columns: tuple[str, ...]) -> Select[Any]:
    selected = [model.id, *(getattr(model, column) for column in columns)]
    return select(*selected).where(model.catalog_item_id == item_id)


async def _move_rows(
    session: AsyncSession, model: Any, *, keep_id: int, drop_id: int, unique: tuple[str, ...]
) -> tuple[int, int]:
    """Re-point one table's rows; return (moved, dropped as duplicates)."""
    dropped = 0
    if unique:
        held = (await session.execute(_rows_of(model, keep_id, unique))).all()
        taken = {tuple(row[1:]) for row in held}
        collisions = [
            row[0]
            for row in (await session.execute(_rows_of(model, drop_id, unique))).all()
            if tuple(row[1:]) in taken
        ]
        if collisions:
            await session.execute(delete(model).where(model.id.in_(collisions)))
            dropped = len(collisions)
    moved = (
        await session.execute(select(func.count(model.id)).where(model.catalog_item_id == drop_id))
    ).scalar_one()
    await session.execute(
        update(model)
        .where(model.catalog_item_id == drop_id)
        .values(catalog_item_id=keep_id)
        .execution_options(synchronize_session=False)
    )
    return int(moved), dropped


async def _still_referenced(session: AsyncSession, item_id: int) -> list[str]:
    names: list[str] = []
    for model, _unique in REFERENCES:
        count = (
            await session.execute(
                select(func.count(model.id)).where(model.catalog_item_id == item_id)
            )
        ).scalar_one()
        if count:
            names.append(f"{model.__tablename__}={count}")
    return names


async def apply_merges(
    session: AsyncSession,
    decisions: list[tuple[int, int]],
    *,
    dry_run: bool,
) -> MergeOutcome:
    """Move everything off the old record onto the new one, then retire it."""
    outcome = MergeOutcome()
    for keep_id, drop_id in decisions:
        keep = await session.get(CatalogItem, keep_id)
        drop = await session.get(CatalogItem, drop_id)
        if keep is None or drop is None:
            outcome.problems.append(f"merge {drop_id} -> {keep_id}: one of the records is gone")
            continue
        if keep.created_by is not None or drop.created_by is not None:
            # A personal item belongs to its author; the pipeline speaks for
            # the issuer and has no say over it.
            outcome.problems.append(
                f"merge {drop_id} -> {keep_id}: only shared records can be merged"
            )
            continue

        before_keep = await holdings_of(session, keep_id)
        before_drop = await holdings_of(session, drop_id)
        row: dict[str, Any] = {
            "keepItemId": keep_id,
            "keepTitle": keep.title_original,
            "dropItemId": drop_id,
            "dropTitle": drop.title_original,
            "before": {"keep": before_keep.to_dict(), "drop": before_drop.to_dict()},
            "moved": before_drop.to_dict(),
        }
        if dry_run:
            row["after"] = (before_keep + before_drop).to_dict()
            row["deleted"] = False
            outcome.merged.append(row)
            continue

        moved: dict[str, dict[str, int]] = {}
        for model, unique in REFERENCES:
            count, dropped = await _move_rows(
                session, model, keep_id=keep_id, drop_id=drop_id, unique=unique
            )
            if count or dropped:
                moved[model.__tablename__] = {"moved": count, "droppedAsDuplicate": dropped}
        await session.flush()

        # Archived first, deleted second: a shared record only ever goes this
        # way round, and if anything still points at it the archive is where
        # it stops (docs/04-business-rules.md, rule 10).
        drop.is_archived = True
        drop.archive_reason = f"merged into #{keep_id}"
        drop.archived_at = datetime.now(UTC)
        await session.flush()

        remaining = await _still_referenced(session, drop_id)
        if remaining:
            outcome.problems.append(
                f"merge {drop_id} -> {keep_id}: archived but kept, still referenced by "
                + ", ".join(remaining)
            )
            row["deleted"] = False
        else:
            await session.execute(delete(CatalogItem).where(CatalogItem.id == drop_id))
            await session.flush()
            row["deleted"] = True

        after = await holdings_of(session, keep_id)
        row["tables"] = moved
        row["after"] = after.to_dict()
        expected = before_keep + before_drop
        if (after.instances, after.quantity, after.media) != (
            expected.instances,
            expected.quantity,
            expected.media,
        ):
            outcome.problems.append(
                f"merge {drop_id} -> {keep_id}: {expected.to_dict()} expected, "
                f"{after.to_dict()} found"
            )
        outcome.merged.append(row)
    return outcome
