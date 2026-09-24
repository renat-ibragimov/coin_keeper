"""Catalog use cases: listing, cards, price history, CRUD and archiving.

Permission semantics (docs/auth.md): an invisible item — someone else's
personal record — is a 404; a visible shared record the user may not touch is
a 403.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.locale import DEFAULT_LOCALE, LOCALE_EN, LOCALE_UK, pick_name
from app.db.session import get_session_factory
from app.models import (
    AuditLog,
    CatalogItem,
    CoinSeries,
    Country,
    Denomination,
    EdgeType,
    Material,
    QualityType,
    User,
)
from app.models.enums import TranslationSource, UserRole
from app.reference_data.denominations import render_label
from app.repositories.catalog import CatalogFilters, CatalogRepository, CatalogRow
from app.repositories.collection import CollectionRepository
from app.repositories.media import MediaRepository
from app.repositories.rates import RateRepository
from app.repositories.users import UserRepository
from app.schemas.catalog import (
    ArchiveStateOut,
    CatalogCard,
    CatalogCollectionItemOut,
    CatalogItemCreate,
    CatalogItemUpdate,
    CatalogListItem,
    CatalogSummaryOut,
    CoinDenomination,
    CoinDescriptions,
    CoinEdgeType,
    CoinMaterial,
    CoinQualityType,
    NewCatalogItemIn,
    PriceHistoryItem,
    PublicCatalogCard,
    PublicCatalogListItem,
)
from app.services.media_urls import (
    CatalogImages,
    MediaUrlBuilder,
    image_out,
    images_by_catalog_item,
)
from app.services.translation import TranslationResult, translate_coin_title

logger = logging.getLogger("app.services.catalog")


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


class DraftStateError(CatalogError):
    pass


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
    """title_{locale} → title_original (docs/business-rules.md)."""
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


def edge_type_out(edge_type: EdgeType | None, locale: str) -> CoinEdgeType | None:
    if edge_type is None:
        return None
    return CoinEdgeType(
        id=edge_type.id,
        code=edge_type.code,
        name=edge_type.name_uk if locale == "uk" else edge_type.name_en,
    )


def quality_type_out(quality_type: QualityType | None, locale: str) -> CoinQualityType | None:
    if quality_type is None:
        return None
    return CoinQualityType(
        id=quality_type.id,
        code=quality_type.code,
        name=quality_type.name_uk if locale == "uk" else quality_type.name_en,
    )


def _descriptions_json(
    locale: str, *, general: str | None, obverse: str | None, reverse: str | None
) -> dict[str, object] | None:
    """The `descriptions` column as docs/data-model.md fixes its shape:
    every locale key and every part key present, `null` where there is no
    text. Nothing typed at all leaves the column NULL — an untouched row,
    not a row full of nulls."""
    texts = {
        "general": (general or "").strip() or None,
        "obverse": (obverse or "").strip() or None,
        "reverse": (reverse or "").strip() or None,
    }
    if not any(texts.values()):
        return None
    empty = {"general": None, "obverse": None, "reverse": None}
    return {
        LOCALE_UK: texts if locale == LOCALE_UK else empty,
        LOCALE_EN: texts if locale != LOCALE_UK else empty,
    }


def description_out(descriptions: dict[str, object] | None, locale: str) -> CoinDescriptions | None:
    """Text for the requested locale, falling back to the other one where the
    parser found nothing to write there (docs/data-model.md)."""
    if not descriptions:
        return None
    other = "en" if locale == "uk" else "uk"
    primary = descriptions.get(locale)
    fallback = descriptions.get(other)

    def pick(key: str) -> str | None:
        for locale_texts in (primary, fallback):
            if isinstance(locale_texts, dict):
                value = locale_texts.get(key)
                if isinstance(value, str):
                    return value
        return None

    general, obverse, reverse = pick("general"), pick("obverse"), pick("reverse")
    if general is None and obverse is None and reverse is None:
        return None
    return CoinDescriptions(general=general, obverse=obverse, reverse=reverse)


def _artist_name(entry: object, locale: str) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        other = "en" if locale == "uk" else "uk"
        value = entry.get(locale) or entry.get(other)
        return value if isinstance(value, str) else None
    return None


def artist_names(artists: dict[str, object] | None, role: str, locale: str) -> list[str]:
    if not artists:
        return []
    entries = artists.get(role)
    if not isinstance(entries, list):
        return []
    names = (_artist_name(entry, locale) for entry in entries)
    return [name for name in names if name]


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
        self._users = UserRepository(session)
        self._rates = RateRepository(session)
        self._urls = MediaUrlBuilder()

    # --------------------------------------------------------------- reading

    async def list_catalog(
        self,
        filters: CatalogFilters,
        *,
        limit: int,
        offset: int,
        require_confirmed: bool = True,
        apply_storefront: bool = True,
    ) -> tuple[list[CatalogListItem], int]:
        """`require_confirmed=False` is for a caller about the user's own
        collection rather than the catalogue browse experience (a series
        screen) -- never from a request filter, see storefront_visible()
        (app/repositories/catalog.py, docs/business-rules.md, BR-13a).
        `apply_storefront=False` goes one further and is the typeahead's
        alone: see the same function's docstring."""
        settings = await self._users.get_settings(self._user.id)
        filters.show_packaging_variants = settings is None or settings.show_packaging_variants
        page = await self._repo.list_items(
            filters,
            limit=limit,
            offset=offset,
            require_confirmed=require_confirmed,
            apply_storefront=apply_storefront,
        )
        images = await self._images_for([row.item.id for row in page.rows])
        items = [
            self._list_item(row, images.get(row.item.id, CatalogImages())) for row in page.rows
        ]
        return items, page.total

    async def summary(self, filters: CatalogFilters) -> CatalogSummaryOut:
        """The "Каталог" KPI tiles for the filters currently applied, always
        under the catalogue's own `require_confirmed` gate (BR-13a) -- the same
        gate `list_catalog` uses, so the tiles never report a coverage the
        list below could not possibly show."""
        settings = await self._users.get_settings(self._user.id)
        filters.show_packaging_variants = settings is None or settings.show_packaging_variants
        data = await self._repo.summary(filters)
        return CatalogSummaryOut(
            total=data.total,
            owned=data.owned,
            missing=data.missing,
            purchase_total_uah=data.purchase_total_uah,
            missing_budget_uah=data.missing_budget_uah,
            unpriced_missing=data.unpriced_missing,
        )

    async def list_confirmed_materials(self, country_id: int | None) -> list[CoinMaterial]:
        materials = await self._repo.list_confirmed_materials(country_id)
        return [out for material in materials if (out := material_out(material, self._locale))]

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
        collection_repo = CollectionRepository(
            self._session, owner_id=self._user.id, locale=self._locale
        )
        instances = await collection_repo.list_for_item(item_id)
        supporting_by_instance = await collection_repo.supporting_expenses_by_instance(
            [instance.id for instance, _ in instances]
        )
        out = []
        for instance, storage_location in instances:
            total_uah = (
                (instance.purchase_price or Decimal(0))
                * (instance.purchase_rate_uah or Decimal(1))
                * instance.quantity
            )
            # The rate on THIS instance's own purchase date, not today's --
            # what it cost then, not a live estimate (docs/business-rules.md,
            # BR-6).
            usd_rate, eur_rate = (
                (
                    await self._rates.rate_on("USD", instance.acquisition_date),
                    await self._rates.rate_on("EUR", instance.acquisition_date),
                )
                if instance.acquisition_date is not None
                else (None, None)
            )
            out.append(
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
                    total_uah=total_uah,
                    total_usd=total_uah / usd_rate if usd_rate else None,
                    total_eur=total_uah / eur_rate if eur_rate else None,
                    supporting_expenses_uah=supporting_by_instance.get(instance.id),
                    storage_location=storage_location,
                    notes=instance.notes,
                )
            )
        return out

    # --------------------------------------------------------------- writing

    async def create_item(self, payload: CatalogItemCreate) -> CatalogCard:
        if payload.shared and not self._is_admin:
            raise SharedRecordForbiddenError
        item = await self._insert(
            payload.model_dump(exclude={"shared"}),
            created_by=None if payload.shared else self._user.id,
        )
        return await self.get_card(item.id)

    async def create_personal_item(self, payload: NewCatalogItemIn) -> CatalogItem:
        """A personal item entered on the purchase form, in the caller's transaction.

        Returns the row rather than a card on purpose: the caller is
        CollectionService, which goes on to create the instance and the
        purchase expense before anything is committed (docs/business-rules.md,
        BR-4). Both language slots start out holding the typed text, exactly
        as a new storage location does, and the background job replaces the
        one that is a translation rather than a copy.
        """
        values = payload.model_dump()
        title = values["title_original"]
        descriptions = _descriptions_json(
            self._locale,
            general=values.pop("description"),
            obverse=values.pop("description_obverse"),
            reverse=values.pop("description_reverse"),
        )
        return await self._insert(
            {
                **values,
                "title_uk": title,
                "title_uk_source": TranslationSource.MANUAL,
                "title_en": title,
                "title_en_source": TranslationSource.MANUAL,
                "descriptions": descriptions,
            },
            created_by=self._user.id,
        )

    async def _insert(self, values: dict[str, Any], *, created_by: int | None) -> CatalogItem:
        await self._check_references(
            country_id=values["country_id"],
            series_id=values.get("series_id"),
            denomination_id=values.get("denomination_id"),
            composition_id=values.get("composition_id"),
            edge_type_id=values.get("edge_type_id"),
            quality_type_id=values.get("quality_type_id"),
        )
        item = CatalogItem(**values, created_by=created_by)
        await self._repo.add(item)
        return item

    async def update_item(self, item_id: int, payload: CatalogItemUpdate) -> CatalogCard:
        item = await self._get_writable(item_id)
        changes = payload.model_dump(exclude_unset=True)
        description_fields = {
            key: changes.pop(key)
            for key in ("description", "description_obverse", "description_reverse")
            if key in changes
        }
        await self._check_references(
            country_id=changes.get("country_id", item.country_id),
            series_id=changes.get("series_id", item.series_id),
            denomination_id=changes.get("denomination_id", item.denomination_id),
            composition_id=changes.get("composition_id", item.composition_id),
            edge_type_id=changes.get("edge_type_id", item.edge_type_id),
            quality_type_id=changes.get("quality_type_id", item.quality_type_id),
        )
        for field_name, value in changes.items():
            setattr(item, field_name, value)
        # A title slot set through this endpoint is a human edit, whoever makes
        # it — an admin correcting a shared record or an owner naming a personal
        # one — never the pipeline's official wording or its own LLM guess.
        if "title_uk" in changes:
            item.title_uk_source = TranslationSource.MANUAL
        if "title_en" in changes:
            item.title_en_source = TranslationSource.MANUAL
        if description_fields:
            current = description_out(item.descriptions, self._locale)
            item.descriptions = _descriptions_json(
                self._locale,
                general=description_fields.get("description", current.general if current else None),
                obverse=description_fields.get(
                    "description_obverse", current.obverse if current else None
                ),
                reverse=description_fields.get(
                    "description_reverse", current.reverse if current else None
                ),
            )
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

    async def publish_draft(self, item_id: int) -> CatalogCard:
        item = await self._get_shared_for_admin(item_id)
        if item.is_archived or item.status != "draft":
            raise DraftStateError
        item.status = "active"
        self._audit("catalog_item.publish", item.id, None)
        await self._session.flush()
        return await self.get_card(item.id)

    async def reject_draft(self, item_id: int, reason: str) -> ArchiveStateOut:
        item = await self._get_shared_for_admin(item_id)
        if item.is_archived or item.status != "draft":
            raise DraftStateError
        item.status = "rejected"
        item.is_archived = True
        item.archived_at = datetime.now(UTC)
        item.archive_reason = reason
        self._audit("catalog_item.reject", item.id, {"reason": reason})
        await self._session.flush()
        return ArchiveStateOut(
            is_archived=True, archived_at=item.archived_at, archive_reason=reason
        )

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
        purchase expenses, in one transaction (docs/business-rules.md, 10).
        """
        collection = CollectionRepository(self._session, owner_id=self._user.id)
        instances = await collection.list_for_item(item.id)
        for instance, _storage_location in instances:
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
        edge_type_id: int | None = None,
        quality_type_id: int | None = None,
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
        if edge_type_id is not None and await self._session.get(EdgeType, edge_type_id) is None:
            raise BadReferenceError("Unknown edgeTypeId.")
        if (
            quality_type_id is not None
            and await self._session.get(QualityType, quality_type_id) is None
        ):
            raise BadReferenceError("Unknown qualityTypeId.")

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
        """The catalog photo, or the owner's own — see images_by_catalog_item."""
        return await images_by_catalog_item(self._media, self._urls, item_ids)

    def _base_fields(self, row: CatalogRow, images: CatalogImages) -> dict[str, object]:
        item = row.item
        return {
            "id": item.id,
            "country": row.country,
            "series_name": row.series_name,
            "denomination": denomination_out(row.denomination, self._locale),
            "denomination_text": item.denomination_text,
            "year": item.issue_year,
            "issue_date": item.issue_date,
            "title": display_title(item, self._locale),
            "title_original": item.title_original,
            "original_lang": item.original_lang,
            "title_uk": item.title_uk,
            "title_uk_source": item.title_uk_source,
            "title_en": item.title_en,
            "title_en_source": item.title_en_source,
            "variety": item.subtype,
            # A named number wins; the unattributed one is the fallback a
            # hand-entered coin brings (docs/data-model.md).
            "catalog_number": (
                item.catalog_km or item.catalog_uc or item.catalog_numista or item.catalog_number
            ),
            "collection_group": item.collection_group,
            "metal_kind": item.metal_kind,
            "composition": material_out(row.composition, self._locale),
            "material": item.material,
            "market_price_uah": row.market_price_uah,
            "price_source": row.price_source,
            "price_observed_at": row.price_observed_at,
            "quantity_owned": row.quantity_owned,
            "purchase_total_uah": row.purchase_total_uah,
            "purchase_total_usd": row.purchase_total_usd,
            "purchase_total_eur": row.purchase_total_eur,
            "supporting_expenses_uah": row.supporting_expenses_uah,
            "obverse_image": image_out(images.obverse),
            "reverse_image": image_out(images.reverse),
            "thumbnail_url": images.thumbnail_url,
            "is_own": item.created_by == self._user.id if self._user else False,
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
            mintage_announced=item.mintage_announced,
            mintage_actual=item.mintage_actual,
            weight_grams=item.weight_grams,
            diameter_mm=item.diameter_mm,
            thickness_mm=item.thickness_mm,
            shape=item.shape,
            edge_type=edge_type_out(row.edge_type, self._locale),
            edge=item.edge,
            orientation=item.orientation,
            quality_type=quality_type_out(row.quality_type, self._locale),
            quality=item.quality,
            catalog_km=item.catalog_km,
            catalog_uc=item.catalog_uc,
            catalog_numista=item.catalog_numista,
            notes=item.notes,
            description=description_out(item.descriptions, self._locale),
            designers=artist_names(item.artists, "designers", self._locale),
            sculptors=artist_names(item.artists, "sculptors", self._locale),
            archived_at=item.archived_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )


