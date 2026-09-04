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
from app.models.enums import CollectionGroup, MetalKind, TranslationSource

collection_group_enum = ENUM(
    CollectionGroup,
    name="collection_group",
    values_callable=lambda e: [m.value for m in e],
)
metal_kind_enum = ENUM(MetalKind, name="metal_kind", values_callable=lambda e: [m.value for m in e])
translation_source_enum = ENUM(
    TranslationSource,
    name="translation_source",
    values_callable=lambda e: [m.value for m in e],
)


class Country(Base):
    """A coin issuer, past or present.

    Three name slots like every other named entity: `name_original` is the
    endonym, `name_uk` and `name_en` are the translations. `is_active` decides
    whether the country appears on the storefront (chips, the default shared
    catalogue); the personal-item form offers all of them regardless
    (docs/04-business-rules.md).
    """

    __tablename__ = "countries"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str | None] = mapped_column(Text, unique=True)
    name_original: Mapped[str] = mapped_column(Text, nullable=False)
    original_lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="uk")
    name_uk: Mapped[str | None] = mapped_column(Text)
    name_en: Mapped[str | None] = mapped_column(Text)
    collect_variants: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (UniqueConstraint("name_original", name="uq_countries_name_original"),)


class Denomination(Base):
    """A face value as structure, not as a string.

    The label ("5 копійок", "5 kopecks") is rendered per locale from
    value + unit; see app/reference_data/denominations.py. `sort_order` is the
    face value in the currency's smallest unit, which is what puts 50 копійок
    before 1 гривня; `value` breaks ties between units of equal worth
    (25 центів and ¼ долара).
    """

    __tablename__ = "denominations"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(ForeignKey("countries.id"), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    __table_args__ = (
        UniqueConstraint(
            "country_id",
            "currency_code",
            "unit",
            "value",
            name="uq_denominations_country_id_currency_code_unit_value",
        ),
    )


class Material(Base):
    """The composition dictionary behind catalog_items.composition_id.

    Seeded from what the catalogue actually contains
    (app/reference_data/materials.py), not from a general list of alloys.
    """

    __tablename__ = "materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name_uk: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str] = mapped_column(Text, nullable=False)


class CoinSeries(Base):
    __tablename__ = "coin_series"

    id: Mapped[int] = mapped_column(primary_key=True)
    country_id: Mapped[int] = mapped_column(
        ForeignKey("countries.id", ondelete="CASCADE"), nullable=False
    )
    name_original: Mapped[str] = mapped_column(Text, nullable=False)
    original_lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="uk")
    name_uk: Mapped[str | None] = mapped_column(Text)
    name_uk_source: Mapped[TranslationSource | None] = mapped_column(translation_source_enum)
    name_en: Mapped[str | None] = mapped_column(Text)
    name_en_source: Mapped[TranslationSource | None] = mapped_column(translation_source_enum)
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
    # Three language slots. title_original is the issuer's own wording in
    # original_lang and is never translated; the other two are translations and
    # each says where it came from (docs/02-data-model.md).
    title_original: Mapped[str] = mapped_column(Text, nullable=False)
    original_lang: Mapped[str] = mapped_column(Text, nullable=False, server_default="uk")
    title_uk: Mapped[str | None] = mapped_column(Text)
    title_uk_source: Mapped[TranslationSource | None] = mapped_column(translation_source_enum)
    title_en: Mapped[str | None] = mapped_column(Text)
    title_en_source: Mapped[TranslationSource | None] = mapped_column(translation_source_enum)
    issue_year: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_date: Mapped[date | None] = mapped_column(Date)
    mintage_announced: Mapped[int | None] = mapped_column(BigInteger)
    mintage_actual: Mapped[int | None] = mapped_column(BigInteger)
    composition_id: Mapped[int | None] = mapped_column(
        ForeignKey("materials.id", ondelete="SET NULL")
    )
    # What the composition parser could not read, kept verbatim rather than
    # guessed at (docs/09-data-migration.md).
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
