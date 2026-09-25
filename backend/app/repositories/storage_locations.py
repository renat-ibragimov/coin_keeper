"""Data access for the storage-location dictionary (docs/data-model.md)."""

from __future__ import annotations

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StorageLocation


class StorageLocationRepository:
    def __init__(self, session: AsyncSession, *, owner_id: int) -> None:
        self._session = session
        self._owner_id = owner_id

    def _visible(self) -> ColumnElement[bool]:
        return or_(StorageLocation.owner_id.is_(None), StorageLocation.owner_id == self._owner_id)

    async def list_visible(self) -> list[StorageLocation]:
        # Presets (owner_id IS NULL) first, in the order they were seeded;
        # the owner's own entries after, in the order they were created.
        result = await self._session.execute(
            select(StorageLocation)
            .where(self._visible())
            .order_by(StorageLocation.owner_id.is_not(None), StorageLocation.id)
        )
        return list(result.scalars().all())

    async def find_by_name(self, name: str) -> StorageLocation | None:
        needle = name.strip().lower()
        result = await self._session.execute(
            select(StorageLocation).where(
                self._visible(),
                or_(
                    func.lower(StorageLocation.name_uk) == needle,
                    func.lower(StorageLocation.name_en) == needle,
                    func.lower(StorageLocation.name_original) == needle,
                ),
            )
        )
        return result.scalars().first()

    async def get(self, location_id: int) -> StorageLocation | None:
        return await self._session.get(StorageLocation, location_id)

    async def add(self, location: StorageLocation) -> StorageLocation:
        self._session.add(location)
        await self._session.flush()
        return location

    async def delete(self, location: StorageLocation) -> None:
        await self._session.delete(location)
        await self._session.flush()
