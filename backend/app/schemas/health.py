"""Health check payload."""

from __future__ import annotations

from typing import Literal

from app.schemas.base import CamelModel


class ComponentHealth(CamelModel):
    status: Literal["ok", "error"]
    detail: str | None = None


class HealthOut(CamelModel):
    status: Literal["ok", "degraded"]
    database: ComponentHealth
    redis: ComponentHealth
    storage: ComponentHealth
