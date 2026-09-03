"""Collection use cases: the purchase transaction and its bookkeeping.

Creating an instance also creates a coin_purchase expense for
price x quantity with the NBU rate on the purchase date; updating recomputes
that expense, deleting removes it — always in the same transaction
(docs/04-business-rules.md, rules 4, 6 and 10).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CollectionItem, Currency, Expense, MediaFile, User
from app.models.enums import ExpenseCategory, UserRole
from app.repositories.catalog import CatalogRepository
from app.repositories.collection import (
    CollectionFilters,
    CollectionRepository,
    CollectionRow,
)
from app.repositories.media import MediaRepository
from app.repositories.rates import RateRepository
from app.schemas.collection import (
    CollectionItemCreate,
    CollectionItemOut,
    CollectionItemUpdate,
)
from app.services.catalog import display_title
from app.services.media_urls import CatalogImages, MediaUrlBuilder


class CollectionError(Exception):
    pass


class CatalogItemNotFoundError(CollectionError):
    """The referenced catalog item is absent or not visible: 404."""


class CollectionItemNotFoundError(CollectionError):
    """No such instance in this user's collection: 404."""


class UnknownCurrencyError(CollectionError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.detail = f"Unknown currency code: {code}."


class MissingRateError(CollectionError):
    """No NBU rate on or before the purchase date: 422 (docs/03)."""

    def __init__(self, currency: str, on_date: str) -> None:
        super().__init__(currency)
        self.detail = (
            f"No exchange rate is stored for {currency} on or before {on_date}. "
            "Enter the purchase in UAH or pick a date covered by the rate table."
        )


class CollectionService:
    def __init__(self, session: AsyncSession, user: User) -> None:
        self._session = session
        self._user = user
        self._repo = CollectionRepository(session, owner_id=user.id)
        self._catalog = CatalogRepository(
            session, user_id=user.id, is_admin=user.role == UserRole.ADMIN
        )
        self._rates = RateRepository(session)
        self._media = MediaRepository(session, user_id=user.id)
        self._urls = MediaUrlBuilder()

    async def list_collection(
        self, filters: CollectionFilters, *, limit: int, offset: int
    ) -> tuple[list[CollectionItemOut], int]:
        rows, total = await self._repo.list_page(filters, limit=limit, offset=offset)
        images = await self._images_for([row.catalog_item.id for row in rows])
        return [
            self._row_out(row, images.get(row.catalog_item.id, CatalogImages())) for row in rows
        ], total

    async def create(self, payload: CollectionItemCreate) -> CollectionItemOut:
        item = await self._catalog.get_visible(payload.catalog_item_id)
        if item is None:
            raise CatalogItemNotFoundError
        rate = await self._resolve_rate(payload.currency, payload.purchase_date)

        instance = CollectionItem(
            owner_id=self._user.id,
            catalog_item_id=item.id,
            quantity=payload.quantity,
            grade=payload.grade,
            acquisition_date=payload.purchase_date,
            seller=payload.seller,
            purchase_price=payload.price,
            purchase_currency=payload.currency,
            purchase_rate_uah=rate,
            notes=payload.notes,
        )
        await self._repo.add(instance)
        self._session.add(self._build_expense(instance))
        await self._session.flush()
        return await self._get_out(instance.id)

    async def update(self, item_id: int, payload: CollectionItemUpdate) -> CollectionItemOut:
        row = await self._repo.get_row(item_id)
        if row is None:
            raise CollectionItemNotFoundError
        instance = row.instance

        changes = payload.model_dump(exclude_unset=True)
        field_map = {
            "quantity": "quantity",
            "price": "purchase_price",
            "currency": "purchase_currency",
            "purchase_date": "acquisition_date",
            "seller": "seller",
            "notes": "notes",
            "grade": "grade",
        }
        for source, target in field_map.items():
            if source in changes:
                setattr(instance, target, changes[source])

        money_changed = {"quantity", "price", "currency", "purchase_date"} & changes.keys()
        if money_changed:
            assert instance.purchase_currency is not None
            assert instance.acquisition_date is not None
            instance.purchase_rate_uah = await self._resolve_rate(
                instance.purchase_currency, instance.acquisition_date
            )

        expense = await self._repo.purchase_expense_for(instance.id)
        if expense is not None:
            self._sync_expense(expense, instance)
        elif money_changed:
            # Defensive: an instance should always carry its purchase expense.
            self._session.add(self._build_expense(instance))
        await self._session.flush()
        return await self._get_out(item_id)

    async def delete(self, item_id: int) -> None:
        instance = await self._repo.get(item_id)
        if instance is None:
            raise CollectionItemNotFoundError
        expense = await self._repo.purchase_expense_for(instance.id)
        if expense is not None:
            await self._session.delete(expense)
            await self._session.flush()
        await self._repo.delete(instance)

    # ------------------------------------------------------------- internals

    async def _get_out(self, item_id: int) -> CollectionItemOut:
        row = await self._repo.get_row(item_id)
        assert row is not None
        images = await self._images_for([row.catalog_item.id])
        return self._row_out(row, images.get(row.catalog_item.id, CatalogImages()))

    async def _images_for(self, item_ids: list[int]) -> dict[int, CatalogImages]:
        """Same visibility rules as the catalog listing (docs/06-media-storage.md)."""
        files = await self._media.visible_for_catalog_items(item_ids)
        by_item: dict[int, list[MediaFile]] = {}
        for media in files:
            if media.catalog_item_id is not None:
                by_item.setdefault(media.catalog_item_id, []).append(media)
        return {
            item_id: self._urls.pick_catalog_images(items) for item_id, items in by_item.items()
        }

    async def _resolve_rate(self, currency: str, on_date: date) -> Decimal:
        if await self._session.get(Currency, currency) is None:
            raise UnknownCurrencyError(currency)
        if currency == "UAH":
            return Decimal(1)
        rate = await self._rates.rate_on(currency, on_date)
        if rate is None:
            raise MissingRateError(currency, on_date.isoformat())
        return rate

    def _build_expense(self, instance: CollectionItem) -> Expense:
        assert instance.purchase_price is not None
        assert instance.purchase_currency is not None
        assert instance.acquisition_date is not None
        return Expense(
            owner_id=self._user.id,
            category=ExpenseCategory.COIN_PURCHASE,
            amount=instance.purchase_price * instance.quantity,
            currency_code=instance.purchase_currency,
            rate_uah=instance.purchase_rate_uah,
            expense_date=instance.acquisition_date,
            catalog_item_id=instance.catalog_item_id,
            collection_item_id=instance.id,
            vendor=instance.seller,
        )

    @staticmethod
    def _sync_expense(expense: Expense, instance: CollectionItem) -> None:
        assert instance.purchase_price is not None
        assert instance.purchase_currency is not None
        assert instance.acquisition_date is not None
        expense.amount = instance.purchase_price * instance.quantity
        expense.currency_code = instance.purchase_currency
        expense.rate_uah = instance.purchase_rate_uah
        expense.expense_date = instance.acquisition_date
        expense.vendor = instance.seller

    def _row_out(self, row: CollectionRow, images: CatalogImages) -> CollectionItemOut:
        instance = row.instance
        item = row.catalog_item
        return CollectionItemOut(
            id=instance.id,
            catalog_item_id=item.id,
            title=display_title(item),
            country=row.country,
            series_name=row.series_name,
            denomination=row.denomination,
            year=item.issue_year,
            is_archived=item.is_archived,
            archive_reason=item.archive_reason,
            quantity=instance.quantity,
            grade=instance.grade,
            purchase_date=instance.acquisition_date,
            seller=instance.seller,
            price=instance.purchase_price,
            currency=instance.purchase_currency,
            rate_uah=instance.purchase_rate_uah,
            total_uah=(instance.purchase_price or Decimal(0))
            * (instance.purchase_rate_uah or Decimal(1))
            * instance.quantity,
            notes=instance.notes,
            thumbnail_url=images.thumbnail_url,
            market_price_uah=row.market_price_uah,
        )
