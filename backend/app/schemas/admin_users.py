"""User monitoring and role management in the admin section."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.base import CamelModel
from app.schemas.common import Page


class AdminUserSummary(CamelModel):
    total_users: int
    collectors: int


class AdminUserOut(CamelModel):
    id: int
    email: str
    display_name: str | None
    role: str
    is_active: bool
    email_verified: bool
    created_at: datetime
    coin_count: int


class AdminUsersOut(Page[AdminUserOut]):
    summary: AdminUserSummary


class AdminUserRoleIn(CamelModel):
    role: Literal["user", "admin"]
