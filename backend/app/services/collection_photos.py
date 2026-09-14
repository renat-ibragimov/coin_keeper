"""The owner's own photos of a collection instance (docs/06-media-storage.md).

This is the one place that ever writes a `user_upload` row for a coin, and it
can only ever write one scoped to `collection_item_id` + `owner_id` — never to
`catalog_item_id`, and never to another owner's row. That is what keeps a
user's photo from ever touching a catalog record or another account's data:
the architecture, not a check here, is what makes it impossible (see the
module boundary with app.services.catalog, which never writes `user_upload`).

Modelled on app.services.avatars: same raw-bytes upload, same worker-thread
handoff for Pillow, same "write the new object, point the row at it, drop the
old one last" ordering so a failure part-way through never leaves a row
naming a key that is not in the bucket.
"""

from __future__ import annotations

from functools import lru_cache

import anyio.to_thread
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.images import process_image
from app.core.media_keys import (
    collection_base,
    preview_key_of,
    primary_key_of,
    stored_variants,
    variant_key,
)
from app.core.storage import ObjectStorage, build_s3_client
from app.models import CollectionItem, MediaFile, User
from app.models.enums import MediaRole, MediaSource
from app.repositories.media import MediaRepository
from app.services.media_urls import CatalogImages, MediaUrlBuilder

CONTENT_TYPE = "image/webp"
# Of the source, not of our encoding: twelve hex characters are plenty to tell
# one upload of the same instance and role from the next (mirrors avatars.py).
KEY_DIGEST_CHARS = 12

__all__ = ["CollectionItemNotFoundError", "CollectionPhotoService"]


@lru_cache
def _storage() -> ObjectStorage:
    settings = get_settings()
    presign_client = (
        build_s3_client(settings, endpoint_url=settings.s3_public_endpoint)
        if settings.s3_public_endpoint
        else None
    )
    return ObjectStorage(
        build_s3_client(settings), settings.s3_bucket, presign_client=presign_client
    )


class CollectionItemNotFoundError(Exception):
    """No such instance for this owner: 404, whether it is missing or someone else's."""


class CollectionPhotoService:
    def __init__(self, session: AsyncSession, storage: ObjectStorage | None = None) -> None:
        self._session = session
        self._storage = storage or _storage()

    async def set_photo(
        self, *, owner: User, item_id: int, role: MediaRole, payload: bytes
    ) -> CatalogImages:
        """Store the picture as a new row, then retire the previous one.

        The write order is the whole point (see the module docstring): the
        new object and row exist before the old row's own object is ever
        deleted, so an interruption leaves either the previous photo or an
        orphaned object — never a row pointing at a key that was never
        written.
        """
        instance = await self._owned_instance(owner, item_id)
        # Pillow's decode/resize/encode is CPU-bound; off the event loop it
        # goes, exactly like AvatarService.set_avatar.
        processed = await anyio.to_thread.run_sync(process_image, payload)

        name = processed.sha256[:KEY_DIGEST_CHARS]
        base = collection_base(owner.id, instance.id, role.value, name)
        sides = processed.processed_sides()
        keys = {side: variant_key(base, side) for side in sides}
        for side in sides:
            self._storage.put(keys[side], processed.variants[side], CONTENT_TYPE)

        previous = await self._own_row(owner, instance.id, role)
        self._session.add(
            MediaFile(
                collection_item_id=instance.id,
                owner_id=owner.id,
                role=role,
                source=MediaSource.USER_UPLOAD,
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

        if previous is not None:
            await self._retire(previous)

        return await self._images_for(owner, instance)

    async def remove_photo(self, *, owner: User, item_id: int, role: MediaRole) -> CatalogImages:
        """Clearing what is already gone is not an error, as with the avatar."""
        instance = await self._owned_instance(owner, item_id)
        existing = await self._own_row(owner, instance.id, role)
        if existing is not None:
            await self._retire(existing)
        return await self._images_for(owner, instance)

    # ------------------------------------------------------------- internals

    async def _owned_instance(self, owner: User, item_id: int) -> CollectionItem:
        """Scoped by owner, not just existence: another account's instance id
        answers not-found exactly like a missing one (docs/07-auth.md)."""
        instance = await self._session.get(CollectionItem, item_id)
        if instance is None or instance.owner_id != owner.id:
            raise CollectionItemNotFoundError
        return instance

    async def _own_row(self, owner: User, item_id: int, role: MediaRole) -> MediaFile | None:
        result = await self._session.execute(
            select(MediaFile).where(
                MediaFile.collection_item_id == item_id,
                MediaFile.owner_id == owner.id,
                MediaFile.role == role,
                MediaFile.source == MediaSource.USER_UPLOAD,
            )
        )
        return result.scalar_one_or_none()

    async def _retire(self, row: MediaFile) -> None:
        keys = {row.storage_key, row.thumbnail_key, *(row.variants or {}).values()}
        await self._session.delete(row)
        await self._session.flush()
        self._storage.delete_many([key for key in keys if key])

    async def _images_for(self, owner: User, instance: CollectionItem) -> CatalogImages:
        media = MediaRepository(self._session, user_id=owner.id)
        catalog_files = await media.visible_for_catalog_items([instance.catalog_item_id])
        own_files = await media.visible_for_collection_items([instance.id])
        return MediaUrlBuilder(self._storage).pick_catalog_images([*catalog_files, *own_files])
