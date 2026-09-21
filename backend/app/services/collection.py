"""Collection use cases: the purchase transaction and its bookkeeping.

Creating an instance also creates a coin_purchase expense for
price x quantity with the NBU rate on the purchase date; updating recomputes
that expense, deleting removes it — always in the same transaction
(docs/04-business-rules.md, rules 4, 6 and 10).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE, pick_name
from app.models import (
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Country,
    Currency,
    Denomination,
    Expense,
    User,
)
from app.models.enums import ExpenseCategory, MediaRole, UserRole
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
from app.schemas.catalog import CoinMaterial
from app.schemas.collection import (
    CollectionItemCreate,
    CollectionItemOut,
    CollectionItemUpdate,
    CollectionPositionOut,
    ExtraExpenseIn,
    StorageLocationOut,
)
from app.schemas.reference import CountryOut, DenominationOut
from app.schemas.series import SeriesOut
from app.services.catalog import CatalogService, display_title, material_out
from app.services.media_urls import (
    CatalogImages,
    MediaUrlBuilder,
    image_out,
    images_by_catalog_item,
)
from app.services.storage_locations import StorageLocationService


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
        catalog_confirmed=country.catalog_confirmed,
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


def _denomination_label(
    denomination: Denomination | None, item: CatalogItem, locale: str
) -> str | None:
    """The dictionary label, or what the owner typed on a personal item when
    their country has no denominations at all (docs/04-business-rules.md, §14)."""
    if denomination is not None:
        return render_label(denomination.value, denomination.unit, locale)
    text = (item.denomination_text or "").strip()
    return text or None


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
    def __init__(
        self,
        session: AsyncSession,
        user: User,
        locale: str = DEFAULT_LOCALE,
        background_tasks: BackgroundTasks | None = None,
    ) -> None:
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
        self._storage_locations = StorageLocationService(
            session, owner_id=user.id, locale=locale, background_tasks=background_tasks
        )

    async def list_storage_locations(self) -> list[StorageLocationOut]:
        return await self._storage_locations.list_locations()

    async def add_storage_location(self, name: str) -> StorageLocationOut:
        return await self._storage_locations.add(name)

    async def delete_storage_location(self, name: str) -> None:
        await self._storage_locations.delete(name)

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

    async def list_owned_materials(self, country_id: int | None) -> list[CoinMaterial]:
        materials = await self._repo.list_owned_materials(country_id)
        return [out for material in materials if (out := material_out(material, self._locale))]

    async def get(self, item_id: int) -> CollectionItemOut:
        if await self._repo.get_row(item_id) is None:
            raise CollectionItemNotFoundError
        return await self._get_out(item_id)

    async def create(self, payload: CollectionItemCreate) -> CollectionItemOut:
        """The purchase transaction (docs/04-business-rules.md, rule 4).

        With `newCatalogItem` it grows a third write — the personal catalog
        item itself — and with `extraExpenses` one more per supporting
        expense. The order below is the whole point: every rate is resolved
        before anything is inserted, so a purchase rejected for a missing rate
        cannot leave a coin nobody bought behind. The schema guarantees
        exactly one of the two coin fields is set.
        """
        rate = await self._resolve_rate(payload.currency, payload.purchase_date)
        # Every currency in the request, the coin's and the delivery's alike,
        # is resolved before the first insert. A supporting expense in a
        # currency with no rate must not leave a coin and an instance behind.
        extra_rates = [
            await self._resolve_rate(extra.currency, payload.purchase_date)
            for extra in payload.extra_expenses
        ]
        # Resolved before the coin, not after: a storage location the owner
        # has not used before is created *and committed* on the spot
        # (app/repositories/storage_locations.py), and that commit must not
        # land in the middle of this transaction's own writes.
        storage_location_id = await self._storage_locations.resolve(payload.storage_location)

        if payload.new_catalog_item is not None:
            item = await CatalogService(
                self._session, self._user, self._locale
            ).create_personal_item(payload.new_catalog_item)
        else:
            assert payload.catalog_item_id is not None
            found = await self._catalog.get_visible(payload.catalog_item_id)
            if found is None:
                raise CatalogItemNotFoundError
            item = found

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
            storage_location_id=storage_location_id,
            notes=payload.notes,
        )
        await self._repo.add(instance)
        self._session.add(self._build_expense(instance))
        for extra, extra_rate in zip(payload.extra_expenses, extra_rates, strict=True):
            self._session.add(self._build_extra_expense(extra, extra_rate, instance))
        await self._session.flush()
        if payload.new_catalog_item is not None:
            # All three rows at once, here rather than at the end of the
            # request: FastAPI runs BackgroundTasks *before* the request's own
            # commit (proved the hard way on storage locations, 2026-09-13),
            # and the translation task opens a session of its own — it would
            # find no such coin. Atomicity is untouched: this is still one
            # commit for the item, the instance and the expense together.
            await self._session.commit()
        return await self._get_out(instance.id)

    async def update(self, item_id: int, payload: CollectionItemUpdate) -> CollectionItemOut:
        row = await self._repo.get_row(item_id)
        if row is None:
            raise CollectionItemNotFoundError
        instance = row.instance

        changes = payload.model_dump(exclude_unset=True)
        if "storage_location" in changes:
            instance.storage_location_id = await self._storage_locations.resolve(
                changes.pop("storage_location")
            )
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
        images, own_roles = await self._instance_images(row.instance.id, row.catalog_item.id)
        return self._row_out(row, images, own_roles)

    async def _images_for(self, item_ids: list[int]) -> dict[int, CatalogImages]:
        """The listing's thumbnail: any of the owner's own purchases of the
        item may carry the photo, since a position is not any one instance
        (docs/06-media-storage.md)."""
        return await images_by_catalog_item(self._media, self._urls, item_ids)

    async def _instance_images(
        self, item_id: int, catalog_item_id: int
    ) -> tuple[CatalogImages, frozenset[MediaRole]]:
        """This exact instance's own photo, or the catalog's — never a
        sibling purchase's, unlike the position listing above. The role set
        is which sides are actually this owner's own upload, for the edit
        page's delete button."""
        catalog_files = await self._media.visible_for_catalog_items([catalog_item_id])
        own_files = await self._media.visible_for_collection_items([item_id])
        images = self._urls.pick_catalog_images([*catalog_files, *own_files])
        return images, frozenset(media.role for media in own_files)

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

    def _build_extra_expense(
        self, extra: ExtraExpenseIn, rate: Decimal, instance: CollectionItem
    ) -> Expense:
        """A supporting expense of the purchase — as a plain manual expense.

        Linked to the coin, deliberately not to the instance: `collection_item_id`
        means "this row *is* the purchase" everywhere else (it is what the money
        journal's icons act on, and what deleting a coin takes with it, rule 4).
        A delivery is money that was spent whether or not the coin later leaves
        the collection, and deleting the delivery must never touch the coin.
        """
        return Expense(
            owner_id=self._user.id,
            category=extra.category,
            amount=extra.amount,
            currency_code=extra.currency,
            rate_uah=rate,
            expense_date=instance.acquisition_date,
            catalog_item_id=instance.catalog_item_id,
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
            denomination=_denomination_label(row.denomination, item, self._locale),
            year=item.issue_year,
            issue_date=item.issue_date,
            is_archived=item.is_archived,
            archive_reason=item.archive_reason,
            total_quantity=row.total_quantity,
            total_spend_uah=row.total_spend_uah,
            market_value_uah=row.market_value_uah,
            last_acquisition_date=row.last_acquisition_date,
            grades=row.grades,
            thumbnail_url=images.thumbnail_url,
        )

    def _row_out(
        self, row: CollectionRow, images: CatalogImages, own_roles: frozenset[MediaRole]
    ) -> CollectionItemOut:
        instance = row.instance
        item = row.catalog_item
        return CollectionItemOut(
            id=instance.id,
            catalog_item_id=item.id,
            title=display_title(item, self._locale),
            country=row.country,
            series_name=row.series_name,
            denomination=_denomination_label(row.denomination, item, self._locale),
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
            storage_location=row.storage_location,
            notes=instance.notes,
            thumbnail_url=images.thumbnail_url,
            market_price_uah=row.market_price_uah,
            obverse_image=image_out(images.obverse),
            reverse_image=image_out(images.reverse),
            obverse_photo_is_own=MediaRole.OBVERSE in own_roles,
            reverse_photo_is_own=MediaRole.REVERSE in own_roles,
        )
