"""GET /bootstrap (docs/03-api-contract.md)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, RequestLocale
from app.schemas.bootstrap import BootstrapOut, SettingsOut, SettingsUpdate
from app.services.bootstrap import BootstrapService

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap")
async def bootstrap(session: DbSession, user: CurrentUser, locale: RequestLocale) -> BootstrapOut:
    return await BootstrapService(session, user, locale).bootstrap()


@router.patch("/bootstrap/settings")
async def update_settings(
    payload: SettingsUpdate, session: DbSession, user: CurrentUser, locale: RequestLocale
) -> SettingsOut:
    return await BootstrapService(session, user, locale).update_settings(
        show_packaging_variants=payload.show_packaging_variants
    )
