"""Database enum types.

Values mirror docs/02-data-model.md exactly; the native PostgreSQL type names are
used by the initial migration.
"""

from __future__ import annotations

import enum


class CollectionGroup(enum.StrEnum):
    CIRCULATION = "circulation"
    COMMEMORATIVE = "commemorative"
    COLLECTOR = "collector"
    OTHER = "other"


class MetalKind(enum.StrEnum):
    PRECIOUS = "precious"
    BASE = "base"
    UNKNOWN = "unknown"


class MediaRole(enum.StrEnum):
    OBVERSE = "obverse"
    REVERSE = "reverse"
    EDGE = "edge"
    ADDITIONAL = "additional"


class MediaSource(enum.StrEnum):
    """Where an image came from. Drives visibility, see docs/06-media-storage.md."""

    USER_UPLOAD = "user_upload"
    UCOIN = "ucoin"
    NBU = "nbu"
    MANUAL = "manual"


class MatchStatus(enum.StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class OfferStatus(enum.StrEnum):
    CONSIDERING = "considering"
    ORDERED = "ordered"
    PURCHASED = "purchased"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


class UserRole(enum.StrEnum):
    USER = "user"
    ADMIN = "admin"


class ExpenseCategory(enum.StrEnum):
    COIN_PURCHASE = "coin_purchase"
    DELIVERY = "delivery"
    ALBUM = "album"
    HOLDER = "holder"
    STORAGE = "storage"
    GRADING = "grading"
    LITERATURE = "literature"
    PHOTO_EQUIPMENT = "photo_equipment"
    OTHER = "other"


class AuthTokenKind(enum.StrEnum):
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"  # noqa: S105 - token kind, not a secret
