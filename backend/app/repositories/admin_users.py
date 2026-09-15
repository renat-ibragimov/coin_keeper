"""Queries used by the user-monitoring part of the admin section."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectionItem, User
from app.models.enums import UserRole


@dataclass(frozen=True)
class UserRow:
    user: User
    coin_count: int


class AdminUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_users(self, *, limit: int, offset: int) -> tuple[list[UserRow], int]:
        coin_counts = (
            select(
                CollectionItem.owner_id.label("owner_id"),
                func.coalesce(func.sum(CollectionItem.quantity), 0).label("coin_count"),
            )
            .group_by(CollectionItem.owner_id)
            .subquery()
        )
        statement = (
            select(User, func.coalesce(coin_counts.c.coin_count, 0))
            .outerjoin(coin_counts, coin_counts.c.owner_id == User.id)
            .order_by(User.created_at.desc(), User.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(statement)
        rows = [UserRow(user=user, coin_count=int(count)) for user, count in result.all()]
        total = int(await self._session.scalar(select(func.count()).select_from(User)) or 0)
        return rows, total

    async def collector_count(self) -> int:
        statement = select(func.count(func.distinct(CollectionItem.owner_id)))
        return int(await self._session.scalar(statement) or 0)

    async def lock_user(self, user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def lock_admins(self) -> list[User]:
        result = await self._session.execute(
            select(User).where(User.role == UserRole.ADMIN).order_by(User.id).with_for_update()
        )
        return list(result.scalars().all())
