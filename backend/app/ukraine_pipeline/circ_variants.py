"""circ-variants — retiring uCoin mint/composition duplicates into catalog_variants.

The uCoin Excel import kept more than one quality variant of the same coin
for a handful of (denomination, year) slots — circ_bridge.py's own review CSV
already surfaces them as "two of our records claim one Wikipedia key" and
leaves the one a person did not pick unresolved (docs/05-integrations.md,
section 10: 21 such rows after the production run). This step is what those
21 rows are actually for: once a person has picked the real occupant of the
slot (via circ-bridge's review), the record that lost becomes a *variant* of
the winner — `catalog_variants` — instead of sitting in the shared catalogue
forever unlinked and un-collectible.

**Naming, from our own stored data only.** Nothing here re-reads uCoin: the
distinguishing word is either already in the losing record's own
`title_original` (the Excel import's own wording, e.g. "вдавлений тризуб" on
some 1992 kopiyka records) or in its stored `material` text (a magnetic vs.
non-magnetic steel note on some 2013-2016 kopiyka twins). Where neither says
anything distinguishing, this step does not invent a label — the pair goes to
`--circ-variants-review-out` for a person to name by hand.

**The 2018 hryvnia changeover shares the same mechanism.** Some (denomination,
year) slots — today, only the hryvnia's — carry more than one *design*, not
just more than one photograph: circ_types.py already carries a `subtype` per
design. Before naming a duplicate, this step tries to assign `subtype` to
every member of such a slot by matching its own stored `weight_grams` /
`diameter_mm` against each design's known profile (within `TOLERANCE`, uCoin
figures being rounded to a tenth of a unit). Two records that end up with the
*same* subtype are true duplicates of one design and fall through to the
ordinary naming step above; a record whose physical fields do not pick a
single design goes to review exactly like an unnamed textual duplicate — its
`dupWeight`/`dupDiameter` columns show what was on file, so a reviewer can
tell "no data" from "two designs matched" at a glance.

**Personal collections are never moved.** Archiving a duplicate the ordinary
way (`04-business-rules.md`, rule 10) leaves any `collection_items` pointing
at it exactly where they are — nothing here re-points a coin someone already
owns onto the surviving record. A duplicate that does carry personal
instances is archived like any other, but named in the report
(`personalInstancesOnVariant`) since it is worth a person's attention.

**Idempotent by construction, not by a database constraint.** `is_archived`
alone decides whether this step has already handled a record:
`catalog_variants`'s own unique index treats NULL `mint_mark` values as
distinct from each other, so it cannot be relied on to stop a second insert
for the same pair. Both the automatic path and the review-CSV apply path
check `is_archived` before writing anything, and a record this step already
archived stops appearing in the active groups a second run scans at all.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, CatalogVariant, CollectionItem
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.circ_gaps import SOURCE_KEY_PREFIX
from app.ukraine_pipeline.circ_types import TYPES, CoinType
from app.ukraine_recon.models import SOURCE_WIKIPEDIA

CIRCULATION = "circulation"
ARCHIVE_REASON = "переведено до варіанту каталогу"
NOTE_PREFIX = "circ-variants: former catalog_items.id="

# uCoin's own physical figures are rounded to a tenth of a gram/millimetre;
# a design's profile in circ_types.py carries the same precision, so exact
# equality is brittle. +-0.2 absorbs that rounding without blurring together
# two genuinely different designs (the hryvnia profiles are at least 0.3 g
# and 0.9 mm apart from each other).
TOLERANCE = Decimal("0.2")

TRIZUB_MARKERS = ("вдавлен", "втиснут", "трезубец", "тризуб")
NON_MAGNETIC_MARKERS = ("немагнітн", "немагнитн")
MAGNETIC_MARKERS = ("магнітн", "магнитн")

CSV_COLUMNS = (
    "decision",
    "dupItemId",
    "dupTitle",
    "dupMaterial",
    "dupWeight",
    "dupDiameter",
    "baseItemId",
    "baseTitle",
    "variantName",
)
YES = frozenset({"y", "yes", "1", "true", "+", "так"})


@dataclass
class ItemFields:
    """The columns catalog.OurItem does not carry, fetched once per run."""

    title_original: str
    material: str | None
    weight_grams: Decimal | None
    diameter_mm: Decimal | None
    subtype: str | None
    is_archived: bool


@dataclass
class ReviewRow:
    dup_id: int
    base_id: int
    dup_fields: ItemFields
    base_fields: ItemFields


@dataclass
class CircVariantsOutcome:
    created: list[dict[str, Any]] = field(default_factory=list)
    review: list[ReviewRow] = field(default_factory=list)
    subtypes_assigned: list[dict[str, Any]] = field(default_factory=list)
    personal_instances_on_variant: list[dict[str, Any]] = field(default_factory=list)
    skipped_no_base: int = 0
    skipped_multiple_bases: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "created": len(self.created),
            "archived": len(self.created),
            "reviewRows": len(self.review),
            "subtypesAssigned": len(self.subtypes_assigned),
            "personalInstancesOnVariant": len(self.personal_instances_on_variant),
            "skippedNoBase": self.skipped_no_base,
            "skippedMultipleBases": self.skipped_multiple_bases,
        }


def _is_wikipedia_linked(item: OurItem) -> bool:
    """Same check as circ_reclassify.py's own — a connection this pipeline
    made (a price_source_links row or circ_gaps.py's "wiki-circ:" source
    key), not a person's manual link."""
    if SOURCE_WIKIPEDIA in item.links:
        return True
    return (item.source_key or "").startswith(SOURCE_KEY_PREFIX)


