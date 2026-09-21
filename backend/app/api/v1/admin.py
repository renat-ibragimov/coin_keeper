"""Admin section endpoints (docs/13-admin.md).

Everything here is behind the admin role. Reading job runs is the first thing
it gives: the nightly price run used to be visible only in a log file on the
server.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminUser, AppSettings, DbSession, Pagination
from app.api.errors import ProblemError
from app.models import User
from app.models.enums import UserRole
from app.repositories.admin_proposals import AdminProposalRepository
from app.repositories.admin_users import AdminUserRepository
from app.repositories.jobs import JobRunRepository
from app.schemas.admin_proposals import AdminProposalOut, AdminProposalsOut
from app.schemas.admin_users import (
    AdminUserOut,
    AdminUserRoleIn,
    AdminUsersOut,
    AdminUserSummary,
)
from app.schemas.catalog import ArchiveRequest, ArchiveStateOut, CatalogCard
from app.schemas.jobs import JobRunOut, JobRunsOut
from app.schemas.telegram import TelegramLinkOut, TelegramStatusOut
from app.services.admin_users import (
    AdminUserIneligibleError,
    AdminUserNotFoundError,
    AdminUserService,
    CannotDemoteSelfError,
    LastAdminError,
)
from app.services.catalog import CatalogService, DraftStateError, ItemNotFoundError
from app.services.telegram import BotNotConfiguredError, TelegramLinkService

router = APIRouter(prefix="/admin", tags=["admin"])


def _proposal_conflict() -> ProblemError:
    return ProblemError(
        409, "proposal-not-draft", "Conflict", "This proposal is no longer a draft."
    )


def _user_out(user: User, coin_count: int) -> AdminUserOut:
    return AdminUserOut.model_validate(
        {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role.value,
            "is_active": user.is_active,
            "email_verified": user.email_verified,
            "created_at": user.created_at,
            "coin_count": coin_count,
        }
    )


@router.get("/users")
async def list_users(session: DbSession, _: AdminUser, pagination: Pagination) -> AdminUsersOut:
    repo = AdminUserRepository(session)
    rows, total = await repo.list_users(limit=pagination.page_size, offset=pagination.offset)
    return AdminUsersOut(
        items=[_user_out(row.user, row.coin_count) for row in rows],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        summary=AdminUserSummary(total_users=total, collectors=await repo.collector_count()),
    )


@router.patch("/users/{user_id}/role")
async def set_user_role(
    session: DbSession,
    actor: AdminUser,
    user_id: int,
    payload: AdminUserRoleIn,
) -> AdminUserOut:
    try:
        user = await AdminUserService(session).set_role(
            actor=actor, user_id=user_id, role=UserRole(payload.role)
        )
    except AdminUserNotFoundError as exc:
        raise ProblemError(
            404, "admin-user-not-found", "Not found", "No user with this id."
        ) from exc
    except CannotDemoteSelfError as exc:
        raise ProblemError(
            409, "cannot-demote-self", "Conflict", "You cannot remove your own administrator role."
        ) from exc
    except LastAdminError as exc:
        raise ProblemError(
            409, "last-admin", "Conflict", "The system must keep at least one administrator."
        ) from exc
    except AdminUserIneligibleError as exc:
        raise ProblemError(
            409,
            "admin-user-ineligible",
            "Conflict",
            "Only an active user with a verified email can become an administrator.",
        ) from exc
    return _user_out(user, 0)


@router.get("/jobs")
async def list_job_runs(
    session: DbSession,
    _: AdminUser,
    pagination: Pagination,
    job: Annotated[str | None, Query()] = None,
) -> JobRunsOut:
    repo = JobRunRepository(session)
    runs, total = await repo.list_runs(
        job=job, limit=pagination.page_size, offset=pagination.offset
    )
    return JobRunsOut(
        items=[JobRunOut.model_validate(run) for run in runs],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        jobs=await repo.known_jobs(),
    )


@router.get("/jobs/{run_id}")
async def get_job_run(session: DbSession, _: AdminUser, run_id: int) -> JobRunOut:
    run = await JobRunRepository(session).get_by_id(run_id)
    if run is None:
        raise ProblemError(
            status.HTTP_404_NOT_FOUND,
            "job-run-not-found",
            "Not found",
            "No job run with this id.",
        )
    return JobRunOut.model_validate(run)


@router.get("/proposals")
async def list_proposals(
    session: DbSession, user: AdminUser, pagination: Pagination
) -> AdminProposalsOut:
    rows, total = await AdminProposalRepository(session).list_drafts(
        limit=pagination.page_size, offset=pagination.offset
    )
    service = CatalogService(session, user)
    return AdminProposalsOut(
        items=[
            AdminProposalOut(status=row.status, card=await service.get_card(row.id))
            for row in rows
        ],
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
    )


@router.post("/proposals/{item_id}/approve")
async def approve_proposal(session: DbSession, user: AdminUser, item_id: int) -> CatalogCard:
    try:
        return await CatalogService(session, user).publish_draft(item_id)
    except ItemNotFoundError as exc:
        raise ProblemError(
            404, "proposal-not-found", "Not found", "No proposal with this id."
        ) from exc
    except DraftStateError as exc:
        raise _proposal_conflict() from exc


@router.post("/proposals/{item_id}/reject")
async def reject_proposal(
    session: DbSession, user: AdminUser, item_id: int, payload: ArchiveRequest
) -> ArchiveStateOut:
    reason = payload.reason.strip()
    if not reason:
        raise ProblemError(400, "archive-reason-required", "Bad request", "A reason is required.")
    try:
        return await CatalogService(session, user).reject_draft(item_id, reason)
    except ItemNotFoundError as exc:
        raise ProblemError(
            404, "proposal-not-found", "Not found", "No proposal with this id."
        ) from exc
    except DraftStateError as exc:
        raise _proposal_conflict() from exc


@router.get("/telegram")
async def telegram_status(
    session: DbSession, user: AdminUser, settings: AppSettings
) -> TelegramStatusOut:
    chats = await TelegramLinkService(session, settings).list_chats(user)
    return TelegramStatusOut(connected=bool(chats), chats=len(chats))


@router.post("/telegram/link")
async def create_telegram_link(
    session: DbSession, user: AdminUser, settings: AppSettings
) -> TelegramLinkOut:
    """A one-time code wrapped in a t.me link. Pressing Start in that chat is
    what actually connects it (docs/13-admin.md, 2.5)."""
    try:
        url, expires_at = await TelegramLinkService(session, settings).create_link(user)
    except BotNotConfiguredError as exc:
        raise ProblemError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "telegram-not-configured",
            "Service unavailable",
            "The admin bot is not configured on this server.",
        ) from exc
    return TelegramLinkOut(url=url, expires_at=expires_at)


@router.delete("/telegram", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_telegram(session: DbSession, user: AdminUser, settings: AppSettings) -> None:
    await TelegramLinkService(session, settings).unlink(user)
