"""SQLAlchemy models — the whole schema from docs/02-data-model.md.

Tables the MVP does not use yet (sales, purchase_offers, collection_goals,
catalog_variants, audit_log) are created up front on purpose, so later stages
do not have to rewrite migrations. See docs/01-scope-mvp.md.
"""

from app.models.base import Base
from app.models.catalog import (
    CatalogItem,
    CatalogVariant,
    CoinSeries,
    Country,
    Denomination,
    ExchangeRate,
    Material,
)
from app.models.collection import (
    CollectionGoal,
    CollectionItem,
    Expense,
    PurchaseOffer,
    Sale,
)
from app.models.media import MediaFile
from app.models.pricing import MarketPriceSnapshot, PriceSourceLink
from app.models.user import (
    AuditLog,
    AuthToken,
    Currency,
    RefreshToken,
    UcoinCatalogSource,
    User,
    UserSettings,
)

__all__ = [
    "AuditLog",
    "AuthToken",
    "Base",
    "CatalogItem",
    "CatalogVariant",
    "CoinSeries",
    "CollectionGoal",
    "CollectionItem",
    "Country",
    "Currency",
    "Denomination",
    "ExchangeRate",
    "Expense",
    "MarketPriceSnapshot",
    "Material",
    "MediaFile",
    "PriceSourceLink",
    "PurchaseOffer",
    "RefreshToken",
    "Sale",
    "UcoinCatalogSource",
    "User",
    "UserSettings",
]
