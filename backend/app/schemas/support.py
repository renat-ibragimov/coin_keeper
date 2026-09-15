"""Public support-bot wire types."""

from __future__ import annotations

from app.schemas.base import CamelModel


class SupportLinkIn(CamelModel):
    source_path: str | None = None


class SupportLinkOut(CamelModel):
    url: str
