"""GET /bootstrap (docs/api.md)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from app.api.deps import CurrentUser, DbSession, RequestLocale
from app.schemas.bootstrap import BootstrapOut, SettingsOut, SettingsUpdate
from app.services.bootstrap import BootstrapService

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap")
async def bootstrap(session: DbSession, user: CurrentUser, locale: RequestLocale) -> BootstrapOut:
    return await BootstrapService(session, user, locale).bootstrap()


@router.patch("/bootstrap/settings")
async def update_settings(
    payload: SettingsUpdate,
    session: DbSession,
    user: CurrentUser,
    locale: RequestLocale,
    background_tasks: BackgroundTasks,
) -> SettingsOut:
    return await BootstrapService(session, user, locale, background_tasks).update_settings(
        **payload.model_dump(exclude_unset=True)
    )
