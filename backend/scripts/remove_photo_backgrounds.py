"""Cut a uniform (white or dark), round background out of stored coin photos.

One-off cleanup over `media_files` rows that hold their own `storage_key`
(NBU, ua-coins, manual — anything we host; an `external_url`-only uCoin
hotlink is never touched). See docs/06-media-storage.md, "Удаление фона",
and app.services.media_background for the classifier this calls. Dark-branch
cuts (proof coins on black felt/velvet) get their own `cut:dark` verdict and
their own section in the HTML sheet -- that branch's flood-fill tolerance is
deliberately tight, so its cuts are worth a closer look.

    docker compose run --no-deps api python scripts/remove_photo_backgrounds.py --dry-run

Nothing is written without --apply; a dry run still downloads and classifies
every candidate, since the review CSV and HTML sheet are the point of it.
Already-processed rows (storage_key already carrying the `-nobg` marker this
script writes) are skipped without a network call.

`--trim` is the opposite pass: it walks only the already-`-nobg` rows and
re-crops them to their alpha bbox (app.services.media_background.trim_to_alpha),
for objects cut before that margin trim existed. It rewrites the object at its
own key rather than minting a new one -- the pre-cut original is still the
rollback plan.

    docker compose run --no-deps api python scripts/remove_photo_backgrounds.py --trim --dry-run

`--revert-transparent-originals` is the rollback for the 2026-09 incident: a
run before classify() guarded against it flattened some already-transparent
NBU originals to RGB, read their black matte as a dark background, and cut a
fresh (wrong) alpha over whatever that matte was hiding. It walks the same
already-`-nobg` rows as --trim, but downloads each row's ORIGINAL (the key
without `-nobg`) and applies the same already-transparent criterion
classify() now uses; a row whose original truly had no transparency is a
legitimate white/dark cut and is left alone. See docs/06-media-storage.md,
"Удаление фона", for the full runbook.

    docker compose run --no-deps api python scripts/remove_photo_backgrounds.py \\
        --revert-transparent-originals --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import csv
import hashlib
import html
import io
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.images import VARIANT_SIDES, encode_variants
from app.core.media_keys import preview_key_of, primary_key_of, stored_variants, variant_key
from app.core.storage import ObjectStorage
from app.models import CatalogItem, CollectionItem, MediaFile
from app.services.media_background import (
    ALREADY_TRANSPARENT_FRACTION_MIN,
    Verdict,
    classify,
    cut_background,
    transparent_pixel_fraction,
    trim_to_alpha,
)

EXIT_OK = 0
EXIT_USAGE = 2

# The marker a cut object's key carries so a second run recognizes it as
# already done, without a schema change to record the fact.
NOBG_MARKER = "-nobg"
_VARIANT_SUFFIX = re.compile(r"_(\d+)\.webp$")

PREVIEW_SIDE = 200

# How many trimmed rows get a before/after preview in the --trim HTML sheet --
# a "sample", not a card per row like the main review does for every cut.
TRIM_SAMPLE_SIZE = 30

CSV_COLUMNS = (
    "mediaFileId",
    "itemId",
    "title",
    "verdict",
    "bgKind",
    "borderBackgroundFraction",
    "circularity",
    "cornerWhiteness",
    "oldKey",
    "newKey",
    "error",
)

TRIM_CSV_COLUMNS = (
    "mediaFileId",
    "itemId",
    "title",
    "oldWidth",
    "oldHeight",
    "newWidth",
    "newHeight",
    "trimmedFraction",
    "oldKey",
    "error",
)

# --revert-transparent-originals status values, in the order a row can reach
# them: no surviving original to check at all, checked and legitimately not
# transparent, checked and needs (or got) reverted, or a read/write failure.
REVERT_STATUS_MISSING_ORIGINAL = "missing_original"
REVERT_STATUS_NOT_NEEDED = "not_needed"
REVERT_STATUS_NEEDS_REVERT = "needs_revert"
REVERT_STATUS_REVERTED = "reverted"
REVERT_STATUS_ERROR = "error"

REVERT_CSV_COLUMNS = (
    "mediaFileId",
    "itemId",
    "title",
    "status",
    "width",
    "height",
    "transparentFraction",
    "nobgKey",
    "originalBase",
    "error",
)


@dataclass
class Candidate:
    media_id: int
    item_id: int | None
    title: str
    old_key: str
    source_key: str  # the largest existing variant — what is actually read


@dataclass
class ReviewRow:
    candidate: Candidate
    verdict: Verdict
    new_key: str | None = None
    error: str | None = None
    before_preview: str | None = None  # data: URI, "cut" rows only
    after_preview: str | None = None


@dataclass
class Outcome:
    already_processed: int = 0
    cut: int = 0
    cut_dark: int = 0  # subset of `cut` classified against a dark background -- see verdict_label
    applied: int = 0
    skipped_by_reason: dict[str, int] = field(default_factory=dict)
    failed: list[dict[str, Any]] = field(default_factory=list)
    rows: list[ReviewRow] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "alreadyProcessed": self.already_processed,
            "cut": self.cut,
            "cutDark": self.cut_dark,
            "applied": self.applied,
            "skippedByReason": dict(sorted(self.skipped_by_reason.items())),
            "failed": len(self.failed),
            "candidates": len(self.rows),
        }


@dataclass
class TrimReviewRow:
    candidate: Candidate
    old_size: tuple[int, int]
    new_size: tuple[int, int] | None = None  # None only while unset; equal to old_size if unchanged
    trimmed_fraction: float = 0.0
    error: str | None = None
    before_preview: str | None = None  # data: URI, only for the HTML sample
    after_preview: str | None = None


@dataclass
class TrimOutcome:
    candidates: int = 0
    unchanged: int = 0
    trimmed: int = 0
    applied: int = 0
    failed: list[dict[str, Any]] = field(default_factory=list)
    rows: list[TrimReviewRow] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "unchanged": self.unchanged,
            "trimmed": self.trimmed,
            "applied": self.applied,
            "failed": len(self.failed),
        }


@dataclass
class RevertReviewRow:
    candidate: Candidate  # source_key/old_key here are the current (-nobg) row
    original_base: str
    status: str = REVERT_STATUS_ERROR
    width: int | None = None
    height: int | None = None
    transparent_fraction: float | None = None
    error: str | None = None


@dataclass
class RevertOutcome:
    candidates: int = 0
    missing_original: int = 0
    not_needed: int = 0
    needs_revert: int = 0  # includes reverted, once --apply is used
    reverted: int = 0
    failed: list[dict[str, Any]] = field(default_factory=list)
    rows: list[RevertReviewRow] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "candidates": self.candidates,
            "missingOriginal": self.missing_original,
            "notNeeded": self.not_needed,
            "needsRevert": self.needs_revert,
            "reverted": self.reverted,
            "failed": len(self.failed),
        }


def is_already_processed(storage_key: str) -> bool:
    return f"{NOBG_MARKER}_" in storage_key


def base_of(key: str) -> str:
    """The key without its trailing `_<side>.webp`."""
    return _VARIANT_SUFFIX.sub("", key)


def original_base_of(nobg_key: str) -> str:
    """The pre-cut base key, recovered from an already-cut row's own key.

    Only meaningful for a key `is_already_processed` -- asserts the marker is
    there rather than silently returning a nonsense base for one that never
    had it.
    """
    base = base_of(nobg_key)
    assert base.endswith(NOBG_MARKER), f"{nobg_key!r} is not an already-cut key"
    return base[: -len(NOBG_MARKER)]


def largest_variant_key(storage_key: str, variants: dict[str, str] | None) -> str:
    if not variants:
        return storage_key
    return variants[str(max(int(side) for side in variants))]


def _media_query(only_ids: frozenset[int] | None) -> Select[Any]:
    via_collection = aliased(CatalogItem)
    stmt = (
        select(
            MediaFile.id,
            MediaFile.catalog_item_id,
            MediaFile.collection_item_id,
            MediaFile.storage_key,
            MediaFile.variants,
            CatalogItem.title_original,
            via_collection.title_original,
        )
        .outerjoin(CatalogItem, CatalogItem.id == MediaFile.catalog_item_id)
        .outerjoin(CollectionItem, CollectionItem.id == MediaFile.collection_item_id)
        .outerjoin(via_collection, via_collection.id == CollectionItem.catalog_item_id)
        .where(MediaFile.storage_key.is_not(None))
        .order_by(MediaFile.id)
    )
    if only_ids:
        stmt = stmt.where(MediaFile.id.in_(only_ids))
    return stmt


def _candidate_from_row(row: Any) -> Candidate:
    media_id, catalog_item_id, collection_item_id, storage_key, variants, title_a, title_b = row
    assert storage_key is not None  # the WHERE clause guarantees this
    return Candidate(
        media_id=media_id,
        item_id=catalog_item_id if catalog_item_id is not None else collection_item_id,
        title=title_a or title_b or "",
        old_key=storage_key,
        source_key=largest_variant_key(storage_key, variants),
    )


async def find_candidates(
    session: AsyncSession, *, only_ids: frozenset[int] | None
) -> tuple[list[Candidate], int]:
    """Rows not yet cut, and how many were already processed (skipped up front)."""
    candidates: list[Candidate] = []
    already_processed = 0
    for row in (await session.execute(_media_query(only_ids))).all():
        if is_already_processed(row.storage_key):
            already_processed += 1
            continue
        candidates.append(_candidate_from_row(row))
    return candidates, already_processed


async def find_trim_candidates(
    session: AsyncSession, *, only_ids: frozenset[int] | None
) -> list[Candidate]:
    """Rows already cut (storage_key carries the -nobg marker) -- the --trim universe."""
    candidates: list[Candidate] = []
    for row in (await session.execute(_media_query(only_ids))).all():
        if is_already_processed(row.storage_key):
            candidates.append(_candidate_from_row(row))
    return candidates


def is_dark_cut(verdict: Verdict) -> bool:
    return verdict.cut and (verdict.metrics or {}).get("bgKind") == "dark"


def verdict_label(verdict: Verdict) -> str:
    """The CSV/console verdict string: `cut`, `cut:dark`, or a `skip:*` reason.

    `Verdict.cut` alone does not distinguish the two -- both classify() and
    Verdict itself treat white and dark uniformly, and the split only exists
    for review purposes (dark cuts get their own CSV/HTML/console line).
    """
    if not verdict.cut:
        return verdict.reason or "skip:unknown"
    return "cut:dark" if is_dark_cut(verdict) else "cut"


def _preview_data_uri(image: Image.Image) -> str:
    preview = image.copy()
    preview.thumbnail((PREVIEW_SIDE, PREVIEW_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    preview.convert("RGBA").save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


async def _apply_cut(
    session: AsyncSession, storage: ObjectStorage, candidate: Candidate, cut_image: Image.Image
) -> str:
    """Upload the new object under a `-nobg` key and point the row at it.

    The original is never touched: it stays at its old key under the old
    role, so the CSV's oldKey/newKey pair is itself the rollback plan.
    """
    row = await session.get(MediaFile, candidate.media_id)
    assert row is not None
    sha256 = row.sha256 or hashlib.sha256(cut_image.tobytes()).hexdigest()
    processed = encode_variants(cut_image, sha256=sha256)
    new_base = base_of(candidate.old_key) + NOBG_MARKER
    new_keys = {side: variant_key(new_base, side) for side in processed.variants}
    for side, key in new_keys.items():
        storage.put(key, processed.variants[side], processed.mime_type)

    row.storage_key = primary_key_of(new_keys)
    row.thumbnail_key = preview_key_of(new_keys)
    row.variants = stored_variants(new_keys)
    row.size_bytes = processed.total_bytes
    row.width = processed.width
    row.height = processed.height
    await session.commit()
    return row.storage_key


async def process_candidates(
    session: AsyncSession,
    storage: ObjectStorage,
    candidates: Sequence[Candidate],
    *,
    apply: bool,
    log: Callable[[str], None],
) -> Outcome:
    outcome = Outcome()
    for index, candidate in enumerate(candidates, start=1):
        try:
            payload = storage.get(candidate.source_key)
            # RGBA, not RGB: classify()'s already-transparent guard needs the
            # source's real alpha channel intact. Flattening to RGB here (as
            # this used to do) throws that away before classify ever sees it
            # -- see the 2026-09 incident note on ALREADY_TRANSPARENT_FRACTION_MIN
            # in app.services.media_background.
            image = Image.open(io.BytesIO(payload)).convert("RGBA")
        except Exception as exc:  # a bad object or a storage error must not stop the run
            outcome.failed.append(
                {"mediaFileId": candidate.media_id, "key": candidate.source_key, "error": str(exc)}
            )
            continue

        verdict = classify(image)
        review_row = ReviewRow(candidate=candidate, verdict=verdict)

        if verdict.cut and verdict.mask is not None:
            outcome.cut += 1
            if is_dark_cut(verdict):
                outcome.cut_dark += 1
            cut_image = cut_background(image, verdict.mask)
            review_row.before_preview = _preview_data_uri(image)
            review_row.after_preview = _preview_data_uri(cut_image)
            if apply:
                try:
                    review_row.new_key = await _apply_cut(session, storage, candidate, cut_image)
                    outcome.applied += 1
                except Exception as exc:  # one failure must not stop the run
                    await session.rollback()
                    review_row.error = str(exc)
                    outcome.failed.append({"mediaFileId": candidate.media_id, "error": str(exc)})
        else:
            reason = verdict.reason or "skip:unknown"
            outcome.skipped_by_reason[reason] = outcome.skipped_by_reason.get(reason, 0) + 1

        outcome.rows.append(review_row)
        if index % 50 == 0 or index == len(candidates):
            log(f"backgrounds {index}/{len(candidates)}: {outcome.cut} cut so far")
    return outcome


async def _apply_trim(
    session: AsyncSession, storage: ObjectStorage, candidate: Candidate, trimmed_image: Image.Image
) -> None:
    """Re-encode the already-cut object in place, at its own (still `-nobg`) key.

    Unlike `_apply_cut`, this never introduces a new key: the pre-cut original
    is the rollback plan already, and it is untouched by this step too.
    """
    row = await session.get(MediaFile, candidate.media_id)
    assert row is not None
    sha256 = row.sha256 or hashlib.sha256(trimmed_image.tobytes()).hexdigest()
    processed = encode_variants(trimmed_image, sha256=sha256)
    base = base_of(candidate.old_key)
    new_keys = {side: variant_key(base, side) for side in processed.variants}
    for side, key in new_keys.items():
        storage.put(key, processed.variants[side], processed.mime_type)

    row.storage_key = primary_key_of(new_keys)
    row.thumbnail_key = preview_key_of(new_keys)
    row.variants = stored_variants(new_keys)
    row.size_bytes = processed.total_bytes
    row.width = processed.width
    row.height = processed.height
    await session.commit()


async def process_trim_candidates(
    session: AsyncSession,
    storage: ObjectStorage,
    candidates: Sequence[Candidate],
    *,
    apply: bool,
    log: Callable[[str], None],
) -> TrimOutcome:
    outcome = TrimOutcome(candidates=len(candidates))
    sampled = 0
    for index, candidate in enumerate(candidates, start=1):
        try:
            payload = storage.get(candidate.source_key)
            image = Image.open(io.BytesIO(payload)).convert("RGBA")
        except Exception as exc:  # a bad object or a storage error must not stop the run
            outcome.failed.append(
                {"mediaFileId": candidate.media_id, "key": candidate.source_key, "error": str(exc)}
            )
            continue

        old_size = image.size
        trimmed_image = trim_to_alpha(image)
        row = TrimReviewRow(candidate=candidate, old_size=old_size, new_size=trimmed_image.size)

        if trimmed_image.size == old_size:
            outcome.unchanged += 1
        else:
            outcome.trimmed += 1
            old_area = old_size[0] * old_size[1]
            new_area = trimmed_image.width * trimmed_image.height
            row.trimmed_fraction = 1 - (new_area / old_area) if old_area else 0.0
            if sampled < TRIM_SAMPLE_SIZE:
                row.before_preview = _preview_data_uri(image)
                row.after_preview = _preview_data_uri(trimmed_image)
                sampled += 1
            if apply:
                try:
                    await _apply_trim(session, storage, candidate, trimmed_image)
                    outcome.applied += 1
                except Exception as exc:  # one failure must not stop the run
                    await session.rollback()
                    row.error = str(exc)
                    outcome.failed.append({"mediaFileId": candidate.media_id, "error": str(exc)})

        outcome.rows.append(row)
        if index % 50 == 0 or index == len(candidates):
            log(f"trim {index}/{len(candidates)}: {outcome.trimmed} trimmed so far")
    return outcome


def _existing_original_variants(
    storage: ObjectStorage, original_base: str
) -> dict[int, tuple[str, int]]:
    """Which of the original's 300/600/1200 variants still exist, keyed by side.

    A HEAD per candidate side, not a GET: checking what survived must not
    pull a possibly-large object over the wire before it is known a revert
    is even needed. Value is (key, size in bytes) -- the size lets the row's
    size_bytes be recomputed after --apply without a further download of a
    variant this pass leaves untouched.
    """
    existing: dict[int, tuple[str, int]] = {}
    for side in VARIANT_SIDES:
        key = variant_key(original_base, side)
        size = storage.head(key)
        if size is not None:
            existing[side] = (key, size)
    return existing


async def _apply_revert(
    session: AsyncSession,
    storage: ObjectStorage,
    candidate: Candidate,
    original_base: str,
    existing: dict[int, tuple[str, int]],
    image: Image.Image,
    payload: bytes,
) -> None:
    """Point the row back at the original key, regenerating only missing sides.

    A side already present in `existing` is left untouched: re-encoding it
    from the largest surviving variant risks a byte-for-byte mismatch with a
    variant that was never actually broken, for no benefit. `-nobg` objects
    are not deleted -- cleanup is a separate, later concern; the point here
    is that the row stops pointing at them.
    """
    missing_sides = [side for side in VARIANT_SIDES if side not in existing]
    final_keys = {side: key for side, (key, _size) in existing.items()}
    size_bytes = sum(size for _key, size in existing.values())

    if missing_sides:
        sha256 = hashlib.sha256(payload).hexdigest()
        processed = encode_variants(image, sha256=sha256)
        for side in missing_sides:
            if side not in processed.variants:
                continue  # a small original legitimately never produced this side
            key = variant_key(original_base, side)
            storage.put(key, processed.variants[side], processed.mime_type)
            final_keys[side] = key
            size_bytes += len(processed.variants[side])

    row = await session.get(MediaFile, candidate.media_id)
    assert row is not None
    row.storage_key = primary_key_of(final_keys)
    row.thumbnail_key = preview_key_of(final_keys)
    row.variants = stored_variants(final_keys)
    row.size_bytes = size_bytes
    row.width = image.width
    row.height = image.height
    await session.commit()


async def process_revert_candidates(
    session: AsyncSession,
    storage: ObjectStorage,
    candidates: Sequence[Candidate],
    *,
    apply: bool,
    log: Callable[[str], None],
) -> RevertOutcome:
    """Check every already-cut row's original for the already-transparent bug, and fix it.

    `candidates` is the same already-`-nobg` universe `--trim` walks
    (`find_trim_candidates`); this reads the ORIGINAL (the key without
    `-nobg`) for each, not the cut object itself.
    """
    outcome = RevertOutcome(candidates=len(candidates))
    for index, candidate in enumerate(candidates, start=1):
        original_base = original_base_of(candidate.old_key)
        existing = _existing_original_variants(storage, original_base)
        row = RevertReviewRow(candidate=candidate, original_base=original_base)

        if not existing:
            row.status = REVERT_STATUS_MISSING_ORIGINAL
            row.error = f"no surviving original variant under {original_base}"
            outcome.missing_original += 1
            outcome.rows.append(row)
            continue

        largest_side = max(existing)
        largest_key, _size = existing[largest_side]
        try:
            payload = storage.get(largest_key)
            image = Image.open(io.BytesIO(payload)).convert("RGBA")
        except Exception as exc:  # a bad object or a storage error must not stop the run
            row.status = REVERT_STATUS_ERROR
            row.error = str(exc)
            outcome.failed.append({"mediaFileId": candidate.media_id, "error": str(exc)})
            outcome.rows.append(row)
            continue

        fraction = transparent_pixel_fraction(image)
        row.width, row.height = image.width, image.height
        row.transparent_fraction = fraction

        if fraction <= ALREADY_TRANSPARENT_FRACTION_MIN:
            row.status = REVERT_STATUS_NOT_NEEDED
            outcome.not_needed += 1
            outcome.rows.append(row)
            continue

        row.status = REVERT_STATUS_NEEDS_REVERT
        outcome.needs_revert += 1
        if apply:
            try:
                await _apply_revert(
                    session, storage, candidate, original_base, existing, image, payload
                )
                row.status = REVERT_STATUS_REVERTED
                outcome.reverted += 1
            except Exception as exc:  # one failure must not stop the run
                await session.rollback()
                row.error = str(exc)
                outcome.failed.append({"mediaFileId": candidate.media_id, "error": str(exc)})

        outcome.rows.append(row)
        if index % 50 == 0 or index == len(candidates):
            log(f"revert {index}/{len(candidates)}: {outcome.needs_revert} need reverting so far")
    return outcome


def write_revert_review_csv(path: Path, outcome: RevertOutcome) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVERT_CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.rows:
            writer.writerow(
                {
                    "mediaFileId": row.candidate.media_id,
                    "itemId": row.candidate.item_id,
                    "title": row.candidate.title,
                    "status": row.status,
                    "width": row.width if row.width is not None else "",
                    "height": row.height if row.height is not None else "",
                    "transparentFraction": (
                        f"{row.transparent_fraction:.4f}"
                        if row.transparent_fraction is not None
                        else ""
                    ),
                    "nobgKey": row.candidate.old_key,
                    "originalBase": row.original_base,
                    "error": row.error or "",
                }
            )


def write_review_csv(path: Path, outcome: Outcome) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.rows:
            metrics = row.verdict.metrics or {}
            writer.writerow(
                {
                    "mediaFileId": row.candidate.media_id,
                    "itemId": row.candidate.item_id,
                    "title": row.candidate.title,
                    "verdict": verdict_label(row.verdict),
                    "bgKind": metrics.get("bgKind", ""),
                    "borderBackgroundFraction": metrics.get("borderBackgroundFraction", ""),
                    "circularity": metrics.get("circularity", ""),
                    "cornerWhiteness": metrics.get("cornerWhiteness", ""),
                    "oldKey": row.candidate.old_key,
                    "newKey": row.new_key or "",
                    "error": row.error or "",
                }
            )


def _escape(value: object) -> str:
    return html.escape(str(value))


def _cut_cards(rows: list[ReviewRow]) -> str:
    return "\n".join(
        f"""
        <figure class="pair">
          <figcaption>#{row.candidate.media_id} — {_escape(row.candidate.title)}</figcaption>
          <div class="images">
            <img src="{row.before_preview}" alt="before">
            <div class="checker"><img src="{row.after_preview}" alt="after"></div>
          </div>
        </figure>"""
        for row in rows
    )


def write_review_html(path: Path, outcome: Outcome) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cut_rows = [row for row in outcome.rows if row.verdict.cut and not is_dark_cut(row.verdict)]
    cut_dark_rows = [row for row in outcome.rows if is_dark_cut(row.verdict)]
    skipped_rows = [row for row in outcome.rows if not row.verdict.cut]
    summary = outcome.summary()

    cards = _cut_cards(cut_rows)
    dark_cards = _cut_cards(cut_dark_rows)

    skip_rows_html = "\n".join(
        f"<tr><td>{row.candidate.media_id}</td><td>{_escape(row.candidate.title)}</td>"
        f"<td>{_escape(row.verdict.reason)}</td></tr>"
        for row in skipped_rows
    )

    html_doc = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>remove_photo_backgrounds review</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
.summary {{ margin-bottom: 2rem; }}
.pair {{ display: inline-block; margin: 0 1rem 2rem 0; text-align: center; }}
.images {{ display: flex; gap: 0.5rem; }}
.images img {{ width: 150px; height: 150px; object-fit: contain; border: 1px solid #ccc; }}
.checker {{
  background-image: linear-gradient(45deg, #ccc 25%, transparent 25%),
    linear-gradient(-45deg, #ccc 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #ccc 75%),
    linear-gradient(-45deg, transparent 75%, #ccc 75%);
  background-size: 16px 16px;
  background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
}}
table {{ border-collapse: collapse; }}
td, th {{ border: 1px solid #ccc; padding: 0.25rem 0.5rem; }}
</style></head>
<body>
<h1>remove_photo_backgrounds review</h1>
<div class="summary"><pre>{_escape(json.dumps(summary, indent=2, ensure_ascii=False))}</pre></div>
<h2>Cut ({len(cut_rows)})</h2>
{cards}
<h2>Cut, dark background ({len(cut_dark_rows)})</h2>
<p>Reviewed separately: the dark branch's flood-fill tolerance is deliberately
tight (mirrored proof fields), so a false negative is expected sooner here
than a false positive -- still worth a closer look per docs/06-media-storage.md.</p>
{dark_cards}
<h2>Skipped ({len(skipped_rows)})</h2>
<table>
<tr><th>mediaFileId</th><th>title</th><th>reason</th></tr>
{skip_rows_html}
</table>
</body></html>
"""
    path.write_text(html_doc, encoding="utf-8")


