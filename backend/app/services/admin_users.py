"""Role changes and their safety rules."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User
from app.models.enums import UserRole
from app.repositories.admin_users import AdminUserRepository


class AdminUserNotFoundError(Exception):
    pass


class CannotDemoteSelfError(Exception):
    pass


class LastAdminError(Exception):
    pass


class AdminUserIneligibleError(Exception):
    pass


class AdminUserService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AdminUserRepository(session)

    async def set_role(self, *, actor: User, user_id: int, role: UserRole) -> User:
        admins: list[User] = []
        if role == UserRole.USER:
            # Lock every current administrator in a stable order before choosing
            # the target. Concurrent demotions then cannot both observe two admins.
            admins = await self._repo.lock_admins()
            target = next((user for user in admins if user.id == user_id), None)
            target = target or await self._repo.lock_user(user_id)
        else:
            target = await self._repo.lock_user(user_id)
        if target is None:
            raise AdminUserNotFoundError(user_id)
        if target.id == actor.id and role != UserRole.ADMIN:
            raise CannotDemoteSelfError
        if target.role == role:
            return target

        if role == UserRole.ADMIN and (not target.is_active or not target.email_verified):
            raise AdminUserIneligibleError
        if target.role == UserRole.ADMIN and role != UserRole.ADMIN and len(admins) <= 1:
            raise LastAdminError

        previous = target.role
        target.role = role
        self._session.add(
            AuditLog(
                user_id=actor.id,
                action="role.promote" if role == UserRole.ADMIN else "role.demote",
                entity_type="user",
                entity_id=str(target.id),
                details={
                    "from": previous.value,
                    "to": role.value,
                    "target_email": target.email,
                },
            )
        )
        await self._session.flush()
        return target
