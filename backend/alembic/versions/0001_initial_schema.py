"""Initial schema — the whole model from docs/02-data-model.md.

Includes tables the MVP does not use yet, on purpose: creating them now means
later stages add features instead of rewriting migrations (docs/01-scope-mvp.md).

Revision ID: 0001
Revises:
Create Date: 2026-09-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ENUMS: dict[str, tuple[str, ...]] = {
    "collection_group": ("circulation", "commemorative", "collector", "other"),
    "metal_kind": ("precious", "base", "unknown"),
    "media_role": ("obverse", "reverse", "edge", "additional"),
    "media_source": ("user_upload", "ucoin", "nbu", "manual"),
    "match_status": ("suggested", "confirmed", "rejected"),
    "offer_status": (
        "considering",
        "ordered",
        "purchased",
        "rejected",
        "unavailable",
    ),
    "user_role": ("user", "admin"),
    "auth_token_kind": ("email_verify", "password_reset"),
    "expense_category": (
        "coin_purchase",
        "delivery",
        "album",
        "holder",
        "storage",
        "grading",
        "literature",
        "photo_equipment",
        "other",
    ),
}

# Tables carrying updated_at, maintained by a trigger rather than the app.
TOUCH_TABLES = (
    "users",
    "countries",
    "coin_series",
    "catalog_items",
    "collection_items",
    "sales",
    "ucoin_catalog_sources",
    "user_settings",
)


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(name=name, create_type=False)


def _timestamps() -> list[sa.Column[sa.DateTime]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    for name, values in ENUMS.items():
        rendered = ", ".join(f"'{value}'" for value in values)
        op.execute(f"CREATE TYPE {name} AS ENUM ({rendered})")

    op.execute(
        """
        CREATE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )

    # ------------------------------------------------------------- reference

    op.create_table(
        "currencies",
        sa.Column("code", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=True),
        sa.Column("decimal_places", sa.SmallInteger(), nullable=False, server_default="2"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("role", _enum("user_role"), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("locale", sa.Text(), nullable=False, server_default="uk"),
        *_timestamps(),
    )

    op.create_table(
        "countries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("code", sa.Text(), nullable=True, unique=True),
        sa.Column("name_original", sa.Text(), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("collect_variants", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        *_timestamps(),
        sa.UniqueConstraint("name_original", name="uq_countries_name_original"),
    )

    op.create_table(
        "denominations",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "country_id",
            sa.BigInteger(),
            sa.ForeignKey("countries.id", name="fk_denominations_country_id"),
            nullable=False,
        ),
        sa.Column(
            "currency_code",
            sa.Text(),
            sa.ForeignKey("currencies.code", name="fk_denominations_currency_code"),
            nullable=True,
        ),
        sa.Column("value_minor_units", sa.BigInteger(), nullable=True),
        sa.Column("label_original", sa.Text(), nullable=False),
        sa.Column("label_ru", sa.Text(), nullable=True),
        sa.Column("label_en", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.UniqueConstraint(
            "country_id",
            "label_original",
            name="uq_denominations_country_id_label_original",
        ),
    )

    op.create_table(
        "coin_series",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "country_id",
            sa.BigInteger(),
            sa.ForeignKey("countries.id", ondelete="CASCADE", name="fk_coin_series_country_id"),
            nullable=False,
        ),
        sa.Column("name_original", sa.Text(), nullable=False),
        sa.Column("name_ru", sa.Text(), nullable=True),
        sa.Column("name_en", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_year", sa.Integer(), nullable=True),
        sa.Column("end_year", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint(
            "country_id", "name_original", name="uq_coin_series_country_id_name_original"
        ),
    )

    # --------------------------------------------------------------- catalog

    op.create_table(
        "catalog_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("item_type", sa.Text(), nullable=False, server_default="coin"),
        sa.Column(
            "country_id",
            sa.BigInteger(),
            sa.ForeignKey("countries.id", name="fk_catalog_items_country_id"),
            nullable=False,
        ),
        sa.Column(
            "series_id",
            sa.BigInteger(),
            sa.ForeignKey("coin_series.id", ondelete="SET NULL", name="fk_catalog_items_series_id"),
            nullable=True,
        ),
        sa.Column(
            "denomination_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "denominations.id",
                ondelete="SET NULL",
                name="fk_catalog_items_denomination_id",
            ),
            nullable=True,
        ),
        sa.Column("collection_group", _enum("collection_group"), nullable=False),
        sa.Column("subtype", sa.Text(), nullable=True),
        sa.Column("title_original", sa.Text(), nullable=False),
        sa.Column("title_uk", sa.Text(), nullable=True),
        sa.Column("title_ru", sa.Text(), nullable=True),
        sa.Column("title_en", sa.Text(), nullable=True),
        sa.Column("issue_year", sa.Integer(), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=True),
        sa.Column("mintage_announced", sa.BigInteger(), nullable=True),
        sa.Column("mintage_actual", sa.BigInteger(), nullable=True),
        sa.Column("material", sa.Text(), nullable=True),
        sa.Column("metal_kind", _enum("metal_kind"), nullable=False, server_default="unknown"),
        sa.Column("weight_grams", sa.Numeric(10, 3), nullable=True),
        sa.Column("diameter_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("thickness_mm", sa.Numeric(8, 2), nullable=True),
        sa.Column("shape", sa.Text(), nullable=True),
        sa.Column("edge", sa.Text(), nullable=True),
        sa.Column("orientation", sa.Text(), nullable=True),
        sa.Column("catalog_km", sa.Text(), nullable=True),
        sa.Column("catalog_uc", sa.Text(), nullable=True),
        sa.Column("catalog_numista", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source_key", sa.Text(), nullable=True),
        # CASCADE, not SET NULL: deleting a user must not promote their personal
        # items into the shared catalog. docs/02-data-model.md.
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_catalog_items_created_by"),
            nullable=True,
        ),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archive_reason", sa.Text(), nullable=True),
        *_timestamps(),
    )

    # Partial indexes: the storefront always carries "NOT is_archived" verbatim.
    op.create_index(
        "ix_catalog_items_country_id_issue_year",
        "catalog_items",
        ["country_id", "issue_year"],
        postgresql_where=sa.text("NOT is_archived"),
    )
    op.create_index(
        "ix_catalog_items_series_id",
        "catalog_items",
        ["series_id"],
        postgresql_where=sa.text("NOT is_archived"),
    )
    op.create_index("ix_catalog_items_created_by", "catalog_items", ["created_by"])
    for column in ("catalog_km", "catalog_uc", "catalog_numista"):
        op.create_index(
            f"ix_catalog_items_{column}",
            "catalog_items",
            [column],
            postgresql_where=sa.text("NOT is_archived"),
        )
    op.create_index(
        "ix_catalog_items_archived_at",
        "catalog_items",
        ["archived_at"],
        postgresql_where=sa.text("is_archived"),
    )
    # Uniqueness of source_key: global for shared rows, per owner for personal
    # ones. Archived rows are deliberately NOT excluded (docs/02-data-model.md).
    op.create_index(
        "catalog_items_source_key_shared_idx",
        "catalog_items",
        ["source_key"],
        unique=True,
        postgresql_where=sa.text("source_key IS NOT NULL AND created_by IS NULL"),
    )
    op.create_index(
        "catalog_items_source_key_own_idx",
        "catalog_items",
        ["created_by", "source_key"],
        unique=True,
        postgresql_where=sa.text("source_key IS NOT NULL AND created_by IS NOT NULL"),
    )
    op.execute(
        """
        CREATE INDEX catalog_items_search_idx ON catalog_items
        USING gin (to_tsvector('simple',
            coalesce(title_original,'') || ' ' || coalesce(title_uk,'') || ' ' ||
            coalesce(title_ru,'')       || ' ' || coalesce(title_en,'')))
        WHERE NOT is_archived
        """
    )

    op.create_table(
        "catalog_variants",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="CASCADE",
                name="fk_catalog_variants_catalog_item_id",
            ),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("mint_name", sa.Text(), nullable=True),
        sa.Column("mint_mark", sa.Text(), nullable=True),
        sa.Column("variety_code", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "catalog_item_id",
            "name",
            "mint_mark",
            name="uq_catalog_variants_catalog_item_id_name_mint_mark",
        ),
    )

    # ------------------------------------------------------------ collection

    op.create_table(
        "collection_items",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_collection_items_owner_id"),
            nullable=False,
        ),
        # NO ACTION, not RESTRICT: this key is a backstop, the rule itself lives
        # in the service layer, and NO ACTION keeps the option of deferring the
        # check. docs/02-data-model.md.
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="NO ACTION",
                name="fk_collection_items_catalog_item_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "variant_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_variants.id",
                ondelete="SET NULL",
                name="fk_collection_items_variant_id",
            ),
            nullable=True,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("grade", sa.Text(), nullable=True),
        sa.Column("condition_notes", sa.Text(), nullable=True),
        sa.Column("acquisition_date", sa.Date(), nullable=True),
        sa.Column("acquisition_place", sa.Text(), nullable=True),
        sa.Column("seller", sa.Text(), nullable=True),
        sa.Column("purchase_price", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "purchase_currency",
            sa.Text(),
            sa.ForeignKey("currencies.code", name="fk_collection_items_purchase_currency"),
            nullable=True,
        ),
        sa.Column("purchase_rate_uah", sa.Numeric(14, 6), nullable=True),
        sa.Column("storage_location", sa.Text(), nullable=True),
        sa.Column("grading_company", sa.Text(), nullable=True),
        sa.Column("grading_number", sa.Text(), nullable=True),
        sa.Column("grading_grade", sa.Text(), nullable=True),
        sa.Column("is_for_swap", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_for_sale", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("needs_replacement", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_collection_items_quantity_positive"),
    )
    op.create_index(
        "ix_collection_items_owner_id_catalog_item_id",
        "collection_items",
        ["owner_id", "catalog_item_id"],
    )
    op.create_index(
        "ix_collection_items_owner_id_acquisition_date",
        "collection_items",
        ["owner_id", sa.text("acquisition_date DESC")],
    )

    op.create_table(
        "market_price_snapshots",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="CASCADE",
                name="fk_market_price_snapshots_catalog_item_id",
            ),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("grade", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "currency_code",
            sa.Text(),
            sa.ForeignKey("currencies.code", name="fk_market_price_snapshots_currency_code"),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        # NULL = central job snapshot, visible to everyone. docs/04, rule 7.
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey(
                "users.id",
                ondelete="SET NULL",
                name="fk_market_price_snapshots_created_by",
            ),
            nullable=True,
        ),
        sa.CheckConstraint("price >= 0", name="ck_market_price_snapshots_price_non_negative"),
        sa.UniqueConstraint(
            "catalog_item_id",
            "source",
            "grade",
            "observed_at",
            name="uq_market_price_snapshots_item_source_grade_observed",
        ),
    )
    op.create_index(
        "ix_market_price_snapshots_catalog_item_id_observed_at",
        "market_price_snapshots",
        ["catalog_item_id", sa.text("observed_at DESC")],
    )
    op.create_index(
        "ix_market_price_snapshots_created_by", "market_price_snapshots", ["created_by"]
    )

    op.create_table(
        "price_source_links",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="CASCADE",
                name="fk_price_source_links_catalog_item_id",
            ),
            nullable=False,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column(
            "match_status",
            _enum("match_status"),
            nullable=False,
            server_default="confirmed",
        ),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "catalog_item_id",
            "source",
            name="uq_price_source_links_catalog_item_id_source",
        ),
    )

    op.create_table(
        "media_files",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="CASCADE",
                name="fk_media_files_catalog_item_id",
            ),
            nullable=True,
        ),
        sa.Column(
            "collection_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "collection_items.id",
                ondelete="CASCADE",
                name="fk_media_files_collection_item_id",
            ),
            nullable=True,
        ),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_media_files_owner_id"),
            nullable=True,
        ),
        sa.Column("role", _enum("media_role"), nullable=False),
        # Provenance drives visibility. docs/06-media-storage.md.
        sa.Column("source", _enum("media_source"), nullable=False, server_default="user_upload"),
        sa.Column("license", sa.Text(), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=True),
        sa.Column("external_url", sa.Text(), nullable=True),
        sa.Column("thumbnail_key", sa.Text(), nullable=True),
        sa.Column("mime_type", sa.Text(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("sha256", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "catalog_item_id IS NOT NULL OR collection_item_id IS NOT NULL",
            name="ck_media_files_belongs_to_catalog_or_collection",
        ),
        sa.CheckConstraint(
            "storage_key IS NOT NULL OR external_url IS NOT NULL",
            name="ck_media_files_has_storage_key_or_external_url",
        ),
    )
    op.create_index("ix_media_files_catalog_item_id", "media_files", ["catalog_item_id"])
    op.create_index("ix_media_files_collection_item_id", "media_files", ["collection_item_id"])
    op.create_index("ix_media_files_owner_id", "media_files", ["owner_id"])

    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "currency_code",
            sa.Text(),
            sa.ForeignKey("currencies.code", name="fk_exchange_rates_currency_code"),
            nullable=False,
        ),
        sa.Column("rate_uah", sa.Numeric(14, 6), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False, server_default="NBU"),
        sa.CheckConstraint("rate_uah > 0", name="ck_exchange_rates_rate_uah_positive"),
        sa.UniqueConstraint(
            "currency_code",
            "effective_date",
            "source",
            name="uq_exchange_rates_currency_code_effective_date_source",
        ),
    )

    op.create_table(
        "expenses",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_expenses_owner_id"),
            nullable=False,
        ),
        sa.Column("category", _enum("expense_category"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "currency_code",
            sa.Text(),
            sa.ForeignKey("currencies.code", name="fk_expenses_currency_code"),
            nullable=False,
        ),
        sa.Column("rate_uah", sa.Numeric(14, 6), nullable=True),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="SET NULL",
                name="fk_expenses_catalog_item_id",
            ),
            nullable=True,
        ),
        # SET NULL is only a backstop; the service layer deletes the
        # coin_purchase expense explicitly. docs/04-business-rules.md, rule 10.
        sa.Column(
            "collection_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "collection_items.id",
                ondelete="SET NULL",
                name="fk_expenses_collection_item_id",
            ),
            nullable=True,
        ),
        sa.Column(
            "series_id",
            sa.BigInteger(),
            sa.ForeignKey("coin_series.id", ondelete="SET NULL", name="fk_expenses_series_id"),
            nullable=True,
        ),
        sa.Column("vendor", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("amount >= 0", name="ck_expenses_amount_non_negative"),
    )
    op.create_index("ix_expenses_owner_id_expense_date", "expenses", ["owner_id", "expense_date"])

    # ------------------------------------------- created now, unused in MVP

    op.create_table(
        "sales",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_sales_owner_id"),
            nullable=False,
        ),
        sa.Column(
            "collection_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "collection_items.id",
                ondelete="NO ACTION",
                name="fk_sales_collection_item_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id", ondelete="NO ACTION", name="fk_sales_catalog_item_id"
            ),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("sale_date", sa.Date(), nullable=False),
        sa.Column("buyer", sa.Text(), nullable=True),
        sa.Column("sale_price", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "sale_currency",
            sa.Text(),
            sa.ForeignKey("currencies.code", name="fk_sales_sale_currency"),
            nullable=False,
            server_default="UAH",
        ),
        sa.Column("sale_rate_uah", sa.Numeric(14, 6), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("quantity > 0", name="ck_sales_quantity_positive"),
        sa.CheckConstraint("sale_price >= 0", name="ck_sales_sale_price_non_negative"),
    )

    op.create_table(
        "purchase_offers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_purchase_offers_owner_id"),
            nullable=False,
        ),
        sa.Column(
            "catalog_item_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "catalog_items.id",
                ondelete="CASCADE",
                name="fk_purchase_offers_catalog_item_id",
            ),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "currency_code",
            sa.Text(),
            sa.ForeignKey("currencies.code", name="fk_purchase_offers_currency_code"),
            nullable=False,
        ),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("seller", sa.Text(), nullable=True),
        sa.Column("found_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _enum("offer_status"), nullable=False, server_default="considering"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("price >= 0", name="ck_purchase_offers_price_non_negative"),
    )

    op.create_table(
        "collection_goals",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_collection_goals_owner_id"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "country_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "countries.id",
                ondelete="CASCADE",
                name="fk_collection_goals_country_id",
            ),
            nullable=True,
        ),
        sa.Column(
            "series_id",
            sa.BigInteger(),
            sa.ForeignKey(
                "coin_series.id",
                ondelete="CASCADE",
                name="fk_collection_goals_series_id",
            ),
            nullable=True,
        ),
        sa.Column("collection_group", _enum("collection_group"), nullable=True),
        sa.Column("year_from", sa.Integer(), nullable=True),
        sa.Column("year_to", sa.Integer(), nullable=True),
        sa.Column("denomination_ids", postgresql.JSONB(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ----------------------------------------------------- per-user settings

    op.create_table(
        "ucoin_catalog_sources",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "owner_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_ucoin_catalog_sources_owner_id"),
            nullable=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("collection_group", _enum("collection_group"), nullable=True),
        sa.Column("last_import_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_inserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_skipped", sa.Integer(), nullable=False, server_default="0"),
        *_timestamps(),
    )
    op.create_index(
        "uq_ucoin_catalog_sources_owner_id_url",
        "ucoin_catalog_sources",
        ["owner_id", "url"],
        unique=True,
    )

    op.create_table(
        "user_settings",
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_settings_user_id"),
            primary_key=True,
        ),
        sa.Column("locale", sa.Text(), nullable=False, server_default="uk"),
        sa.Column("display_currency", sa.Text(), nullable=False, server_default="UAH"),
        sa.Column("default_grade_commemorative", sa.Text(), nullable=False, server_default="UNC"),
        sa.Column("default_grade_circulation", sa.Text(), nullable=False, server_default="VF"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ------------------------------------------------------ sessions, tokens

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_tokens_user_id"),
            nullable=False,
        ),
        # sha256 of the token, never the token itself. docs/07-auth.md.
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_auth_tokens_user_id"),
            nullable=False,
        ),
        sa.Column("kind", _enum("auth_token_kind"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_auth_tokens_user_id_kind", "auth_tokens", ["user_id", "kind"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column(
            "user_id",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_audit_log_user_id"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    for table in TOUCH_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_set_updated_at BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
        )


def downgrade() -> None:
    for table in TOUCH_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {table}_set_updated_at ON {table}")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")

    for table in (
        "audit_log",
        "auth_tokens",
        "refresh_tokens",
        "user_settings",
        "ucoin_catalog_sources",
        "collection_goals",
        "purchase_offers",
        "sales",
        "expenses",
        "exchange_rates",
        "media_files",
        "price_source_links",
        "market_price_snapshots",
        "collection_items",
        "catalog_variants",
        "catalog_items",
        "coin_series",
        "denominations",
        "countries",
        "users",
        "currencies",
    ):
        op.drop_table(table)

    for name in ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {name}")
