"""Catalog use cases: listing, cards, price history, CRUD and archiving.

Permission semantics (docs/07-auth.md): an invisible item — someone else's
personal record — is a 404; a visible shared record the user may not touch is
a 403.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.locale import DEFAULT_LOCALE, pick_name
from app.models import (
    AuditLog,
    CatalogItem,
    CoinSeries,
    Country,
    Denomination,
    Material,
    MediaFile,
    User,
)
from app.models.enums import UserRole
from app.reference_data.denominations import render_label
from app.repositories.catalog import CatalogFilters, CatalogRepository, CatalogRow
from app.repositories.collection import CollectionRepository
from app.repositories.media import MediaRepository
from app.schemas.catalog import (
    ArchiveStateOut,
    CatalogCard,
    CatalogCollectionItemOut,
    CatalogItemCreate,
    CatalogItemUpdate,
    CatalogListItem,
    CoinDenomination,
    CoinMaterial,
    PriceHistoryItem,
)
from app.services.media_urls import CatalogImages, MediaUrlBuilder


class CatalogError(Exception):
    """Base class so routes can map service failures to problems."""


class ItemNotFoundError(CatalogError):
    """Invisible or absent: presented as 404."""


class SharedRecordForbiddenError(CatalogError):
    """A regular user tried to modify the shared catalog: 403."""


class NotApplicableToPersonalError(CatalogError):
    """Archiving applies to shared records only: 400."""


class ArchiveStateError(CatalogError):
    """Archive/unarchive called twice, or delete before archive: 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class ItemHasReferencesError(CatalogError):
    """Deletion blocked by existing references: 409."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BadReferenceError(CatalogError):
    """countryId/seriesId/denominationId do not exist or do not match: 422."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def display_title(item: CatalogItem, locale: str = DEFAULT_LOCALE) -> str:
    """title_{locale} → title_original (docs/04-business-rules.md)."""
    return pick_name(locale, uk=item.title_uk, en=item.title_en, original=item.title_original)


def denomination_out(denomination: Denomination | None, locale: str) -> CoinDenomination | None:
    if denomination is None:
        return None
    return CoinDenomination(
        id=denomination.id,
        value=denomination.value,
        unit=denomination.unit,
        currency_code=denomination.currency_code,
        label=render_label(denomination.value, denomination.unit, locale),
    )


def material_out(material: Material | None, locale: str) -> CoinMaterial | None:
    if material is None:
        return None
    return CoinMaterial(
        id=material.id,
        code=material.code,
        name=material.name_uk if locale == "uk" else material.name_en,
    )