def write_trim_review_csv(path: Path, outcome: TrimOutcome) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRIM_CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.rows:
            new_size = row.new_size or row.old_size
            writer.writerow(
                {
                    "mediaFileId": row.candidate.media_id,
                    "itemId": row.candidate.item_id,
                    "title": row.candidate.title,
                    "oldWidth": row.old_size[0],
                    "oldHeight": row.old_size[1],
                    "newWidth": new_size[0],
                    "newHeight": new_size[1],
                    "trimmedFraction": f"{row.trimmed_fraction:.4f}",
                    "oldKey": row.candidate.old_key,
                    "error": row.error or "",
                }
            )


def write_trim_review_html(path: Path, outcome: TrimOutcome) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rows = [row for row in outcome.rows if row.before_preview and row.after_preview]
    summary = outcome.summary()

    cards = "\n".join(
        f"""
        <figure class="pair">
          <figcaption>#{row.candidate.media_id} — {_escape(row.candidate.title)}
            ({row.old_size[0]}x{row.old_size[1]} → {row.new_size[0]}x{row.new_size[1]},
            {row.trimmed_fraction:.0%} trimmed)</figcaption>
          <div class="images">
            <div class="checker"><img src="{row.before_preview}" alt="before"></div>
            <div class="checker"><img src="{row.after_preview}" alt="after"></div>
          </div>
        </figure>"""
        for row in sample_rows
        if row.new_size is not None
    )

    html_doc = f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<title>remove_photo_backgrounds --trim review</title>
