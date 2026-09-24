"""Access to media rows, restricted by provenance (docs/media.md)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectionItem, MediaFile
from app.models.enums import MediaSource

PUBLIC_SOURCES = (MediaSource.NBU, MediaSource.MANUAL, MediaSource.UA_COINS)


class MediaRepository:
    def __init__(self, session: AsyncSession, *, user_id: int) -> None:
        self._session = session
        self._user_id = user_id

    async def visible_for_catalog_items(self, item_ids: Sequence[int]) -> Sequence[MediaFile]:
        """nbu/manual/ua_coins are public; user_upload and ucoin only for their owner."""
        if not item_ids:
            return []
        result = await self._session.execute(
            select(MediaFile).where(
                MediaFile.catalog_item_id.in_(item_ids),
                or_(
                    MediaFile.source.in_(PUBLIC_SOURCES),
                    MediaFile.owner_id == self._user_id,
                ),
            )
        )
        return result.scalars().all()

    async def visible_for_collection_items(self, item_ids: Sequence[int]) -> Sequence[MediaFile]:
        """This viewer's own photos of these exact instances.

        Always `user_upload`, always this viewer's own: a collection item is
        never visible to anyone else, so there is nothing else to filter on.
        """
        if not item_ids:
            return []
        result = await self._session.execute(
            select(MediaFile).where(
                MediaFile.collection_item_id.in_(item_ids),
                MediaFile.owner_id == self._user_id,
            )
        )
        return result.scalars().all()

    async def owned_instance_media_for_catalog_items(
        self, catalog_item_ids: Sequence[int]
    ) -> Sequence[tuple[int, MediaFile]]:
        """This viewer's own instance photos of these catalog items, paired with
        which catalog item each belongs to.

        A user photo always hangs off `collection_item_id`, never off the
        catalog item it happens to be a purchase of (docs/media.md,
        "User photos belong to the collection item") — so picking it for a catalog card or a
        collection listing means joining through the owner's own
        `collection_items`, not reading `catalog_item_id` off the row.
        """
        if not catalog_item_ids:
            return []
        result = await self._session.execute(
            select(CollectionItem.catalog_item_id, MediaFile)
            .join(CollectionItem, CollectionItem.id == MediaFile.collection_item_id)
            .where(
                CollectionItem.owner_id == self._user_id,
                CollectionItem.catalog_item_id.in_(catalog_item_ids),
                MediaFile.source == MediaSource.USER_UPLOAD,
            )
        )
        return [(row[0], row[1]) for row in result.all()]
