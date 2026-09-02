"""Stored images and their provenance."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, created_at_column
from app.models.enums import MediaRole, MediaSource


class MediaFile(Base):
    __tablename__ = "media_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    catalog_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("catalog_items.id", ondelete="CASCADE")
    )
    collection_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_items.id", ondelete="CASCADE")
    )
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[MediaRole] = mapped_column(
        ENUM(MediaRole, name="media_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    # Provenance drives visibility, see docs/06-media-storage.md.
    source: Mapped[MediaSource] = mapped_column(
        ENUM(MediaSource, name="media_source", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=MediaSource.USER_UPLOAD.value,
    )
    license: Mapped[str | None] = mapped_column(Text)
    attribution: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    external_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_key: Mapped[str | None] = mapped_column(Text)
    mime_type: Mapped[str | None] = mapped_column(Text)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        CheckConstraint(
            "catalog_item_id IS NOT NULL OR collection_item_id IS NOT NULL",
            name="belongs_to_catalog_or_collection",
        ),
        CheckConstraint(
            "storage_key IS NOT NULL OR external_url IS NOT NULL",
            name="has_storage_key_or_external_url",
        ),
        Index("ix_media_files_catalog_item_id", "catalog_item_id"),
        Index("ix_media_files_collection_item_id", "collection_item_id"),
        Index("ix_media_files_owner_id", "owner_id"),
    )