<style>
body {{ font-family: sans-serif; margin: 2rem; }}
.summary {{ margin-bottom: 2rem; }}
.pair {{ display: inline-block; margin: 0 1rem 2rem 0; text-align: center; }}
.images {{ display: flex; gap: 0.5rem; }}
.checker {{
  background-image: linear-gradient(45deg, #ccc 25%, transparent 25%),
    linear-gradient(-45deg, #ccc 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #ccc 75%),
    linear-gradient(-45deg, transparent 75%, #ccc 75%);
  background-size: 16px 16px;
  background-position: 0 0, 0 8px, 8px -8px, -8px 0px;
}}
.checker img {{ display: block; max-width: 150px; max-height: 150px; }}
</style></head>
<body>
<h1>remove_photo_backgrounds --trim review</h1>
<div class="summary"><pre>{_escape(json.dumps(summary, indent=2, ensure_ascii=False))}</pre></div>
<h2>Sample ({len(sample_rows)} of {outcome.trimmed} trimmed)</h2>
{cards}
</body></html>
"""
    path.write_text(html_doc, encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=Path("migration-reports"))
    parser.add_argument("--apply", action="store_true", help="write cut images and update the rows")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="explicit form of the default: classify and report, write nothing",
    )
    parser.add_argument("--only-ids", help="comma-separated media_files ids to (re)run against")
    parser.add_argument("--limit", type=int, help="stop after N candidates")
    parser.add_argument(
        "--trim",
        action="store_true",
        help=(
            "re-crop already-cut (`-nobg`) rows to their alpha bbox instead of "
            "classifying new ones -- for photos cut before this margin trim existed"
        ),
    )
    parser.add_argument(
        "--revert-transparent-originals",
        action="store_true",
        help=(
            "roll back already-cut rows whose ORIGINAL was itself already "
            "transparent (the 2026-09 incident) -- checks every already-cut "
            "row's original and points the row back at it, leaving a "
            "legitimate white/dark cut untouched"
        ),
    )
    return parser.parse_args(argv)


class Progress:
    def __call__(self, message: str) -> None:
        print(message, file=sys.stderr, flush=True)


async def _run(args: argparse.Namespace, log: Progress) -> int:
    from app.core.config import get_settings
    from app.core.storage import build_s3_client
    from app.db.session import dispose_engine, get_session_factory

    only_ids = (
        frozenset(int(value) for value in args.only_ids.split(",") if value.strip())
        if args.only_ids
        else None
    )
    settings = get_settings()
    storage = ObjectStorage(build_s3_client(settings), settings.s3_bucket)

    if args.revert_transparent_originals:
        try:
            async with get_session_factory()() as session:
                candidates = await find_trim_candidates(session, only_ids=only_ids)
                batch = candidates if args.limit is None else candidates[: args.limit]
                log(f"{len(candidates)} already-cut candidates, running {len(batch)}")
                revert_outcome = await process_revert_candidates(
                    session, storage, batch, apply=args.apply, log=log
                )
        finally:
            await dispose_engine()

        args.out_dir.mkdir(parents=True, exist_ok=True)
        write_revert_review_csv(args.out_dir / "revert-review.csv", revert_outcome)
        (args.out_dir / "revert-report.json").write_text(
            json.dumps(revert_outcome.summary(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

        for line in (
            f"candidates: {revert_outcome.candidates}",
            f"missing original: {revert_outcome.missing_original}",
            f"not needed (legitimate cut): {revert_outcome.not_needed}",
            f"needs revert: {revert_outcome.needs_revert}",
            f"reverted: {revert_outcome.reverted}",
            f"failed: {len(revert_outcome.failed)}",
        ):
            print(line)
        print(f"\nreports written to {args.out_dir}")
        return EXIT_OK

    if args.trim:
        try:
            async with get_session_factory()() as session:
                candidates = await find_trim_candidates(session, only_ids=only_ids)
                batch = candidates if args.limit is None else candidates[: args.limit]
                log(f"{len(candidates)} already-cut candidates, running {len(batch)}")
                trim_outcome = await process_trim_candidates(
                    session, storage, batch, apply=args.apply, log=log
                )
        finally:
            await dispose_engine()

        args.out_dir.mkdir(parents=True, exist_ok=True)
        write_trim_review_csv(args.out_dir / "trim-review.csv", trim_outcome)
        write_trim_review_html(args.out_dir / "trim-review.html", trim_outcome)
        (args.out_dir / "trim-report.json").write_text(
            json.dumps(trim_outcome.summary(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

        for line in (
            f"candidates: {trim_outcome.candidates}",
            f"unchanged: {trim_outcome.unchanged}",
            f"trimmed: {trim_outcome.trimmed}",
            f"applied: {trim_outcome.applied}",
            f"failed: {len(trim_outcome.failed)}",
        ):
            print(line)
        print(f"\nreports written to {args.out_dir}")
        return EXIT_OK

    try:
        async with get_session_factory()() as session:
            candidates, already_processed = await find_candidates(session, only_ids=only_ids)
            batch = candidates if args.limit is None else candidates[: args.limit]
            log(
                f"{len(candidates)} candidates, {already_processed} already processed, "
                f"running {len(batch)}"
            )
            outcome = await process_candidates(session, storage, batch, apply=args.apply, log=log)
            outcome.already_processed = already_processed
    finally:
        await dispose_engine()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_review_csv(args.out_dir / "nobg-review.csv", outcome)
    write_review_html(args.out_dir / "nobg-review.html", outcome)
    (args.out_dir / "nobg-report.json").write_text(
        json.dumps(outcome.summary(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for line in (
        f"already processed: {outcome.already_processed}",
        f"cut: {outcome.cut}",
        f"  of which cut:dark: {outcome.cut_dark}",
        f"applied: {outcome.applied}",
        f"failed: {len(outcome.failed)}",
        *(f"  {reason}: {count}" for reason, count in sorted(outcome.skipped_by_reason.items())),
    ):
        print(line)
    print(f"\nreports written to {args.out_dir}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.apply and args.dry_run:
        print("--apply and --dry-run contradict each other", file=sys.stderr)
        return EXIT_USAGE
    if args.trim and args.revert_transparent_originals:
        print("--trim and --revert-transparent-originals contradict each other", file=sys.stderr)
        return EXIT_USAGE
    return asyncio.run(_run(args, Progress()))


if __name__ == "__main__":
    raise SystemExit(main())
