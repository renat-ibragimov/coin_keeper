"""Market prices and external source links."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    desc,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import MatchStatus


class MarketPriceSnapshot(Base):
    """Append-only price history.

    created_by decides visibility: NULL is a central job snapshot visible to
    everyone, a value is the author's own. See docs/04-business-rules.md, rule 7.
    """

    __tablename__ = "market_price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    grade: Mapped[str | None] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Set by the legacy migration for snapshots that fail the price checks.
    # They stay in the history but are excluded from collection value.
    # See docs/09-data-migration.md and docs/05-integrations.md.
    is_suspect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    __table_args__ = (
        CheckConstraint("price >= 0", name="price_non_negative"),
        UniqueConstraint(
            "catalog_item_id",
            "source",
            "grade",
            "observed_at",
            name="uq_market_price_snapshots_item_source_grade_observed",
        ),
        Index(
            "ix_market_price_snapshots_catalog_item_id_observed_at",
            "catalog_item_id",
            desc("observed_at"),
        ),
        Index("ix_market_price_snapshots_created_by", "created_by"),
        Index(
            "ix_market_price_snapshots_suspect",
            "catalog_item_id",
            postgresql_where=text("is_suspect"),
        ),
    )


class PriceSourceLink(Base):
    __tablename__ = "price_source_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    match_status: Mapped[MatchStatus] = mapped_column(
        ENUM(MatchStatus, name="match_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=MatchStatus.CONFIRMED.value,
    )
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "catalog_item_id", "source", name="uq_price_source_links_catalog_item_id_source"
        ),
    )
