from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem


class AdminProposalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_drafts(self, *, limit: int, offset: int) -> tuple[list[CatalogItem], int]:
        where = (
            CatalogItem.created_by.is_(None),
            CatalogItem.status == "draft",
            CatalogItem.is_archived.is_(False),
        )
        total = (
            await self._session.execute(select(func.count(CatalogItem.id)).where(*where))
        ).scalar_one()
        items = (
            await self._session.execute(
                select(CatalogItem)
                .where(*where)
                .order_by(CatalogItem.created_at.asc(), CatalogItem.id.asc())
                .limit(limit)
                .offset(offset)
            )
        ).scalars().all()
        return list(items), total
