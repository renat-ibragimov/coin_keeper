"""photos — official images, downloaded once and kept as ours.

The National Bank is the first source: its 1600 px PNGs are the issuer's own
photographs. Where it has none, ua-coins.info serves a 600 px WebP, which is
the largest that site really has — its "big" directory is 198 px.

The originals are not kept. A card's PNG is three to four megabytes; it is
fetched, re-encoded to our three sizes and dropped. What lives on disk and in
MinIO is only our WebP.

Provenance travels with the file: media_files.source says who took the picture
and attribution says whom to credit, because storing someone's image is not the
same as owning it (docs/06-media-storage.md).

The uCoin links on Ukrainian records go: their images were never downloaded,
they are not ours to show, and the National Bank now covers the same coins.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.images import ImageRejectedError, process_image
from app.core.media_keys import (
    catalog_base,
    preview_key_of,
    primary_key_of,
    stored_variants,
    variant_key,
)
from app.core.storage import ObjectStorage
from app.models import MediaFile
from app.models.enums import MediaRole, MediaSource
from app.ukraine_pipeline.sources import Sources, nbu_sides, nbu_thumbnails, ua_coins_sides
from app.ukraine_recon.http import PoliteClient, SourceUnreachableError
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS
from app.ukraine_recon.triangulate import Cluster

ROLES = ("obverse", "reverse")
ATTRIBUTION = {
    MediaSource.NBU: "Національний банк України",
    MediaSource.UA_COINS: "ua-coins.info",
}
LICENSE = {
    MediaSource.NBU: (
        "bank.gov.ua/ua/useterms: the material may be used with a reference to the source"
    ),
    MediaSource.UA_COINS: "ua-coins.info, © 2015-2026, used with attribution",
}


@dataclass
class PhotoOutcome:
    stored: int = 0
    already_stored: int = 0
    from_nbu: int = 0
    from_ua_coins: int = 0
    without_source: list[int] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    removed_ucoin_rows: int = 0
    bytes_by_side: dict[int, int] = field(default_factory=dict)
    items_done: int = 0
    items_left: int = 0

    @property
    def total_bytes(self) -> int:
        return sum(self.bytes_by_side.values())

    def summary(self) -> dict[str, Any]:
        return {
            "stored": self.stored,
            "alreadyStored": self.already_stored,
            "fromNbu": self.from_nbu,
            "fromUaCoins": self.from_ua_coins,
            "itemsWithoutAnyImage": len(self.without_source),
            "itemsDone": self.items_done,
            "itemsLeft": self.items_left,
            "failed": len(self.failed),
            "removedUcoinRows": self.removed_ucoin_rows,
            "bytesBySide": {str(side): value for side, value in sorted(self.bytes_by_side.items())},
            "totalBytes": self.total_bytes,
            "totalMegabytes": round(self.total_bytes / 1024 / 1024, 1),
        }


def image_urls(cluster: Cluster) -> tuple[MediaSource, dict[str, str]] | None:
    """Where to take the two sides from.

    The issuer's own full-size photograph first — but only 389 of the 1048
    cards have one. For the rest ua-coins serves 600 px, which is three times
    the 198 px preview the NBU card offers, and that preview is the last
    resort rather than the second choice.
    """
    nbu_record = cluster.record_of(SOURCE_NBU)
    if nbu_record is not None:
        sides = nbu_sides(nbu_record)
        if sides:
            return MediaSource.NBU, sides
    ua_record = cluster.record_of(SOURCE_UA_COINS)
    if ua_record is not None and ua_record.source_id.isdigit():
        return MediaSource.UA_COINS, ua_coins_sides(ua_record)
    if nbu_record is not None:
        previews = nbu_thumbnails(nbu_record)
        if previews:
            return MediaSource.NBU, previews
    return None


async def existing_official(
    session: AsyncSession, item_ids: list[int]
) -> dict[tuple[int, str], str]:
    """{(item id, role): sha256} for images we already hold from a source."""
    if not item_ids:
        return {}
    rows = await session.execute(
        select(MediaFile.catalog_item_id, MediaFile.role, MediaFile.sha256).where(
            MediaFile.catalog_item_id.in_(item_ids),
            MediaFile.storage_key.is_not(None),
            MediaFile.source.in_((MediaSource.NBU, MediaSource.UA_COINS)),
        )
    )
    return {
        (item_id, str(role)): sha or "" for item_id, role, sha in rows.all() if item_id is not None
    }


async def drop_ucoin_links(session: AsyncSession, item_ids: list[int], *, dry_run: bool) -> int:
    """Remove the uCoin hotlink rows of the Ukrainian records.

    Only rows with no file of ours behind them — a link we never downloaded and
    may not show. Nothing outside this country's records is touched, and no
    collection photo is: those belong to their owner.
    """
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


async def download_photos(
    session: AsyncSession,
    *,
    client: PoliteClient,
    storage: ObjectStorage | None,
    pairs: dict[int, Cluster],
    sources: Sources,
    dry_run: bool,
    limit: int | None,
    log: Callable[[str], None],
) -> PhotoOutcome:
    """`pairs` is {catalog item id: its cluster}, from the bridge step."""
    outcome = PhotoOutcome()
    item_ids = list(pairs)
    outcome.removed_ucoin_rows = await drop_ucoin_links(session, item_ids, dry_run=dry_run)
    held = await existing_official(session, item_ids)

    pending = [
        (item_id, cluster)
        for item_id, cluster in pairs.items()
        if any((item_id, role) not in held for role in ROLES)
    ]
    outcome.already_stored = len(item_ids) - len(pending)
    batch = pending if limit is None else pending[:limit]
    outcome.items_left = len(pending) - len(batch)

    for index, (item_id, cluster) in enumerate(batch, start=1):
        chosen = image_urls(cluster)
        if chosen is None:
            outcome.without_source.append(item_id)
            continue
        provenance, urls = chosen
        for role in ROLES:
            if (item_id, role) in held or role not in urls:
                continue
            await _store_one(
                session,
                storage=storage,
                client=client,
                item_id=item_id,
                role=role,
                url=urls[role],
                provenance=provenance,
                outcome=outcome,
                dry_run=dry_run,
            )
        outcome.items_done += 1
        if index % 25 == 0 or index == len(batch):
            log(
                f"photos {index}/{len(batch)} items, {outcome.stored} images,"
                f" {outcome.total_bytes / 1024 / 1024:.1f} MB"
            )
    if not dry_run:
        await session.flush()
    return outcome


async def _store_one(
    session: AsyncSession,
    *,
    storage: ObjectStorage | None,
    client: PoliteClient,
    item_id: int,
    role: str,
    url: str,
    provenance: MediaSource,
    outcome: PhotoOutcome,
    dry_run: bool,
) -> None:
    try:
        payload = _download(client, url)
    except (SourceUnreachableError, OSError) as exc:
        outcome.failed.append({"itemId": item_id, "role": role, "url": url, "error": str(exc)})
        return
    if payload is None:
        outcome.failed.append({"itemId": item_id, "role": role, "url": url, "error": "not found"})
        return
    try:
        processed = process_image(payload)
    except ImageRejectedError as exc:
        outcome.failed.append({"itemId": item_id, "role": role, "url": url, "error": str(exc)})
        return

    outcome.stored += 1
    if provenance is MediaSource.NBU:
        outcome.from_nbu += 1
    else:
        outcome.from_ua_coins += 1
    for side, body in processed.variants.items():
        outcome.bytes_by_side[side] = outcome.bytes_by_side.get(side, 0) + len(body)
    if dry_run:
        return

    # Only the sizes actually produced: a 600 px source has no 1200 px form.
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
            source=provenance,
            license=LICENSE[provenance],
            attribution=ATTRIBUTION[provenance],
            storage_key=primary_key_of(keys),
            thumbnail_key=preview_key_of(keys),
            variants=stored_variants(keys),
            # The source URL is kept as the reference to the first publisher,
            # not as something the page ever loads (docs/06-media-storage.md).
            external_url=url,
            mime_type=processed.mime_type,
            width=processed.width,
            height=processed.height,
            size_bytes=processed.total_bytes,
            sha256=processed.sha256,
        )
    )


MAX_IMAGE_BYTES = 12 * 1024 * 1024


def _download(client: PoliteClient, url: str) -> bytes | None:
    """The file, capped at what the processor would accept anyway.

    The polite client caches by URL, so a second run over the same coins costs
    no traffic — which is what makes --limit and --resume usable against eight
    gigabytes of PNG.
    """
    result, body = client.get_range(url, MAX_IMAGE_BYTES)
    if not result.ok:
        return None
    return body or None
