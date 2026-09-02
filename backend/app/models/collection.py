"""Personal data: collection items, expenses and the deferred MVP tables."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    desc,
)
from sqlalchemy.dialects.postgresql import ENUM, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column, updated_at_column
from app.models.enums import ExpenseCategory, OfferStatus


class CollectionItem(Base):
    __tablename__ = "collection_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # NO ACTION, not RESTRICT: the rule "no deleting an item that has coins"
    # lives in the service layer, so this key is only a backstop — and unlike
    # RESTRICT, NO ACTION can be deferred if a future transaction needs to
    # re-point coins between catalog items. See docs/02-data-model.md.
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="NO ACTION"), nullable=False
    )
    variant_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_variants.id", ondelete="SET NULL")
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    grade: Mapped[str | None] = mapped_column(Text)
    condition_notes: Mapped[str | None] = mapped_column(Text)
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    acquisition_place: Mapped[str | None] = mapped_column(Text)
    seller: Mapped[str | None] = mapped_column(Text)
    purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    purchase_currency: Mapped[str | None] = mapped_column(ForeignKey("currencies.code"))
    purchase_rate_uah: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    storage_location: Mapped[str | None] = mapped_column(Text)
    grading_company: Mapped[str | None] = mapped_column(Text)
    grading_number: Mapped[str | None] = mapped_column(Text)
    grading_grade: Mapped[str | None] = mapped_column(Text)
    is_for_swap: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_for_sale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    needs_replacement: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_collection_items_owner_id_catalog_item_id", "owner_id", "catalog_item_id"),
        Index(
            "ix_collection_items_owner_id_acquisition_date",
            "owner_id",
            desc("acquisition_date"),
        ),
    )


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[ExpenseCategory] = mapped_column(
        ENUM(
            ExpenseCategory,
            name="expense_category",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    rate_uah: Mapped[Decimal | None] = mapped_column(Numeric(14, 6))
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    catalog_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="SET NULL")
    )
    # SET NULL is only a backstop against a dangling reference; the service
    # layer deletes the coin_purchase expense explicitly. docs/04, rule 10.
    collection_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_items.id", ondelete="SET NULL")
    )
    series_id: Mapped[int | None] = mapped_column(ForeignKey("coin_series.id", ondelete="SET NULL"))
    vendor: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_non_negative"),
        Index("ix_expenses_owner_id_expense_date", "owner_id", "expense_date"),
    )


class Sale(Base):
    """Created now, unused in the MVP."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    collection_item_id: Mapped[int] = mapped_column(
        ForeignKey("collection_items.id", ondelete="NO ACTION"), nullable=False
    )
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="NO ACTION"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    buyer: Mapped[str | None] = mapped_column(Text)
    sale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    sale_currency: Mapped[str] = mapped_column(
        ForeignKey("currencies.code"), nullable=False, server_default="UAH"
    )
    sale_rate_uah: Mapped[Decimal] = mapped_column(
        Numeric(14, 6), nullable=False, server_default="1"
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("sale_price >= 0", name="sale_price_non_negative"),
    )


class PurchaseOffer(Base):
    """Created now, unused in the MVP."""

    __tablename__ = "purchase_offers"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    catalog_item_id: Mapped[int] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency_code: Mapped[str] = mapped_column(ForeignKey("currencies.code"), nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    seller: Mapped[str | None] = mapped_column(Text)
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[OfferStatus] = mapped_column(
        ENUM(OfferStatus, name="offer_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=OfferStatus.CONSIDERING.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (CheckConstraint("price >= 0", name="price_non_negative"),)


class CollectionGoal(Base):
    """Created now, unused in the MVP."""

    __tablename__ = "collection_goals"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_id: Mapped[int | None] = mapped_column(ForeignKey("countries.id", ondelete="CASCADE"))
    series_id: Mapped[int | None] = mapped_column(ForeignKey("coin_series.id", ondelete="CASCADE"))
    collection_group: Mapped[str | None] = mapped_column(
        ENUM(name="collection_group", create_type=False)
    )
    year_from: Mapped[int | None] = mapped_column(Integer)
    year_to: Mapped[int | None] = mapped_column(Integer)
    denomination_ids: Mapped[list[int] | None] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = created_at_column()
