"""Storage-location dictionary: a handful of system presets plus whatever
each owner types the first time (docs/04-business-rules.md).

Never a direct CRUD resource for the client: a name typed into the purchase
form or into settings is resolved here, transparently creating a personal
entry the first time it is seen. Translation into the language the owner
didn't type happens in the background (BackgroundTasks, not a queue — see
translate_in_background()) so saving a purchase never waits on an LLM call.
"""

from __future__ import annotations

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.locale import DEFAULT_LOCALE
from app.db.session import get_session_factory
from app.models import StorageLocation
from app.models.enums import TranslationSource
from app.repositories.storage_locations import StorageLocationRepository
from app.schemas.collection import StorageLocationOut
from app.services.translation import TranslationResult, translate_short_phrase


class StorageLocationNotFoundError(Exception):
    pass


class StorageLocationForbiddenError(Exception):
    """Raised for a preset (owner_id IS NULL): shared across every account,
    so no single user can delete one (docs/04-business-rules.md — the same
    read-only-shared-record rule as the catalog, applied to this dictionary)."""


def _name(location: StorageLocation, locale: str) -> str:
    return location.name_uk if locale == "uk" else location.name_en


class StorageLocationService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        owner_id: int,
        locale: str = DEFAULT_LOCALE,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
        self._repo = StorageLocationRepository(session, owner_id=owner_id)
        self._owner_id = owner_id
        self._locale = locale
        self._background_tasks = background_tasks

    async def list_locations(self) -> list[StorageLocationOut]:
        locations = await self._repo.list_visible()
        return [
            StorageLocationOut(
                name=_name(location, self._locale), custom=location.owner_id is not None
            )
            for location in locations
        ]

    async def name_for(self, location_id: int | None) -> str | None:
        if location_id is None:
            return None
        location = await self._repo.get(location_id)
        return None if location is None else _name(location, self._locale)

    async def add(self, name: str) -> StorageLocationOut:
        """Explicit "add to my list" from the settings page — the same
        find-or-create as resolve(), just returning the full row instead of
        an id, for a UI that shows what it just added."""
        location = await self._find_or_create(name)
        assert location is not None  # add() never receives a blank name (schema min_length=1)
        return StorageLocationOut(
            name=_name(location, self._locale), custom=location.owner_id is not None
        )

    async def delete(self, name: str) -> None:
        location = await self._repo.find_by_name(name)
        if location is None:
            raise StorageLocationNotFoundError(name)
        if location.owner_id is None:
            raise StorageLocationForbiddenError(name)
        await self._repo.delete(location)

    async def resolve(self, name: str | None) -> int | None:
        """Find-or-create by name, trimmed and matched case-insensitively
        against presets and this owner's own locations. A brand-new one
        starts out with both language slots holding the typed text verbatim
        and is queued for background translation."""
        location = await self._find_or_create(name)
        return None if location is None else location.id

    async def _find_or_create(self, name: str | None) -> StorageLocation | None:
        if name is None:
            return None
        trimmed = name.strip()
        if not trimmed:
            return None

        existing = await self._repo.find_by_name(trimmed)
        if existing is not None:
            return existing

        location = await self._repo.add(
            StorageLocation(
                owner_id=self._owner_id,
                name_original=trimmed,
                name_uk=trimmed,
                name_uk_source=TranslationSource.MANUAL,
                name_en=trimmed,
                name_en_source=TranslationSource.MANUAL,
            )
        )
        if self._background_tasks is not None and get_settings().anthropic_api_key:
            self._background_tasks.add_task(translate_in_background, location.id)
        return location


def apply_translation(location: StorageLocation, result: TranslationResult) -> None:
    """The detected language's own slot stays exactly what the owner typed --
    only the other one is filled in by the model. Pure and DB-free on
    purpose, so the one part of this feature with real judgment calls
    (which slot to touch) is testable without a database."""
    if result.language != "uk":
        location.name_uk = result.name_uk
        location.name_uk_source = TranslationSource.LLM
    if result.language != "en":
        location.name_en = result.name_en
        location.name_en_source = TranslationSource.LLM


async def translate_in_background(location_id: int) -> None:
    """The BackgroundTasks entry point: opens its own session, since the
    request's session is long gone by the time this runs."""
    api_key = get_settings().anthropic_api_key
    if not api_key:
        return
    async with get_session_factory()() as session:
        try:
            location = await session.get(StorageLocation, location_id)
            if location is None:
                return
            result = await translate_short_phrase(location.name_original, api_key)
            if result is None:
                return
            apply_translation(location, result)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