class CatalogService:
    def __init__(self, session: AsyncSession, user: User, locale: str = DEFAULT_LOCALE) -> None:
        self._session = session
        self._user = user
        self._locale = locale
        self._is_admin = user.role == UserRole.ADMIN
        self._repo = CatalogRepository(
            session, user_id=user.id, is_admin=self._is_admin, locale=locale
        )
        self._media = MediaRepository(session, user_id=user.id)
        self._urls = MediaUrlBuilder()

    # --------------------------------------------------------------- reading

    async def list_catalog(
        self, filters: CatalogFilters, *, limit: int, offset: int
    ) -> tuple[list[CatalogListItem], int]:
        page = await self._repo.list_items(filters, limit=limit, offset=offset)
        images = await self._images_for([row.item.id for row in page.rows])
        items = [
            self._list_item(row, images.get(row.item.id, CatalogImages())) for row in page.rows
        ]
        return items, page.total

    async def get_card(self, item_id: int) -> CatalogCard:
        row = await self._repo.get_row(item_id)
        if row is None:
            raise ItemNotFoundError
        images = await self._images_for([item_id])
        return self._card(row, images.get(item_id, CatalogImages()))

    async def list_prices(self, item_id: int) -> list[PriceHistoryItem]:
        row = await self._repo.get_row(item_id)
        if row is None:
            raise ItemNotFoundError
        history = []
        for snapshot, price_uah in await self._repo.list_prices(item_id):
            history.append(
                PriceHistoryItem(
                    id=snapshot.id,
                    source=snapshot.source,
                    grade=snapshot.grade,
                    price=snapshot.price,
                    currency_code=snapshot.currency_code,
                    price_uah=price_uah,
                    observed_at=snapshot.observed_at,
                    source_url=snapshot.source_url,
                    is_own=snapshot.created_by == self._user.id,
                    is_suspect=snapshot.is_suspect,
                )
            )
        return history

    async def list_own_instances(self, item_id: int) -> list[CatalogCollectionItemOut]:
        row = await self._repo.get_row(item_id)
        if row is None:
            raise ItemNotFoundError
        instances = await CollectionRepository(self._session, owner_id=self._user.id).list_for_item(
            item_id
        )
        return [
            CatalogCollectionItemOut(
                id=instance.id,
                catalog_item_id=instance.catalog_item_id,
                quantity=instance.quantity,
                grade=instance.grade,
                acquisition_date=instance.acquisition_date,
                seller=instance.seller,
                purchase_price=instance.purchase_price,
                purchase_currency=instance.purchase_currency,
                purchase_rate_uah=instance.purchase_rate_uah,
                total_uah=(instance.purchase_price or Decimal(0))
                * (instance.purchase_rate_uah or Decimal(1))
                * instance.quantity,
                notes=instance.notes,
            )
            for instance in instances
        ]

    # --------------------------------------------------------------- writing

    async def create_item(self, payload: CatalogItemCreate) -> CatalogCard:
        if payload.shared and not self._is_admin:
            raise SharedRecordForbiddenError
        await self._check_references(
            country_id=payload.country_id,
            series_id=payload.series_id,
            denomination_id=payload.denomination_id,
            composition_id=payload.composition_id,
        )
        values = payload.model_dump(exclude={"shared"})
        item = CatalogItem(
            **values,
            created_by=None if payload.shared else self._user.id,
        )
        await self._repo.add(item)
        return await self.get_card(item.id)

    async def update_item(self, item_id: int, payload: CatalogItemUpdate) -> CatalogCard:
        item = await self._get_writable(item_id)
        changes = payload.model_dump(exclude_unset=True)
        await self._check_references(
            country_id=changes.get("country_id", item.country_id),
            series_id=changes.get("series_id", item.series_id),
            denomination_id=changes.get("denomination_id", item.denomination_id),
            composition_id=changes.get("composition_id", item.composition_id),
        )
        for field_name, value in changes.items():
            setattr(item, field_name, value)
        await self._session.flush()
        return await self.get_card(item_id)

    async def delete_item(self, item_id: int) -> None:
        item = await self._get_writable(item_id)
        if item.created_by is not None:
            await self._delete_personal(item)
        else:
            await self._delete_shared(item)

    async def archive_item(self, item_id: int, reason: str) -> ArchiveStateOut:
        item = await self._get_shared_for_admin(item_id)
        if item.is_archived:
            raise ArchiveStateError("The item is already archived.")
        item.is_archived = True
        item.archived_at = datetime.now(UTC)
        item.archive_reason = reason
        self._audit("catalog_item.archive", item.id, {"reason": reason})
        await self._session.flush()
        return ArchiveStateOut(
            is_archived=True, archived_at=item.archived_at, archive_reason=reason
        )

    async def unarchive_item(self, item_id: int) -> ArchiveStateOut:
        item = await self._get_shared_for_admin(item_id)
        if not item.is_archived:
            raise ArchiveStateError("The item is not archived.")
        item.is_archived = False
        item.archived_at = None
        item.archive_reason = None
        self._audit("catalog_item.unarchive", item.id, None)
        await self._session.flush()
        return ArchiveStateOut(is_archived=False)

    # ------------------------------------------------------------- internals

    async def _get_writable(self, item_id: int) -> CatalogItem:
        item = await self._repo.get_visible(item_id)
        if item is None:
            raise ItemNotFoundError
        if item.created_by is None and not self._is_admin:
            raise SharedRecordForbiddenError
        return item

    async def _get_shared_for_admin(self, item_id: int) -> CatalogItem:
        item = await self._repo.get_visible(item_id)
        if item is None:
            raise ItemNotFoundError
        if item.created_by is not None:
            raise NotApplicableToPersonalError
        if not self._is_admin:
            raise SharedRecordForbiddenError
        return item

    async def _delete_personal(self, item: CatalogItem) -> None:
        """A personal item goes away with the author's own coins and their
        purchase expenses, in one transaction (docs/04-business-rules.md, 10).
        """
        collection = CollectionRepository(self._session, owner_id=self._user.id)
        instances = await collection.list_for_item(item.id)
        for instance in instances:
            expense = await collection.purchase_expense_for(instance.id)
            if expense is not None:
                await self._session.delete(expense)
            await self._session.delete(instance)
        # Without ORM relationships the unit of work cannot order these deletes
        # by foreign keys itself: flush the children before deleting the item.
        await self._session.flush()
        self._audit(
            "catalog_item.delete",
            item.id,
            {"layer": "personal", "cascaded_instances": len(instances)},
        )
        await self._repo.delete(item)

    async def _delete_shared(self, item: CatalogItem) -> None:
        if not self._is_admin:
            raise SharedRecordForbiddenError
        if not item.is_archived:
            raise ArchiveStateError("Archive the item first; active shared items are not deleted.")
        instances, expenses = await self._repo.count_references(item.id)
        if instances or expenses:
            raise ItemHasReferencesError(
                "The item is referenced by collection items or expenses and cannot be deleted."
            )
        self._audit("catalog_item.delete", item.id, {"layer": "shared"})
        await self._repo.delete(item)

    async def _check_references(
        self,
        *,
        country_id: int,
        series_id: int | None,
        denomination_id: int | None,
        composition_id: int | None = None,
    ) -> None:
        country = await self._session.get(Country, country_id)
        if country is None:
            raise BadReferenceError("Unknown countryId.")
        if series_id is not None:
            series = await self._session.get(CoinSeries, series_id)
            if series is None or series.country_id != country_id:
                raise BadReferenceError("Unknown seriesId or it belongs to another country.")
        if denomination_id is not None:
            denomination = await self._session.get(Denomination, denomination_id)
            if denomination is None or denomination.country_id != country_id:
                raise BadReferenceError("Unknown denominationId or it belongs to another country.")
        if composition_id is not None and await self._session.get(Material, composition_id) is None:
            raise BadReferenceError("Unknown compositionId.")

    def _audit(self, action: str, entity_id: int, details: dict[str, object] | None) -> None:
        self._session.add(
            AuditLog(
                user_id=self._user.id,
                action=action,
                entity_type="catalog_item",
                entity_id=str(entity_id),
                details=details,
            )
        )

    async def _images_for(self, item_ids: list[int]) -> dict[int, CatalogImages]:
        files = await self._media.visible_for_catalog_items(item_ids)
        by_item: dict[int, list[MediaFile]] = {}
        for media in files:
            if media.catalog_item_id is not None:
                by_item.setdefault(media.catalog_item_id, []).append(media)
        return {
            item_id: self._urls.pick_catalog_images(items) for item_id, items in by_item.items()
        }

    def _base_fields(self, row: CatalogRow, images: CatalogImages) -> dict[str, object]:
        item = row.item
        return {
            "id": item.id,
            "country": row.country,
            "series_name": row.series_name,
            "denomination": denomination_out(row.denomination, self._locale),
            "year": item.issue_year,
            "title": display_title(item, self._locale),
            "title_original": item.title_original,
            "original_lang": item.original_lang,
            "title_uk": item.title_uk,
            "title_uk_source": item.title_uk_source,
            "title_en": item.title_en,
            "title_en_source": item.title_en_source,
            "variety": item.subtype,
            "catalog_number": item.catalog_km or item.catalog_uc or item.catalog_numista,
            "collection_group": item.collection_group,
            "metal_kind": item.metal_kind,
            "composition": material_out(row.composition, self._locale),
            "material": item.material,
            "market_price_uah": row.market_price_uah,
            "price_source": row.price_source,
            "price_observed_at": row.price_observed_at,
            "quantity_owned": row.quantity_owned,
            "purchase_total_uah": row.purchase_total_uah,
            "obverse_image_url": images.obverse_url,
            "reverse_image_url": images.reverse_url,
            "thumbnail_url": images.thumbnail_url,
            "is_own": item.created_by == self._user.id,
            "is_archived": item.is_archived,
            "archive_reason": item.archive_reason,
            "source_url": row.source_url,
        }

    def _list_item(self, row: CatalogRow, images: CatalogImages) -> CatalogListItem:
        return CatalogListItem(**self._base_fields(row, images))  # type: ignore[arg-type]

    def _card(self, row: CatalogRow, images: CatalogImages) -> CatalogCard:
        item = row.item
        return CatalogCard(
            **self._base_fields(row, images),  # type: ignore[arg-type]
            country_id=item.country_id,
            series_id=item.series_id,
            denomination_id=item.denomination_id,
            item_type=item.item_type,
            subtype=item.subtype,
            issue_date=item.issue_date,
            mintage_announced=item.mintage_announced,
            mintage_actual=item.mintage_actual,
            weight_grams=item.weight_grams,
            diameter_mm=item.diameter_mm,
            thickness_mm=item.thickness_mm,
            shape=item.shape,
            edge=item.edge,
            orientation=item.orientation,
            catalog_km=item.catalog_km,
            catalog_uc=item.catalog_uc,
            catalog_numista=item.catalog_numista,
            notes=item.notes,
            archived_at=item.archived_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
