from __future__ import annotations

from app.schemas.base import CamelModel
from app.schemas.catalog import CatalogCard
from app.schemas.common import Page


class AdminProposalOut(CamelModel):
    status: str
    card: CatalogCard


class AdminProposalsOut(Page[AdminProposalOut]):
    pass
