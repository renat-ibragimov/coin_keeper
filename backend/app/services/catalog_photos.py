"""Administrator-managed public catalogue photos."""

from __future__ import annotations

from functools import lru_cache

import anyio.to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.images import process_image
from app.core.media_keys import (
    catalog_base,
    preview_key_of,
    primary_key_of,
    stored_variants,
    variant_key,
)
from app.core.storage import ObjectStorage, build_s3_client
from app.models import CatalogItem, MediaFile
from app.models.enums import MediaRole, MediaSource

CONTENT_TYPE = "image/webp"


@lru_cache
def _storage() -> ObjectStorage:
    settings = get_settings()
    presign = (
        build_s3_client(settings, endpoint_url=settings.s3_public_endpoint)
        if settings.s3_public_endpoint
        else None
    )
    return ObjectStorage(build_s3_client(settings), settings.s3_bucket, presign_client=presign)


class CatalogPhotoNotFoundError(Exception):
    pass


class CatalogPhotoService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage | None = None) -> None:
        self._session = session
        self._storage = storage or _storage()

    async def set_photo(self, item_id: int, role: MediaRole, payload: bytes) -> None:
        await self._item(item_id)
        processed = await anyio.to_thread.run_sync(process_image, payload)
        base = catalog_base(item_id, role.value, processed.sha256[:12])
        keys = {side: variant_key(base, side) for side in processed.processed_sides()}
        for side, key in keys.items():
            self._storage.put(key, processed.variants[side], CONTENT_TYPE)
        previous = await self._rows(item_id, role)
        self._session.add(
            MediaFile(
                catalog_item_id=item_id,
                role=role,
                source=MediaSource.MANUAL,
                storage_key=primary_key_of(keys),
                thumbnail_key=preview_key_of(keys),
                variants=stored_variants(keys),
                mime_type=processed.mime_type,
                width=processed.width,
                height=processed.height,
                size_bytes=processed.size_bytes,
                sha256=processed.sha256,
            )
        )
        await self._session.flush()
        for row in previous:
            await self._retire(row)

    async def remove_photo(self, item_id: int, role: MediaRole) -> None:
        await self._item(item_id)
        for row in await self._rows(item_id, role):
            await self._retire(row)

    async def _item(self, item_id: int) -> CatalogItem:
        item = await self._session.get(CatalogItem, item_id)
        if item is None or item.created_by is not None:
            raise CatalogPhotoNotFoundError
        return item

    async def _rows(self, item_id: int, role: MediaRole) -> list[MediaFile]:
        rows = list(
            (
                await self._session.execute(
                    select(MediaFile)
                    .where(
                        MediaFile.catalog_item_id == item_id,
                        MediaFile.role == role,
                        MediaFile.source.in_(
                            (MediaSource.NBU, MediaSource.MANUAL, MediaSource.UA_COINS)
                        ),
                    )
                    .order_by(MediaFile.id.desc())
                )
            )
            .scalars()
            .all()
        )
        return rows

    async def _retire(self, row: MediaFile) -> None:
        keys = {row.storage_key, row.thumbnail_key, *(row.variants or {}).values()}
        await self._session.delete(row)
        await self._session.flush()
        self._storage.delete_many([key for key in keys if key])