def apply_title_translation(item: CatalogItem, result: TranslationResult) -> None:
    """The detected language's own slot stays exactly what the collector typed
    -- only the other one is filled in by the model. Pure and DB-free on
    purpose, the same way storage locations do it (app/services/storage_locations.py):
    the one part with a real judgment call is testable without a database.
    """
    if result.language != "uk":
        item.title_uk = result.name_uk
        item.title_uk_source = TranslationSource.LLM
    if result.language != "en":
        item.title_en = result.name_en
        item.title_en_source = TranslationSource.LLM


async def translate_title_in_background(item_id: int) -> None:
    """The BackgroundTasks entry point for a hand-entered coin: opens its own
    session, since the request's is long gone by the time this runs.

    Every early return is logged. A silent no-op leaves the record showing the
    collector's own wording in both language slots forever, with nothing in
    the interface to explain why -- the only way to notice is a log line (the
    same lesson as storage locations, docs/business-rules.md, BR-16).
    """
    api_key = get_settings().anthropic_api_key
    if not api_key:
        logger.warning("catalog title translation skipped: no ANTHROPIC_API_KEY configured")
        return
    async with get_session_factory()() as session:
        try:
            item = await session.get(CatalogItem, item_id)
            if item is None:
                logger.warning("catalog item %s vanished before translation ran", item_id)
                return
            country = await session.get(Country, item.country_id)
            result = await translate_coin_title(
                item.title_original,
                api_key,
                country=(country.name_en or country.name_original) if country else None,
                year=item.issue_year,
            )
            if result is None:
                logger.warning("catalog item %s: translate_coin_title returned None", item_id)
                return
            apply_title_translation(item, result)
            await session.commit()
            logger.info(
                "catalog item %s title translated (original language %s)", item_id, result.language
            )
        except Exception:
            logger.exception("catalog title translation failed for %s", item_id)


