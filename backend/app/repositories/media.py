"""Access to media rows, restricted by provenance (docs/06-media-storage.md)."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaFile
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
