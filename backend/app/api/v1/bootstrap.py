"""GET /bootstrap (docs/03-api-contract.md)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.bootstrap import BootstrapOut
from app.services.bootstrap import BootstrapService

router = APIRouter(tags=["bootstrap"])


@router.get("/bootstrap")
async def bootstrap(session: DbSession, user: CurrentUser) -> BootstrapOut:
    return await BootstrapService(session, user).bootstrap()
