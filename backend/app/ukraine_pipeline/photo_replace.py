"""Storing a new obverse/reverse pair for a shared Ukrainian record, shared by
every step that ever replaces an official photo — today `roll_photos.py`'s
caller (`scripts/scan_coin_photo_packaging.py`) and `photo_upgrade.py`.

`replace_photos` only ever touches a role it is actually handed a URL for: a
partial `urls` (one side resolved, the other not) still deletes and replaces
that one side, but leaves an untouched role's photo exactly as it was rather
than deleting it with nothing to put back — "хуже, чем было, стать не может
по построению" (docs/05-integrations.md, section 12/13).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.images import MAX_SOURCE_BYTES, process_image
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
from app.ukraine_recon.http import PoliteClient

# The sources a photo is replaced out from under — media_files.source values
# that count as "the issuer's own picture", never a personal upload.
OFFICIAL_SOURCES = (MediaSource.NBU, MediaSource.UA_COINS, MediaSource.MANUAL)
ROLES = ("obverse", "reverse")


async def official_photos(session: AsyncSession, item_id: int) -> dict[str, MediaFile]:
    """{role: row} for this record's currently stored official photo(s)."""
    rows = (
        (
            await session.execute(
                select(MediaFile).where(
                    MediaFile.catalog_item_id == item_id,
                    MediaFile.source.in_(OFFICIAL_SOURCES),
                    MediaFile.storage_key.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    return {str(row.role): row for row in rows if str(row.role) in ROLES}


async def replace_photos(
    session: AsyncSession,
    *,
    storage: ObjectStorage,
    client: PoliteClient,
    item_id: int,
    urls: dict[str, str | None],
    license: str,
    attribution: str,
) -> dict[str, Any]:
    """Download and store whichever of `urls`' roles actually resolve; delete
    the old official row only for a role just replaced.

    Every stored size goes through `process_image` — the same background-cut
    guard the rest of the pipeline uses (docs/06-media-storage.md).
    """
    current = await official_photos(session, item_id)
    stored: list[str] = []
    old_keys: list[str] = []
    for role, side_url in urls.items():
        if not side_url or role not in ROLES:
            continue
        _result, payload = client.get_range(side_url, MAX_SOURCE_BYTES)
        if not payload:
            continue
        processed = process_image(payload)
        base = catalog_base(item_id, role, processed.sha256[:16])
        keys = {side: variant_key(base, side) for side in processed.variants}
        for side, key in keys.items():
            storage.put(key, processed.variants[side], processed.mime_type)
        old_row = current.get(role)
        if old_row is not None:
            old_keys.extend((old_row.variants or {}).values())
            await session.delete(old_row)
        session.add(
            MediaFile(
                catalog_item_id=item_id,
                owner_id=None,
                role=MediaRole(role),
                source=MediaSource.UA_COINS,
                license=license,
                attribution=attribution,
                storage_key=primary_key_of(keys),
                thumbnail_key=preview_key_of(keys),
                variants=stored_variants(keys),
                external_url=side_url,
                mime_type=processed.mime_type,
                width=processed.width,
                height=processed.height,
                size_bytes=processed.total_bytes,
                sha256=processed.sha256,
            )
        )
        stored.append(role)
    if old_keys:
        storage.delete_many(old_keys)
    await session.flush()
    return {
        "itemId": item_id,
        "rolesReplaced": stored,
        "oldPhotosRemoved": sum(1 for role in stored if role in current),
    }
