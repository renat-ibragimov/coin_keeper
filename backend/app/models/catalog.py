"""Shared catalog: reference data and coin issues.

A catalog_items row belongs to one of two layers, decided by created_by:
NULL is a shared record (admin and system jobs only), a value is the author's
personal item. See docs/04-business-rules.md, rule 2.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, updated_at_column
from app.models.enums import CollectionGroup, MetalKind

collection_group_enum = ENUM(
    CollectionGroup,
    name="collection_group",
    values_callable=lambda e: [m.value for m in e],
)
metal_kind_enum = ENUM(MetalKind, name="metal_kind", values_callable=lambda e: [m.value for m in e])


class Country(Base):
    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(Text, unique=True)
    name_original: Mapped[str] = mapped_column(Text, nullable=False)
    name_ru: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    collect_variants: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (UniqueConstraint("name_original", name="uq_countries_name_original"),)


class Denomination(Base):
    __tablename__ = "denominations"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    currency_code: Mapped[str | None] = mapped_column(ForeignKey("currencies.code"))
    value_minor_units: Mapped[int | None] = mapped_column(BigInteger)
    label_original: Mapped[str] = mapped_column(Text, nullable=False)
    label_ru: Mapped[str | None] = mapped_column(Text)
    label_en: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    __table_args__ = (
        UniqueConstraint(
            "country_id", "label_original", name="uq_denominations_country_id_label_original"
        ),
    )


class CoinSeries(Base):
    __tablename__ = "coin_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(
        ForeignKey("countries.id", ondelete="CASCADE"), nullable=False
    )
    name_original: Mapped[str] = mapped_column(Text, nullable=False)
    name_ru: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    start_year: Mapped[int | None] = mapped_column(Integer)
    end_year: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        UniqueConstraint(
            "country_id", "name_original", name="uq_coin_series_country_id_name_original"
        ),
    )


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_type: Mapped[str] = mapped_column(
        Text, nullable=False, default="coin", server_default="coin"
    )
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    series_id: Mapped[int | None] = mapped_column(ForeignKey("coin_series.id", ondelete="SET NULL"))
    denomination_id: Mapped[int | None] = mapped_column(
        ForeignKey("denominations.id", ondelete="SET NULL")
    )
    collection_group: Mapped[CollectionGroup] = mapped_column(collection_group_enum, nullable=False)
    subtype: Mapped[str | None] = mapped_column(Text)
    title_original: Mapped[str] = mapped_column(Text, nullable=False)
    title_uk: Mapped[str | None] = mapped_column(Text)
    title_ru: Mapped[str | None] = mapped_column(Text)
    title_en: Mapped[str | None] = mapped_column(Text)
    issue_year: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date)
    mintage_announced: Mapped[int | None] = mapped_column(BigInteger)
    mintage_actual: Mapped[int | None] = mapped_column(BigInteger)
    material: Mapped[str | None] = mapped_column(Text)
    metal_kind: Mapped[MetalKind] = mapped_column(
        metal_kind_enum,
        nullable=False,
        default=MetalKind.UNKNOWN,
        server_default=MetalKind.UNKNOWN.value,
    )
    weight_grams: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    diameter_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    thickness_mm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    shape: Mapped[str | None] = mapped_column(Text)
    edge: Mapped[str | None] = mapped_column(Text)
    orientation: Mapped[str | None] = mapped_column(Text)
    catalog_km: Mapped[str | None] = mapped_column(Text)
    catalog_uc: Mapped[str | None] = mapped_column(Text)
    catalog_numista: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    source_key: Mapped[str | None] = mapped_column(Text)
    # CASCADE, not SET NULL: deleting a user must not silently promote their
    # personal items into the shared catalog. See docs/02-data-model.md.
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    # Partial indexes: nearly every query carries "NOT is_archived" verbatim.
    __table_args__ = (
        Index(
            "ix_catalog_items_country_id_issue_year",
            "country_id",
            "issue_year",
            postgresql_where=text("NOT is_archived"),
        ),
        Index(
            "ix_catalog_items_series_id",
            "series_id",
            postgresql_where=text("NOT is_archived"),
        ),
        Index("ix_catalog_items_created_by", "created_by"),
        Index(
            "ix_catalog_items_catalog_km",
            "catalog_km",
            postgresql_where=text("NOT is_archived"),
        ),
        Index(
            "ix_catalog_items_catalog_uc",
            "catalog_uc",
            postgresql_where=text("NOT is_archived"),
        ),
        Index(
            "ix_catalog_items_catalog_numista",
            "catalog_numista",
            postgresql_where=text("NOT is_archived"),
        ),
        Index(
            "ix_catalog_items_archived_at",
            "archived_at",
            postgresql_where=text("is_archived"),
        ),
        Index(
            "catalog_items_source_key_shared_idx",
            "source_key",
            unique=True,
            postgresql_where=text("source_key IS NOT NULL AND created_by IS NULL"),
        ),
        Index(
            "catalog_items_source_key_own_idx",
            "created_by",
            "source_key",
            unique=True,
            postgresql_where=text("source_key IS NOT NULL AND created_by IS NOT NULL"),
        ),
    )


class CatalogVariant(Base):
    """Created now, unused in the MVP (docs/01-scope-mvp.md)."""

    __tablename__ = "catalog_variants"

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    mint_name: Mapped[str | None] = mapped_column(Text)
    mint_mark: Mapped[str | None] = mapped_column(Text)
    variety_code: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "catalog_item_id",
            "name",
            "mint_mark",
            name="uq_catalog_variants_catalog_item_id_name_mint_mark",
        ),
    )


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    rate_uah: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False, default="NBU", server_default="NBU")

    __table_args__ = (
        CheckConstraint("rate_uah > 0", name="rate_uah_positive"),
        UniqueConstraint(
            "currency_code",
            "effective_date",
            "source",
            name="uq_exchange_rates_currency_code_effective_date_source",
        ),
    )
