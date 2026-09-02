"""User accounts, sessions and one-time tokens."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import CITEXT, ENUM, INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, created_at_column, updated_at_column
from app.models.enums import AuthTokenKind, UserRole


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(CITEXT, nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
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
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = updated_at_column()

    settings: Mapped[UserSettings | None] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class RefreshToken(Base):
    """Stores the sha256 of the token, never the token itself (docs/07-auth.md)."""

    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (Index("ix_refresh_tokens_user_id", "user_id"),)


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
    default_grade_commemorative: Mapped[str] = mapped_column(
        Text, nullable=False, default="UNC", server_default="UNC"
    )
    default_grade_circulation: Mapped[str] = mapped_column(
        Text, nullable=False, default="VF", server_default="VF"
    )
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(back_populates="settings")


class UcoinCatalogSource(Base):
    """Saved uCoin catalog sections for repeat import. Unused until stage 6."""

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