def _slot_groups(items: list[OurItem]) -> dict[tuple[Decimal, str, int], list[OurItem]]:
    """Active, non-NBU-linked circulation records sharing (value, unit, year)."""
    groups: dict[tuple[Decimal, str, int], list[OurItem]] = {}
    for item in items:
        if item.is_archived or item.collection_group != CIRCULATION or item.is_nbu_linked:
            continue
        if item.denomination is None or item.denomination_unit is None:
            continue
        key = (item.denomination, item.denomination_unit, item.issue_year)
        groups.setdefault(key, []).append(item)
    return {key: group for key, group in groups.items() if len(group) > 1}


def _subtype_profiles(value: Decimal, unit: str) -> list[CoinType]:
    """Every design of this denomination that carries its own subtype label,
    regardless of the year range it is normally struck in — a record dated
    outside that range (a set-only strike) is exactly what this is for."""
    return [t for t in TYPES if t.value == value and t.unit == unit and t.subtype is not None]


async def _fetch_fields(session: AsyncSession, item_ids: list[int]) -> dict[int, ItemFields]:
    if not item_ids:
        return {}
    rows = await session.execute(
        select(
            CatalogItem.id,
            CatalogItem.title_original,
            CatalogItem.material,
            CatalogItem.weight_grams,
            CatalogItem.diameter_mm,
            CatalogItem.subtype,
            CatalogItem.is_archived,
        ).where(CatalogItem.id.in_(item_ids))
    )
    return {
        row.id: ItemFields(
            title_original=row.title_original,
            material=row.material,
            weight_grams=row.weight_grams,
            diameter_mm=row.diameter_mm,
            subtype=row.subtype,
            is_archived=row.is_archived,
        )
        for row in rows
    }


def _match_profile(
    weight: Decimal | None, diameter: Decimal | None, candidates: list[CoinType]
) -> str | None:
    if weight is None or diameter is None:
        return None
    matches = [
        c
        for c in candidates
        if abs(c.weight_grams - weight) <= TOLERANCE and abs(c.diameter_mm - diameter) <= TOLERANCE
    ]
    return matches[0].subtype if len(matches) == 1 else None


def _marker(
    text: str | None, *, negative: tuple[str, ...], positive: tuple[str, ...]
) -> str | None:
    """Non-magnetic checked first: "немагнітна" contains "магнітн" as a
    substring, so checking the positive markers first would misclassify it."""
    if not text:
        return None
    lowered = text.casefold()
    if any(marker in lowered for marker in negative):
        return "немагнітна"
    if any(marker in lowered for marker in positive):
        return "магнітна"
    return None


def _classify(dup: ItemFields, base: ItemFields) -> str | None:
    """The variant's name, from the losing record's own stored text — never
    a guess. None means "a person has to look", not "no variant"."""
    if any(marker in dup.title_original.casefold() for marker in TRIZUB_MARKERS):
        return "Втиснутий тризуб"
    dup_marker = _marker(dup.material, negative=NON_MAGNETIC_MARKERS, positive=MAGNETIC_MARKERS)
    base_marker = _marker(base.material, negative=NON_MAGNETIC_MARKERS, positive=MAGNETIC_MARKERS)
    if dup_marker and dup_marker != base_marker:
        return dup_marker.capitalize()
    return None


async def _create_variant(
    session: AsyncSession, *, base_id: int, dup_id: int, name: str, dry_run: bool
) -> None:
    if dry_run:
        return
    session.add(CatalogVariant(catalog_item_id=base_id, name=name, notes=f"{NOTE_PREFIX}{dup_id}"))
    dup_row = await session.get(CatalogItem, dup_id)
    assert dup_row is not None
    dup_row.is_archived = True
    dup_row.archived_at = datetime.now(UTC)
    dup_row.archive_reason = ARCHIVE_REASON


async def _personal_instances(session: AsyncSession, item_id: int) -> int:
    rows = await session.execute(
        select(CollectionItem.id).where(CollectionItem.catalog_item_id == item_id)
    )
    return len(rows.scalars().all())