class PublicCatalogService(CatalogService):
    """Reuse catalog presentation, with read-only shared queries and an allowlisted response."""

    def __init__(self, session: AsyncSession, locale: str = DEFAULT_LOCALE) -> None:
        from app.repositories.public_catalog import PublicCatalogRepository

        self._session = session
        self._user = None  # type: ignore[assignment]  # Anonymous presentation only.
        self._locale = locale
        self._repo = PublicCatalogRepository(session, locale)  # type: ignore[assignment]
        self._media = MediaRepository(session, user_id=-1)
        self._urls = MediaUrlBuilder()

    async def list_catalog(  # type: ignore[override]
        self, filters: CatalogFilters, *, limit: int, offset: int
    ) -> tuple[list[PublicCatalogListItem], int]:
        page = await self._repo.list_items(filters, limit=limit, offset=offset)
        images = await self._images_for([row.item.id for row in page.rows])
        return [
            PublicCatalogListItem.model_validate(
                self._list_item(row, images.get(row.item.id, CatalogImages())).model_dump()
            )
            for row in page.rows
        ], page.total

    async def get_card(self, item_id: int) -> PublicCatalogCard:  # type: ignore[override]
        row = await self._repo.get_row(item_id)
        if row is None:
            raise ItemNotFoundError
        images = await self._images_for([item_id])
        return PublicCatalogCard.model_validate(
            self._card(row, images.get(item_id, CatalogImages())).model_dump()
        )
