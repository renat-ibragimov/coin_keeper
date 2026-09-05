"""circ-photos — official circulation-coin photographs, one download per type.

A circulation record shares its look with every other record of the same
type (app/ukraine_pipeline/circ_types.py): the National Bank photographs a
denomination's design once, not once per year. This step downloads and
processes each type's obverse and reverse exactly once — fetching the "Про
монети" page it names, picking the one card among the (possibly several)
stacked on it that the type means (app/ukraine_pipeline/circ_nbu.py) — and
then stores that same pair of processed images once per catalogue record of
that type.

Storing a copy per record rather than sharing one storage key is deliberate,
not a shortcut: app/core/media_keys.py bakes the catalogue item id into every
key it hands out, so nothing here *can* point two media_files rows at one
object even if it wanted to. At roughly twenty types and a couple of hundred
records the duplication costs kilobytes, not gigabytes.

Idempotent the way app/ukraine_pipeline/photos.py already is: a record
already holding both sides from `nbu` is left alone, and its uCoin hotlink
row — never downloaded, not ours to show — is dropped the same way.

`refresh_types` is the escape hatch idempotency needs when the type map
itself changes underneath already-stored photos — the 1 hryvnia 1992/2004
split (app/ukraine_pipeline/circ_types.py) left every 2004-2017 record
holding the wrong (pre-2004) card's photo, and idempotency alone would keep
it there forever. Passing a type's key here deletes that type's existing
`nbu` images before the normal pass runs, so it re-fetches (or, for a type
`typesWithoutCard` says has no real card, correctly ends up with none) rather
than being silently skipped as "already stored". A type not named here
behaves exactly as before. Deleting is safe to do wholesale rather than
trying to single out this step's own writes: every record `_items_by_type`
offers a type is, by that same query, not NBU-linked, and app/ukraine_pipeline/
photos.py (part B) only ever writes an `nbu` image to a record its own bridge
linked to the NBU numismatic catalogue — which would make it NBU-linked too.
So a `nbu`-sourced image on one of these records can only be this step's own,
whatever type it is grouped under.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.images import ImageRejectedError, ProcessedImage, process_image
from app.core.media_keys import (
    catalog_base,
    preview_key_of,
    primary_key_of,
    stored_variants,
    variant_key,
)
from app.core.storage import ObjectStorage
from app.models import CatalogItem, Denomination, MediaFile
from app.models.enums import CollectionGroup, MediaRole, MediaSource
from app.ukraine_pipeline.catalog import nbu_linked_ids
from app.ukraine_pipeline.circ_nbu import ROLES, page_url, parse_page, pick_card
from app.ukraine_pipeline.circ_types import TYPES, CoinType, type_for
from app.ukraine_recon.http import PoliteClient, SourceUnreachableError

ATTRIBUTION = "Національний банк України"
LICENSE = "bank.gov.ua/ua/useterms: the material may be used with a reference to the source"
MAX_IMAGE_BYTES = 12 * 1024 * 1024


@dataclass
class PhotoOutcome:
    stored: int = 0
    already_stored: int = 0
    items_touched: int = 0
    types_without_card: list[str] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    removed_ucoin_rows: int = 0
    bytes_total: int = 0
    types_left: int = 0
    skipped_nbu_linked: int = 0
    refreshed_items: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "stored": self.stored,
            "alreadyStored": self.already_stored,
            "itemsTouched": self.items_touched,
            "typesWithoutCard": self.types_without_card,
            "typesLeft": self.types_left,
            "failed": len(self.failed),
            "removedUcoinRows": self.removed_ucoin_rows,
            "totalMegabytes": round(self.bytes_total / 1024 / 1024, 1),
            "skippedNbuLinked": self.skipped_nbu_linked,
            "refreshedItems": self.refreshed_items,
        }


async def _items_by_type(
    session: AsyncSession, country_id: int
) -> tuple[dict[str, list[int]], int]:
    rows = (
        await session.execute(
            select(CatalogItem.id, CatalogItem.issue_year, Denomination.value, Denomination.unit)
            .join(Denomination, Denomination.id == CatalogItem.denomination_id)
            .where(
                CatalogItem.country_id == country_id,
                CatalogItem.created_by.is_(None),
                CatalogItem.is_archived.is_(False),
                CatalogItem.collection_group == CollectionGroup.CIRCULATION,
            )
        )
    ).all()
    nbu_ids = await nbu_linked_ids(session, [item_id for item_id, *_ in rows])
    by_type: dict[str, list[int]] = {}
    skipped = 0
    for item_id, year, value, unit in rows:
        if item_id in nbu_ids:
            skipped += 1
            continue
        coin_type = type_for(value, unit, year)
        if coin_type is not None:
            by_type.setdefault(coin_type.key, []).append(item_id)
    return by_type, skipped


async def _existing_official(session: AsyncSession, item_ids: list[int]) -> set[tuple[int, str]]:
    """{(item id, role)} already holding a stored NBU image."""
    if not item_ids:
        return set()
    rows = await session.execute(
        select(MediaFile.catalog_item_id, MediaFile.role).where(
            MediaFile.catalog_item_id.in_(item_ids),
            MediaFile.storage_key.is_not(None),
            MediaFile.source == MediaSource.NBU,
        )
    )
    return {(item_id, str(role)) for item_id, role in rows.all() if item_id is not None}


async def _drop_ucoin_links(session: AsyncSession, item_ids: list[int], *, dry_run: bool) -> int:
    if not item_ids:
        return 0
    condition = (
        MediaFile.catalog_item_id.in_(item_ids),
        MediaFile.source == MediaSource.UCOIN,
        MediaFile.storage_key.is_(None),
        MediaFile.collection_item_id.is_(None),
    )
    count = len((await session.execute(select(MediaFile.id).where(*condition))).scalars().all())
    if count and not dry_run:
        await session.execute(delete(MediaFile).where(*condition))
        await session.flush()
    return count


async def _refresh_existing(
    session: AsyncSession,
    *,
    storage: ObjectStorage | None,
    item_ids: list[int],
    dry_run: bool,
    log: Callable[[str], None],
) -> int:
    """Remove `nbu` obverse/reverse images already on these items, for `refresh_types`.

    Why it is safe to take every `nbu` image on the id rather than trying to
    tell this step's own writes apart from app/ukraine_pipeline/photos.py's —
    see the module docstring. Returns the number of distinct items touched
    (or, in a dry run, that would be); no rows or objects are actually
    deleted when `dry_run` is set, matching every other step here.
    """
    if not item_ids:
        return 0
    rows = (
        (
            await session.execute(
                select(MediaFile).where(
                    MediaFile.catalog_item_id.in_(item_ids),
                    MediaFile.source == MediaSource.NBU,
                    MediaFile.role.in_([MediaRole(role) for role in ROLES]),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return 0
    touched = {row.catalog_item_id for row in rows}
    if dry_run:
        log(f"circ-refresh: would remove {len(rows)} images across {len(touched)} items")
        return len(touched)

    keys = [key for row in rows for key in (row.variants or {}).values()]
    if storage is not None:
        storage.delete_many(keys)
    for row in rows:
        await session.delete(row)
    await session.flush()
    log(f"circ-refresh: removed {len(rows)} images across {len(touched)} items")
    return len(touched)


def _download(client: PoliteClient, url: str) -> bytes | None:
    result, body = client.get_range(url, MAX_IMAGE_BYTES)
    return body or None if result.ok else None


def _fetch_type(
    client: PoliteClient, coin_type: CoinType, outcome: PhotoOutcome
) -> dict[str, ProcessedImage] | None:
    """Both sides of one type, processed once — or None if the page has neither."""
    try:
        result = client.get(page_url(coin_type.photo_slug))
    except SourceUnreachableError as exc:
        outcome.failed.append({"type": coin_type.key, "error": str(exc)})
        return None
    if not result.ok:
        outcome.failed.append({"type": coin_type.key, "error": f"HTTP {result.status}"})
        return None
    card = pick_card(parse_page(result.text), coin_type)
    if card is None or not card.images:
        outcome.types_without_card.append(coin_type.key)
        return None

    processed: dict[str, ProcessedImage] = {}
    for role in ROLES:
        url = card.images.get(role)
        if url is None:
            continue
        try:
            payload = _download(client, url)
            if payload is None:
                outcome.failed.append(
                    {"type": coin_type.key, "role": role, "url": url, "error": "not found"}
                )
                continue
            processed[role] = process_image(payload)
        except (SourceUnreachableError, ImageRejectedError, OSError) as exc:
            outcome.failed.append(
                {"type": coin_type.key, "role": role, "url": url, "error": str(exc)}
            )
    return processed or None


def _store_for_item(
    session: AsyncSession,
    *,
    storage: ObjectStorage | None,
    item_id: int,
    role: str,
    processed: ProcessedImage,
    dry_run: bool,
) -> None:
    if dry_run:
        return
    base = catalog_base(item_id, role, processed.sha256[:16])
    keys = {side: variant_key(base, side) for side in processed.variants}
    if storage is not None:
        for side, key in keys.items():
            storage.put(key, processed.variants[side], processed.mime_type)
    session.add(
        MediaFile(
            catalog_item_id=item_id,
            owner_id=None,
            role=MediaRole(role),
            source=MediaSource.NBU,
            license=LICENSE,
            attribution=ATTRIBUTION,
            storage_key=primary_key_of(keys),
            thumbnail_key=preview_key_of(keys),
            variants=stored_variants(keys),
            mime_type=processed.mime_type,
            width=processed.width,
            height=processed.height,
            size_bytes=processed.total_bytes,
            sha256=processed.sha256,
        )
    )


async def download_photos(
    session: AsyncSession,
    *,
    client: PoliteClient,
    storage: ObjectStorage | None,
    country_id: int,
    dry_run: bool,
    limit: int | None,
    log: Callable[[str], None],
    refresh_types: frozenset[str] = frozenset(),
) -> PhotoOutcome:
    outcome = PhotoOutcome()
    by_type, outcome.skipped_nbu_linked = await _items_by_type(session, country_id)
    item_ids = [item_id for ids in by_type.values() for item_id in ids]
    outcome.removed_ucoin_rows = await _drop_ucoin_links(session, item_ids, dry_run=dry_run)

    refresh_item_ids = [item_id for key in refresh_types for item_id in by_type.get(key, [])]
    outcome.refreshed_items = await _refresh_existing(
        session, storage=storage, item_ids=refresh_item_ids, dry_run=dry_run, log=log
    )

    held = await _existing_official(session, item_ids)
    if dry_run:
        # A dry run leaves the rows in place (see _refresh_existing), so
        # `held` still holds them — subtract by hand, the same set a real
        # run would have emptied, so the batch below still simulates the
        # re-fetch instead of treating a refreshed item as already done.
        held -= {(item_id, role) for item_id in refresh_item_ids for role in ROLES}

    # A type is pending if any of its items is missing a side; already_stored
    # is counted per item, up front, so an item whose type is not even in
    # `batch` (because --limit cut it, or nothing in `pending` needed it)
    # still gets credited rather than silently uncounted.
    outcome.already_stored = sum(
        1 for item_id in item_ids if all((item_id, role) in held for role in ROLES)
    )
    pending = [
        coin_type
        for coin_type in TYPES
        if by_type.get(coin_type.key)
        and any((item_id, role) not in held for item_id in by_type[coin_type.key] for role in ROLES)
    ]
    batch = pending if limit is None else pending[:limit]
    outcome.types_left = len(pending) - len(batch)

    for index, coin_type in enumerate(batch, start=1):
        processed_by_role = _fetch_type(client, coin_type, outcome)
        if not processed_by_role:
            continue
        for item_id in by_type[coin_type.key]:
            touched = False
            for role, processed in processed_by_role.items():
                if (item_id, role) in held:
                    continue
                _store_for_item(
                    session,
                    storage=storage,
                    item_id=item_id,
                    role=role,
                    processed=processed,
                    dry_run=dry_run,
                )
                outcome.stored += 1
                outcome.bytes_total += processed.total_bytes
                touched = True
            if touched:
                outcome.items_touched += 1
        log(
            f"photos {index}/{len(batch)} types, {outcome.stored} images, "
            f"{outcome.bytes_total / 1024 / 1024:.1f} MB"
        )

    if not dry_run:
        await session.flush()
    return outcome
