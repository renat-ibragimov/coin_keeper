"""User accounts, sessions and one-time tokens."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column, updated_at_column
from app.models.enums import AuthTokenKind, UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    role: Mapped[UserRole] = mapped_column(
        ENUM(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=UserRole.USER,
        server_default=UserRole.USER.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="uk", server_default="uk")
    # The storage key of the profile picture, not a URL: the bucket's host can
    # change, and the URL the API hands out is signed and short-lived anyway.
    # A plain column rather than a media_files row — that table's CHECK ties
    # every file to a catalog or collection item, and none of its
    # provenance/role machinery means anything for a face.
    avatar_key: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    identities: Mapped[list[AuthIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None

    @property
    def google_linked(self) -> bool:
        return any(identity.provider == "google" for identity in self.identities)


class AuthIdentity(Base):
    """A provider subject identifies an account even when its email changes."""

    __tablename__ = "auth_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    email_at_link: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created_at_column()

    user: Mapped[User] = relationship(back_populates="identities")

    __table_args__ = (
        UniqueConstraint("provider", "subject", name="uq_auth_identities_provider_subject"),
        UniqueConstraint("user_id", "provider", name="uq_auth_identities_user_provider"),
    )


class RefreshToken(Base):
    """Stores the sha256 of the token, never the token itself (docs/auth.md)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # RefreshRevokeReason; set together with revoked_at.
    revoke_reason: Mapped[str | None] = mapped_column(Text)
    # One family per sign-in; rotation keeps it. A proven replay revokes the
    # family, never the user's other devices (docs/auth.md, "Sessions").
    family_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )
    # When the family's sign-in happened, carried through rotation.
    session_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # "Remember me" at sign-in, carried through rotation.
    persistent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        CheckConstraint(
            "revoke_reason IS NULL OR revoke_reason IN "
            "('rotated', 'logout', 'reuse', 'password_change', 'password_reset', 'logout_all')",
            name="revoke_reason_valid",
        ),
        Index("ix_refresh_tokens_user_id", "user_id"),
        Index("ix_refresh_tokens_family_id", "family_id"),
        Index(
            "ix_refresh_tokens_user_id_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )


class AuthToken(Base):
    """One-time email verification and password reset tokens."""

    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[AuthTokenKind] = mapped_column(
        ENUM(
            AuthTokenKind,
            name="auth_token_kind",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (Index("ix_auth_tokens_user_id_kind", "user_id", "kind"),)


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    locale: Mapped[str] = mapped_column(Text, nullable=False, default="uk", server_default="uk")
    display_currency: Mapped[str] = mapped_column(
        Text, nullable=False, default="UAH", server_default="UAH"
    )
    # One default for every new purchase, regardless of catalog group: the
    # commemorative/circulation split (migration 0014) never earned its
    # complexity — a collector picks a grade per purchase anyway, and this is
    # only ever the pre-filled starting point.
    default_grade: Mapped[str] = mapped_column(
        Text, nullable=False, default="UNC", server_default="UNC"
    )
    # On by default: a souvenir-packaging card (catalog_items.packaging_of_id
    # points at the bare coin, docs/business-rules.md) shows in catalog
    # listings until the viewer opts out.
    show_packaging_variants: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Cross-device preferences (docs/api.md): the client keeps a
    # localStorage copy for instant paint before this row is fetched, but
    # this is the value that survives a new browser or device.
    theme: Mapped[str] = mapped_column(
        Text, nullable=False, default="system", server_default="system"
    )
    catalog_view_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="cards", server_default="cards"
    )
    collection_view_mode: Mapped[str] = mapped_column(
        Text, nullable=False, default="cards", server_default="cards"
    )
    # The primary amount stays UAH everywhere (it is the ledger currency —
    # every purchase and expense converts to it, docs/business-rules.md);
    # this only picks which already-computed historical/live conversion
    # ("≈ $" today) shows alongside it. USD or EUR only: NBU rate history
    # covers just those two (docs/api.md).
    secondary_currency: Mapped[str] = mapped_column(
        Text, nullable=False, default="USD", server_default="USD"
    )
    # Whether delivery/holder/grading count toward "Куплено загалом" and the
    # value-change figure, or stay a separate informational line next to
    # them (docs/business-rules.md, BR-4). On by default.
    include_supporting_expenses: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Pre-fills the purchase form's storage location for a brand-new purchase,
    # same idea as default_grade. NULL until the owner sets one.
    default_storage_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("storage_locations.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(back_populates="settings")


class UcoinCatalogSource(Base):
    """Saved uCoin catalog sections for repeat import. Unused: uCoin import is deferred."""

    __tablename__ = "ucoin_catalog_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str | None] = mapped_column(Text)
    collection_group: Mapped[str | None] = mapped_column(
        ENUM(name="collection_group", create_type=False)
    )
    last_import_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scanned: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_inserted: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_skipped: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    __table_args__ = (
        Index("uq_ucoin_catalog_sources_owner_id_url", "owner_id", "url", unique=True),
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = created_at_column()


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str | None] = mapped_column(String)
    decimal_places: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=2, server_default="2"
    )
