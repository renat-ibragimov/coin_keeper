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

from app.core.locale import DEFAULT_LOCALE, pick_name
from app.models import (
    CoinSeries,
    CollectionItem,
    Country,
    Currency,
    Denomination,
    Expense,
    MediaFile,
    User,
)
from app.models.enums import ExpenseCategory, UserRole
from app.reference_data.denominations import render_label
from app.repositories.catalog import CatalogRepository
from app.repositories.collection import (
    CollectionFilters,
    CollectionPositionRow,
    CollectionRepository,
    CollectionRow,
)
from app.repositories.media import MediaRepository
from app.repositories.rates import RateRepository
from app.schemas.collection import (
    CollectionItemCreate,
    CollectionItemOut,
    CollectionItemUpdate,
    CollectionPositionOut,
)
from app.schemas.reference import CountryOut, DenominationOut
from app.schemas.series import SeriesOut
from app.services.catalog import display_title
from app.services.media_urls import CatalogImages, MediaUrlBuilder


def _country_out(
    country: Country, locale: str, year_bounds: tuple[int, int] | None = None
) -> CountryOut:
    return CountryOut(
        id=country.id,
        code=country.code,
        name=pick_name(
            locale, uk=country.name_uk, en=country.name_en, original=country.name_original
        ),
        name_original=country.name_original,
        original_lang=country.original_lang,
        name_uk=country.name_uk,
        name_en=country.name_en,
        collect_variants=country.collect_variants,
        is_active=country.is_active,
        sort_order=country.sort_order,
        min_year=year_bounds[0] if year_bounds else None,
        max_year=year_bounds[1] if year_bounds else None,
    )


def _series_out(series: CoinSeries, locale: str) -> SeriesOut:
    return SeriesOut(
        id=series.id,
        country_id=series.country_id,
        name=pick_name(locale, uk=series.name_uk, en=series.name_en, original=series.name_original),
        name_original=series.name_original,
        original_lang=series.original_lang,
        name_uk=series.name_uk,
        name_uk_source=series.name_uk_source,
        name_en=series.name_en,
        name_en_source=series.name_en_source,
        description=series.description,
        start_year=series.start_year,
        end_year=series.end_year,
    )


def _denomination_out(denomination: Denomination, locale: str) -> DenominationOut:
    return DenominationOut(
        id=denomination.id,
        country_id=denomination.country_id,
        currency_code=denomination.currency_code,
        value=denomination.value,
        unit=denomination.unit,
        label=render_label(denomination.value, denomination.unit, locale),
        sort_order=denomination.sort_order,
    )


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
    def __init__(self, session: AsyncSession, user: User, locale: str = DEFAULT_LOCALE) -> None:
        self._session = session
        self._user = user
        self._locale = locale
        self._repo = CollectionRepository(session, owner_id=user.id, locale=locale)
        self._catalog = CatalogRepository(
            session, user_id=user.id, is_admin=user.role == UserRole.ADMIN, locale=locale
        )
        self._rates = RateRepository(session)
        self._media = MediaRepository(session, user_id=user.id)
        self._urls = MediaUrlBuilder()

    async def list_positions(
        self, filters: CollectionFilters, *, limit: int, offset: int
    ) -> tuple[list[CollectionPositionOut], int]:
        rows, total = await self._repo.list_positions(filters, limit=limit, offset=offset)
        images = await self._images_for([row.catalog_item.id for row in rows])
        return [
            self._position_out(row, images.get(row.catalog_item.id, CatalogImages()))
            for row in rows
        ], total

    async def list_owned_countries(self) -> list[CountryOut]:
        countries = await self._repo.list_owned_countries()
        year_bounds = await self._repo.owned_year_bounds_by_country()
        return [
            _country_out(country, self._locale, year_bounds.get(country.id))
            for country in countries
        ]

    async def list_owned_series(self, country_id: int | None) -> list[SeriesOut]:
        series = await self._repo.list_owned_series(country_id)
        return [_series_out(item, self._locale) for item in series]

    async def list_owned_denominations(self, country_id: int | None) -> list[DenominationOut]:
        denominations = await self._repo.list_owned_denominations(country_id)
        return [_denomination_out(item, self._locale) for item in denominations]

    async def get(self, item_id: int) -> CollectionItemOut:
        if await self._repo.get_row(item_id) is None:
            raise CollectionItemNotFoundError
        return await self._get_out(item_id)

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

    def _position_out(
        self, row: CollectionPositionRow, images: CatalogImages
    ) -> CollectionPositionOut:
        item = row.catalog_item
        return CollectionPositionOut(
            catalog_item_id=item.id,
            title=display_title(item, self._locale),
            country=row.country,
            series_name=row.series_name,
            collection_group=item.collection_group,
            denomination=(
                None
                if row.denomination is None
                else render_label(row.denomination.value, row.denomination.unit, self._locale)
            ),
            year=item.issue_year,
            is_archived=item.is_archived,
            archive_reason=item.archive_reason,
            total_quantity=row.total_quantity,
            total_spend_uah=row.total_spend_uah,
            market_value_uah=row.market_value_uah,
            last_acquisition_date=row.last_acquisition_date,
            grades=row.grades,
            thumbnail_url=images.thumbnail_url,
        )

    def _row_out(self, row: CollectionRow, images: CatalogImages) -> CollectionItemOut:
        instance = row.instance
        item = row.catalog_item
        return CollectionItemOut(
            id=instance.id,
            catalog_item_id=item.id,
            title=display_title(item, self._locale),
            country=row.country,
            series_name=row.series_name,
            denomination=(
                None
                if row.denomination is None
                else render_label(row.denomination.value, row.denomination.unit, self._locale)
            ),
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