async def _resolve_bucket(
    session: AsyncSession,
    bucket: list[OurItem],
    fields: dict[int, ItemFields],
    outcome: CircVariantsOutcome,
    *,
    dry_run: bool,
) -> None:
    if len(bucket) < 2:
        return
    bases = [item for item in bucket if _is_wikipedia_linked(item)]
    if len(bases) == 0:
        outcome.skipped_no_base += len(bucket)
        return
    if len(bases) > 1:
        outcome.skipped_multiple_bases += len(bucket)
        return
    base = bases[0]
    base_fields = fields[base.id]
    for dup in bucket:
        if dup.id == base.id:
            continue
        dup_fields = fields[dup.id]
        if dup_fields.is_archived:
            continue  # an earlier run (or this one, for another bucket) already handled it
        name = _classify(dup_fields, base_fields)
        if name is None:
            outcome.review.append(
                ReviewRow(
                    dup_id=dup.id, base_id=base.id, dup_fields=dup_fields, base_fields=base_fields
                )
            )
            continue
        instances = await _personal_instances(session, dup.id)
        if instances:
            outcome.personal_instances_on_variant.append({"itemId": dup.id, "instances": instances})
        outcome.created.append({"dupItemId": dup.id, "baseItemId": base.id, "name": name})
        await _create_variant(session, base_id=base.id, dup_id=dup.id, name=name, dry_run=dry_run)


async def run_variants(
    session: AsyncSession, *, items: list[OurItem], dry_run: bool
) -> CircVariantsOutcome:
    outcome = CircVariantsOutcome()
    groups = _slot_groups(items)
    if not groups:
        return outcome

    all_ids = [item.id for group in groups.values() for item in group]
    fields = await _fetch_fields(session, all_ids)

    for (value, unit, _year), group in groups.items():
        profiles = _subtype_profiles(value, unit)
        if profiles:
            for item in group:
                current = fields[item.id]
                if current.subtype is not None:
                    continue
                matched = _match_profile(current.weight_grams, current.diameter_mm, profiles)
                if matched is None:
                    continue
                current.subtype = matched
                outcome.subtypes_assigned.append({"itemId": item.id, "subtype": matched})
                if not dry_run:
                    row = await session.get(CatalogItem, item.id)
                    assert row is not None
                    row.subtype = matched

            by_subtype: dict[str | None, list[OurItem]] = {}
            for item in group:
                by_subtype.setdefault(fields[item.id].subtype, []).append(item)
            for bucket in by_subtype.values():
                await _resolve_bucket(session, bucket, fields, outcome, dry_run=dry_run)
        else:
            await _resolve_bucket(session, group, fields, outcome, dry_run=dry_run)

    if not dry_run:
        await session.flush()
    return outcome


def write_review_csv(path: Path, outcome: CircVariantsOutcome) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.review:
            writer.writerow(
                {
                    "decision": "",
                    "dupItemId": row.dup_id,
                    "dupTitle": row.dup_fields.title_original,
                    "dupMaterial": row.dup_fields.material or "",
                    "dupWeight": row.dup_fields.weight_grams or "",
                    "dupDiameter": row.dup_fields.diameter_mm or "",
                    "baseItemId": row.base_id,
                    "baseTitle": row.base_fields.title_original,
                    "variantName": "",
                }
            )
    return len(outcome.review)


@dataclass
class ReviewDecision:
    dup_id: int
    base_id: int
    variant_name: str


def read_review_csv(path: Path) -> list[ReviewDecision]:
    decisions: list[ReviewDecision] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() not in YES:
                continue
            name = (row.get("variantName") or "").strip()
            if not name:
                message = f"review file marks item #{row['dupItemId']} yes with no variantName"
                raise ValueError(message)
            decisions.append(
                ReviewDecision(
                    dup_id=int(str(row["dupItemId"]).strip()),
                    base_id=int(str(row["baseItemId"]).strip()),
                    variant_name=name,
                )
            )
    return decisions


async def apply_review(
    session: AsyncSession, decisions: list[ReviewDecision], *, dry_run: bool
) -> CircVariantsOutcome:
    outcome = CircVariantsOutcome()
    for decision in decisions:
        dup_row = await session.get(CatalogItem, decision.dup_id)
        if dup_row is None or dup_row.is_archived:
            continue  # already handled, or the id is stale — never guess which
        instances = await _personal_instances(session, decision.dup_id)
        if instances:
            outcome.personal_instances_on_variant.append(
                {"itemId": decision.dup_id, "instances": instances}
            )
        outcome.created.append(
            {
                "dupItemId": decision.dup_id,
                "baseItemId": decision.base_id,
                "name": decision.variant_name,
            }
        )
        await _create_variant(
            session,
            base_id=decision.base_id,
            dup_id=decision.dup_id,
            name=decision.variant_name,
            dry_run=dry_run,
        )
    if not dry_run:
        await session.flush()
    return outcome
