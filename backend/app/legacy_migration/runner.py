"""Orchestration of the legacy migration.

Write order is the 14 steps of docs/09-data-migration.md, strictly by
dependency. Identifiers are preserved, so every foreign key survives and no
old-to-new id table is needed; sequences are reset afterwards.

Each step commits on its own: a failure while uploading images must not roll
back the catalog.
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.legacy_migration import convert, media, prices, reader
from app.legacy_migration.report import MigrationReport
from app.models import (
    Base,
    CatalogItem,
    CoinSeries,
    CollectionItem,
    Country,
    Currency,
    Denomination,
    ExchangeRate,
    Expense,
    MarketPriceSnapshot,
    Material,
    MediaFile,
    PriceSourceLink,
    UcoinCatalogSource,
    User,
    UserSettings,
)
from app.models.enums import UserRole
from app.reference_data import countries as country_seed
from app.reference_data import materials as material_seed
from app.reference_data.denominations import DenominationParseError, parse_label

logger = logging.getLogger("app.legacy_migration")


def _translation_or_none(value: Any, original: str) -> str | None:
    """A translated slot repeating the original is not a translation.

    The desktop application wrote the same string into all three name columns;
    keeping those copies would make every record look translated.
    """
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text == original.strip() else text


COLLECTION_GROUPS = frozenset({"circulation", "commemorative", "collector", "other"})
METAL_KINDS = frozenset({"precious", "base", "unknown"})
MEDIA_ROLES = frozenset({"obverse", "reverse", "edge", "additional"})
MATCH_STATUSES = frozenset({"suggested", "confirmed", "rejected"})
EXPENSE_CATEGORIES = frozenset(
    {
        "coin_purchase",
        "delivery",
        "album",
        "holder",
        "storage",
        "grading",
        "literature",
        "photo_equipment",
        "other",
    }
)

# Models whose ids come from the source; their sequences must be moved past the
# highest inserted id afterwards.
SEQUENCED_MODELS: tuple[tuple[str, Any], ...] = (
    ("users", User),
    ("denominations", Denomination),
    ("coin_series", CoinSeries),
    ("catalog_items", CatalogItem),
    ("exchange_rates", ExchangeRate),
    ("market_price_snapshots", MarketPriceSnapshot),
    ("price_source_links", PriceSourceLink),
    ("collection_items", CollectionItem),
    ("expenses", Expense),
    ("media_files", MediaFile),
    ("ucoin_catalog_sources", UcoinCatalogSource),
)

MEDIA_UPLOAD_BATCH = 50

# PostgreSQL takes at most 32767 bind parameters in one statement, and a
# multi-row INSERT spends one per column per row. Inserting a whole table in a
# single statement blows past that: catalog_items is 3063 rows of 32 columns,
# roughly 98k parameters, which is what the first real migration run died on.
# The budget is deliberately below the limit so no column count lands exactly
# on the edge.
MAX_BIND_PARAMETERS = 30000

# Foreign keys that must be checked before inserting, per table. SQLite does
# not enforce foreign keys unless PRAGMA foreign_keys is on, and the desktop
# app never turned it on — so the source may well hold references to rows that
# do not exist. PostgreSQL does enforce them, and without this guard the whole
# run would die on an opaque asyncpg error halfway through.
REFERENCE_GUARDS: dict[str, tuple[tuple[str, str], ...]] = {
    "denominations": (("country_id", "countries"), ("currency_code", "currencies")),
    "coin_series": (("country_id", "countries"),),
    "catalog_items": (
        ("country_id", "countries"),
        ("series_id", "coin_series"),
        ("denomination_id", "denominations"),
    ),
    "exchange_rates": (("currency_code", "currencies"),),
    "market_price_snapshots": (
        ("catalog_item_id", "catalog_items"),
        ("currency_code", "currencies"),
    ),
    "price_source_links": (("catalog_item_id", "catalog_items"),),
    "collection_items": (
        ("catalog_item_id", "catalog_items"),
        ("purchase_currency", "currencies"),
    ),
    "expenses": (
        ("currency_code", "currencies"),
        ("catalog_item_id", "catalog_items"),
        ("collection_item_id", "collection_items"),
        ("series_id", "coin_series"),
    ),
    "media_files": (
        ("catalog_item_id", "catalog_items"),
        ("collection_item_id", "collection_items"),
    ),
}


@dataclass(slots=True)
class MigrationOptions:
    sqlite_path: Path
    media_path: Path | None
    owner_email: str
    owner_password: str
    dry_run: bool = False
    skip_media: bool = False
    resume: bool = False
    expectations: Mapping[str, Any] | None = None


class MigrationError(RuntimeError):
    """Migration cannot proceed."""


class MigrationRunner:
    def __init__(
        self,
        session: AsyncSession,
        options: MigrationOptions,
        report: MigrationReport,
        storage: Any = None,
    ) -> None:
        self._session = session
        self._options = options
        self._report = report
        self._storage = storage
        self._owner_id: int | None = None
        # Keys that actually made it in, used to catch dangling references.
        self._known_keys: dict[str, set[Any]] = {}
        # Countries are reference data owned by the schema (migration 0003
        # seeds every issuer), so the legacy ids are mapped onto them rather
        # than inserted; everything below carries the mapped id.
        self._country_ids: dict[int, int] = {}
        self._country_langs: dict[int, str] = {}
        self._country_codes: dict[int, str | None] = {}
        self._material_ids: dict[str, int] = {}

    # ------------------------------------------------------------------ entry

    async def run(self) -> MigrationReport:
        options = self._options
        self._report.dry_run = options.dry_run
        self._report.skip_media = options.skip_media

        with reader.open_legacy(options.sqlite_path) as connection:
            self._report.source_counts = reader.source_counts(connection)
            await self._guard_non_empty_target()

            await self._step_owner()
            await self._step_reference(connection)
            await self._step_catalog(connection)
            await self._step_prices(connection)
            await self._step_collection(connection)
            await self._step_media(connection)
            await self._step_settings(connection)

            if not options.dry_run:
                await self._reset_sequences()
            await self._verify(connection)

        return self._report

    # ----------------------------------------------------------- preconditions

    async def _guard_non_empty_target(self) -> None:
        existing = await self._scalar(select(func.count()).select_from(CatalogItem))
        if existing and not self._options.resume:
            msg = (
                f"target database already holds {existing} catalog items; "
                "re-run with --resume to continue on top of it"
            )
            raise MigrationError(msg)
        if existing:
            logger.warning("resuming on a non-empty database (%s catalog items)", existing)

    # ------------------------------------------------------------- step 1: user

    async def _step_owner(self) -> None:
        """The owner is created ready to use: verified, active, admin."""
        existing = await self._scalar(
            select(User.id).where(User.email == self._options.owner_email)
        )
        if existing is not None:
            self._owner_id = int(existing)
            self._report.owner_user_id = self._owner_id
            self._report.migrated["users"] = 0
            return

        if self._options.dry_run:
            # Nothing is written, but the rest of the run needs an owner id.
            self._owner_id = 0
            self._report.migrated["users"] = 1
            return

        user = User(
            email=self._options.owner_email,
            password_hash=hash_password(self._options.owner_password),
            role=UserRole.ADMIN,
            is_active=True,
            email_verified=True,
            locale="uk",
        )
        self._session.add(user)
        await self._session.flush()
        self._session.add(UserSettings(user_id=user.id, locale="uk"))
        await self._session.commit()

        self._owner_id = int(user.id)
        # Only the id reaches the report: never the address or the password.
        self._report.owner_user_id = self._owner_id
        self._report.migrated["users"] = 1

    # -------------------------------------------------- steps 2-5: reference data

    async def _step_reference(self, connection: sqlite3.Connection) -> None:
        await self._copy(
            connection,
            "currencies",
            Currency,
            self._currency_row,
            conflict_index=["code"],
        )
        await self._map_countries(connection)
        await self._load_materials()
        await self._copy(connection, "denominations", Denomination, self._denomination_row)
        await self._copy(connection, "coin_series", CoinSeries, self._series_row)

    def _currency_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "code": row["code"],
            "name": row["name"],
            "symbol": row.get("symbol"),
            "decimal_places": int(row.get("decimal_places") or 2),
        }

    async def _map_countries(self, connection: sqlite3.Connection) -> None:
        """Match every source country to a seeded one; insert what is missing.

        The seed knows the country under several names ("Украина", "Україна",
        "Ukraine"), which is how a legacy row finds its target without a
        duplicate. Its own id is not preserved: the target already holds every
        issuer, and one of them almost certainly sits on that id.
        """
        existing = (await self._session.execute(select(Country))).scalars().all()
        by_code = {country.code: country for country in existing if country.code}
        by_name: dict[str, Country] = {}
        for country in existing:
            for name in (country.name_original, country.name_uk, country.name_en):
                if name:
                    by_name.setdefault(name.casefold(), country)

        matched = 0
        for row in reader.read_table(connection, "countries"):
            legacy_id = int(row["id"])
            seed = self._country_seed_for(row)
            target = by_code.get(seed.code) if seed else None
            if target is None:
                for name in (row.get("name_original"), row.get("name_ru"), row.get("name_en")):
                    if name and name.casefold() in by_name:
                        target = by_name[name.casefold()]
                        break
            if target is not None:
                self._country_ids[legacy_id] = int(target.id)
                self._country_langs[legacy_id] = target.original_lang
                self._country_codes[legacy_id] = target.code
                matched += 1
                continue
            self._country_ids[legacy_id] = await self._insert_country(row, seed)
            self._country_langs[legacy_id] = seed.original_lang if seed else "uk"
            self._country_codes[legacy_id] = seed.code if seed else None

        self._known_keys["countries"] = set(self._country_ids.values())
        self._report.migrated["countries"] = len(self._country_ids)
        logger.info("countries: %s of %s matched a seeded row", matched, len(self._country_ids))

    @staticmethod
    def _country_seed_for(row: Mapping[str, Any]) -> country_seed.CountrySeed | None:
        code = row.get("code")
        if code:
            found = country_seed.find_by_code(str(code))
            if found is not None:
                return found
        for name in (row.get("name_original"), row.get("name_ru"), row.get("name_en")):
            if name:
                found = country_seed.find_by_name(str(name))
                if found is not None:
                    return found
        return None

    async def _insert_country(
        self, row: Mapping[str, Any], seed: country_seed.CountrySeed | None
    ) -> int:
        """A country the seed does not know: kept under its own name."""
        self._report.conversion_warnings.append(
            f"countries#{row.get('id')}: {row.get('name_original')!r} is not in the seed, created"
        )
        if self._options.dry_run:
            return int(row["id"])
        country = Country(
            code=seed.code if seed else None,
            name_original=seed.name_original if seed else str(row["name_original"]),
            original_lang=seed.original_lang if seed else "uk",
            name_uk=seed.name_uk if seed else None,
            name_en=seed.name_en if seed else row.get("name_en"),
            collect_variants=convert.to_bool(row.get("collect_variants")),
            is_active=convert.to_bool(row.get("is_active")),
        )
        self._session.add(country)
        await self._session.flush()
        return int(country.id)

    async def _load_materials(self) -> None:
        rows = (await self._session.execute(select(Material))).scalars().all()
        self._material_ids = {material.code: int(material.id) for material in rows}

    def _country_id(self, legacy_id: Any) -> Any:
        return self._country_ids.get(int(legacy_id), legacy_id) if legacy_id is not None else None

    def _denomination_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """The legacy label parsed into value + unit + currency.

        The country code decides between the Ukrainian копійка and the Soviet
        копейка; nothing else in the label distinguishes them.
        """
        legacy_country = int(row["country_id"])
        try:
            parsed = parse_label(
                row["label_original"], country_code=self._country_codes.get(legacy_country)
            )
        except DenominationParseError as exc:
            raise convert.ConversionError(str(exc)) from exc
        return {
            "id": row["id"],
            "country_id": self._country_id(legacy_country),
            "currency_code": parsed.currency_code,
            "value": parsed.value,
            "unit": parsed.unit,
            "sort_order": parsed.minor_units,
            "is_active": convert.to_bool(row.get("is_active")),
        }

    def _series_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "country_id": self._country_id(row["country_id"]),
            "name_original": row["name_original"],
            "original_lang": self._country_langs.get(int(row["country_id"]), "uk"),
            "name_uk": None,
            "name_en": _translation_or_none(row.get("name_en"), row["name_original"]),
            "description": row.get("description"),
            "start_year": row.get("start_year"),
            "end_year": row.get("end_year"),
            "created_at": convert.to_timestamptz(row.get("created_at")),
            "updated_at": convert.to_timestamptz(row.get("updated_at")),
        }

    # ------------------------------------------------ steps 6-7: catalog, rates

    async def _step_catalog(self, connection: sqlite3.Connection) -> None:
        await self._copy(connection, "catalog_items", CatalogItem, self._catalog_row)
        await self._copy(connection, "exchange_rates", ExchangeRate, self._rate_row)

    def _catalog_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        legacy_country = int(row["country_id"])
        title_original = str(row.get("title_original") or "").strip()
        if not title_original:
            # A blank original with a Russian title: the Russian one is it.
            title_original = str(row.get("title_ru") or "").strip()
        composition = material_seed.parse_material(row.get("material"))
        return {
            "id": row["id"],
            "item_type": row.get("item_type") or "coin",
            "country_id": self._country_id(legacy_country),
            "series_id": row.get("series_id"),
            "denomination_id": row.get("denomination_id"),
            "collection_group": convert.to_enum_value(
                row.get("collection_group"), COLLECTION_GROUPS, default="other"
            ),
            "subtype": row.get("subtype"),
            "title_original": title_original,
            "original_lang": self._country_langs.get(legacy_country, "uk"),
            # title_uk stays empty: the legacy base has no Ukrainian titles.
            # The Ukrainian pipeline fills it in (docs/05-integrations.md).
            "title_uk": None,
            "title_uk_source": None,
            "title_en": _translation_or_none(row.get("title_en"), title_original),
            "title_en_source": None,
            "issue_year": row["issue_year"],
            "issue_date": convert.to_date(row.get("issue_date")),
            "mintage_announced": row.get("mintage_announced"),
            "mintage_actual": row.get("mintage_actual"),
            "composition_id": self._material_ids.get(composition.composition or ""),
            # Only what the parser could not read stays as text.
            "material": None if composition.composition else row.get("material"),
            "metal_kind": convert.to_enum_value(
                row.get("metal_kind"), METAL_KINDS, default="unknown"
            ),
            "weight_grams": row.get("weight_grams") or composition.weight_grams,
            "diameter_mm": row.get("diameter_mm") or composition.diameter_mm,
            "thickness_mm": row.get("thickness_mm"),
            "shape": row.get("shape"),
            "edge": row.get("edge"),
            "orientation": row.get("orientation"),
            "catalog_km": row.get("catalog_km"),
            "catalog_uc": row.get("catalog_uc"),
            "catalog_numista": row.get("catalog_numista"),
            "notes": row.get("notes"),
            "source_key": row.get("source_key"),
            # The migrated catalog becomes the shared one.
            "created_by": None,
            "is_archived": False,
            "created_at": convert.to_timestamptz(row.get("created_at")),
            "updated_at": convert.to_timestamptz(row.get("updated_at")),
        }

    def _rate_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "currency_code": row["currency_code"],
            "rate_uah": convert.to_rate(row["rate_uah"]),
            "effective_date": convert.to_date(row["effective_date"]),
            "fetched_at": convert.to_timestamptz(row.get("fetched_at")),
            "source": row.get("source") or "NBU",
        }

    # ----------------------------------------- steps 8-9: prices and their links

    async def _step_prices(self, connection: sqlite3.Connection) -> None:
        rows = reader.read_table(connection, "market_price_snapshots")
        issue_years = {
            int(item["id"]): item.get("issue_year")
            for item in reader.read_table(connection, "catalog_items")
        }
        currencies = [row["code"] for row in reader.read_table(connection, "currencies")]

        candidates: list[prices.SnapshotUnderTest] = []
        payloads: dict[int, dict[str, Any]] = {}
        for row in rows:
            price = convert.to_money(row["price"]) or Decimal(0)
            snapshot_id = int(row["id"])
            candidates.append(
                prices.SnapshotUnderTest(
                    snapshot_id=snapshot_id,
                    catalog_item_id=int(row["catalog_item_id"]),
                    price=price,
                    currency_code=row.get("currency_code"),
                    issue_year=issue_years.get(int(row["catalog_item_id"])),
                )
            )
            payload, invalid = convert.to_jsonb(row.get("raw_payload_json"))
            if invalid:
                self._report.invalid_json_payloads.append(snapshot_id)
            payloads[snapshot_id] = {"price": price, "payload": payload, "row": row}

        verdicts = prices.evaluate_all(candidates, currencies)
        self._report.suspect_total = sum(1 for v in verdicts.values() if v.is_suspect)
        for candidate in candidates:
            verdict = verdicts[candidate.snapshot_id]
            for rule in verdict.rules:
                self._report.note_suspect(
                    rule,
                    {
                        "snapshotId": candidate.snapshot_id,
                        "catalogItemId": candidate.catalog_item_id,
                        "price": str(candidate.price),
                        "currency": candidate.currency_code,
                    },
                )

        def build(row: Mapping[str, Any]) -> dict[str, Any]:
            snapshot_id = int(row["id"])
            prepared = payloads[snapshot_id]
            return {
                "id": snapshot_id,
                "catalog_item_id": row["catalog_item_id"],
                "source": row["source"],
                "grade": row.get("grade"),
                "price": prepared["price"],
                "currency_code": row["currency_code"],
                "observed_at": convert.to_timestamptz(row["observed_at"]),
                "source_url": row.get("source_url"),
                "raw_payload": prepared["payload"],
                # Migrated snapshots came from external sources, not from a
                # user, so they are shared (docs/09-data-migration.md).
                "created_by": None,
                "is_suspect": verdicts[snapshot_id].is_suspect,
            }

        await self._insert_rows("market_price_snapshots", MarketPriceSnapshot, rows, build)
        await self._copy(connection, "price_source_links", PriceSourceLink, self._link_row)

    def _link_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "catalog_item_id": row["catalog_item_id"],
            "source": row["source"],
            "external_id": row["external_id"],
            "match_status": convert.to_enum_value(
                row.get("match_status"), MATCH_STATUSES, default="confirmed"
            ),
            "matched_at": convert.to_timestamptz(row.get("matched_at")),
        }

    # ------------------------------------------ steps 10-11: collection, expenses

    async def _step_collection(self, connection: sqlite3.Connection) -> None:
        await self._copy(
            connection,
            "collection_items",
            CollectionItem,
            self._collection_row,
        )
        await self._copy(connection, "expenses", Expense, self._expense_row)

    def _collection_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "owner_id": self._owner_id,
            "catalog_item_id": row["catalog_item_id"],
            "variant_id": row.get("variant_id"),
            "quantity": int(row.get("quantity") or 1),
            "grade": row.get("grade"),
            "condition_notes": row.get("condition_notes"),
            "acquisition_date": convert.to_date(row.get("acquisition_date")),
            "acquisition_place": row.get("acquisition_place"),
            "seller": row.get("seller"),
            "purchase_price": convert.to_money(row.get("purchase_price")),
            "purchase_currency": row.get("purchase_currency"),
            "purchase_rate_uah": convert.to_rate(row.get("purchase_rate_uah")),
            "storage_location": row.get("storage_location"),
            "grading_company": row.get("grading_company"),
            "grading_number": row.get("grading_number"),
            "grading_grade": row.get("grading_grade"),
            "is_for_swap": convert.to_bool(row.get("is_for_swap")),
            "is_for_sale": convert.to_bool(row.get("is_for_sale")),
            "needs_replacement": convert.to_bool(row.get("needs_replacement")),
            "notes": row.get("notes"),
            "created_at": convert.to_timestamptz(row.get("created_at")),
            "updated_at": convert.to_timestamptz(row.get("updated_at")),
        }

    def _expense_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "owner_id": self._owner_id,
            "category": convert.to_enum_value(row["category"], EXPENSE_CATEGORIES, default="other"),
            "amount": convert.to_money(row["amount"]),
            "currency_code": row["currency_code"],
            "rate_uah": convert.to_rate(row.get("rate_uah")),
            "expense_date": convert.to_date(row["expense_date"]),
            "catalog_item_id": row.get("catalog_item_id"),
            "collection_item_id": row.get("collection_item_id"),
            "series_id": row.get("series_id"),
            "vendor": row.get("vendor"),
            "description": row.get("description"),
            "created_at": convert.to_timestamptz(row.get("created_at")),
        }

    # ----------------------------------------------------------- step 12: media

    async def _step_media(self, connection: sqlite3.Connection) -> None:
        rows = reader.read_table(connection, "media_files")

        if self._options.skip_media or self._options.media_path is None:
            # The whole step is deferred rather than half-done. Writing rows
            # now would mean a storage_key pointing at an object that was never
            # uploaded — and a row whose file turns out to be missing would be
            # kept, because without processing the file system is never
            # consulted. Re-running without the flag fills the table in.
            self._report.migrated["media_files"] = 0
            self._report.skipped["media_files_deferred"] = len(rows)
            return

        ucoin_items = self._ucoin_catalog_items(connection)
        owner_id = self._owner_id or 0
        process = True

        prepared_rows: list[dict[str, Any]] = []
        pending_uploads: list[media.PreparedMedia] = []

        for row in rows:
            outcome = media.prepare(
                row,
                owner_id=owner_id,
                media_root=self._options.media_path,
                ucoin_catalog_items=ucoin_items,
                process=process,
            )
            if outcome.missing_path is not None:
                # No file and no link: nothing to point at, so the row is dropped.
                self._report.media_missing_file.append(outcome.missing_path)
                self._bump_skip("media_files_without_file_or_url")
                continue
            if outcome.rejected is not None:
                path, reason = outcome.rejected
                self._report.media_rejected.append({"path": path, "reason": reason})
                self._bump_skip("media_files_rejected")
                continue

            item = outcome.prepared
            assert item is not None
            if item.external_url:
                self._report.media_external += 1
            else:
                self._report.media_stored += 1
                if item.processed is not None:
                    pending_uploads.append(item)

            source_name = item.source.value
            self._report.media_by_source[source_name] = (
                self._report.media_by_source.get(source_name, 0) + 1
            )
            prepared_rows.append(
                {
                    "id": item.legacy_id,
                    "catalog_item_id": item.catalog_item_id,
                    "collection_item_id": item.collection_item_id,
                    # Every migrated image belongs to the owner of the source
                    # database; that is what scopes uCoin images to the person
                    # who imported them (docs/09-data-migration.md).
                    "owner_id": owner_id or None,
                    "role": convert.to_enum_value(item.role, MEDIA_ROLES, default="additional"),
                    "source": item.source.value,
                    "license": None,
                    "attribution": None,
                    "storage_key": item.storage_key,
                    "external_url": item.external_url,
                    "thumbnail_key": item.thumbnail_key,
                    "mime_type": item.mime_type,
                    "width": item.width,
                    "height": item.height,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                    "created_at": convert.to_timestamptz(row.get("created_at")),
                }
            )

        await self._upload(pending_uploads)
        await self._insert_prepared("media_files", MediaFile, prepared_rows)

    def _ucoin_catalog_items(self, connection: sqlite3.Connection) -> frozenset[int]:
        """Catalog ids whose coin is known to come from uCoin."""
        found: set[int] = set()
        for row in reader.read_table(connection, "catalog_items"):
            if media.looks_like_ucoin(row.get("source_key")):
                found.add(int(row["id"]))
        for row in reader.read_table(connection, "price_source_links"):
            if media.looks_like_ucoin(row.get("source")) or media.looks_like_ucoin(
                row.get("external_id")
            ):
                found.add(int(row["catalog_item_id"]))
        return frozenset(found)

    async def _upload(self, items: Sequence[media.PreparedMedia]) -> None:
        if not items or self._options.dry_run or self._storage is None:
            return
        total = len(items)
        for index, item in enumerate(items, start=1):
            processed = item.processed
            if processed is None or item.storage_key is None:
                continue
            self._storage.put(item.storage_key, processed.original, processed.mime_type)
            if item.thumbnail_key:
                self._storage.put(item.thumbnail_key, processed.thumbnail, processed.mime_type)
            if index % MEDIA_UPLOAD_BATCH == 0 or index == total:
                print(f"  uploaded {index}/{total} images", flush=True)

    # -------------------------------------------------- steps 13-14: per-user data

    async def _step_settings(self, connection: sqlite3.Connection) -> None:
        rows = reader.read_table(connection, "ucoin_catalog_sources")

        def build(row: Mapping[str, Any]) -> dict[str, Any]:
            return {
                "id": row["id"],
                "owner_id": self._owner_id,
                "title": row["title"],
                "url": row["url"],
                "country": row.get("country"),
                "collection_group": convert.to_enum_value(
                    row.get("collection_group"), COLLECTION_GROUPS, default=None
                ),
                "last_import_at": convert.to_timestamptz(row.get("last_import_at")),
                "last_scanned": int(row.get("last_scanned") or 0),
                "last_inserted": int(row.get("last_inserted") or 0),
                "last_updated": int(row.get("last_updated") or 0),
                "last_skipped": int(row.get("last_skipped") or 0),
                "created_at": convert.to_timestamptz(row.get("created_at")),
                "updated_at": convert.to_timestamptz(row.get("updated_at")),
            }

        await self._insert_rows("ucoin_catalog_sources", UcoinCatalogSource, rows, build)
        await self._migrate_user_settings(connection)

    async def _migrate_user_settings(self, connection: sqlite3.Connection) -> None:
        """The legacy key/value settings table becomes one user_settings row."""
        settings = {
            str(row["key"]): row.get("value_json")
            for row in reader.read_table(connection, "settings")
        }
        values: dict[str, Any] = {}
        display_currency = _unwrap_json(settings.get("display_currency"))
        if isinstance(display_currency, str) and display_currency:
            values["display_currency"] = display_currency
        for legacy_key, column in (
            ("default_grade_commemorative", "default_grade_commemorative"),
            ("default_grade_circulation", "default_grade_circulation"),
        ):
            value = _unwrap_json(settings.get(legacy_key))
            if isinstance(value, str) and value:
                values[column] = value

        self._report.migrated["user_settings"] = 1
        if not values or self._options.dry_run or self._owner_id is None:
            return
        await self._session.execute(
            update(UserSettings).where(UserSettings.user_id == self._owner_id).values(**values)
        )
        await self._session.commit()

    # --------------------------------------------------------------- machinery

    async def _copy(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        model: type[Base],
        builder: Any,
        conflict_index: list[str] | None = None,
    ) -> None:
        rows = reader.read_table(connection, table_name)
        await self._insert_rows(table_name, model, rows, builder, conflict_index=conflict_index)

    async def _insert_rows(
        self,
        table_name: str,
        model: type[Base],
        rows: Sequence[Mapping[str, Any]],
        builder: Any,
        conflict_index: list[str] | None = None,
    ) -> None:
        prepared: list[dict[str, Any]] = []
        for row in rows:
            try:
                prepared.append(builder(row))
            except convert.ConversionError as exc:
                self._report.conversion_warnings.append(f"{table_name}#{row.get('id')}: {exc}")
                self._bump_skip(f"{table_name}_conversion_error")
        await self._insert_prepared(table_name, model, prepared, conflict_index=conflict_index)

    def _register_keys(self, table_name: str, rows: Sequence[Mapping[str, Any]]) -> None:
        key = "code" if table_name == "currencies" else "id"
        self._known_keys[table_name] = {row[key] for row in rows if row.get(key) is not None}

    def _drop_dangling(
        self, table_name: str, prepared: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove rows pointing at parents that are not there.

        Reported rather than fatal: one bad reference in a 5 MB database should
        not cost the whole migration.
        """
        guards = REFERENCE_GUARDS.get(table_name)
        if not guards:
            return list(prepared)

        kept: list[dict[str, Any]] = []
        for row in prepared:
            missing: str | None = None
            for column, parent in guards:
                value = row.get(column)
                if value is None:
                    continue
                known = self._known_keys.get(parent)
                if known is not None and value not in known:
                    missing = f"{column}={value!r} -> {parent}"
                    break
            if missing is None:
                kept.append(row)
            else:
                self._bump_skip(f"{table_name}_dangling_reference")
                self._report.conversion_warnings.append(
                    f"{table_name}#{row.get('id')}: dropped, {missing} does not exist"
                )
        return kept

    async def _insert_prepared(
        self,
        table_name: str,
        model: type[Base],
        prepared: Sequence[dict[str, Any]],
        conflict_index: list[str] | None = None,
    ) -> None:
        prepared = self._drop_dangling(table_name, prepared)
        self._register_keys(table_name, prepared)
        self._report.migrated[table_name] = len(prepared)
        if not prepared or self._options.dry_run:
            return

        for chunk in chunk_rows(prepared):
            # Idempotent by primary key: a second run inserts nothing new, and
            # a run interrupted partway through resumes without duplicating the
            # chunks that already landed.
            statement = pg_insert(model).values(list(chunk))
            statement = statement.on_conflict_do_nothing(index_elements=conflict_index or ["id"])
            await self._session.execute(statement)
        # Still one commit per table: a later failure keeps what already landed.
        await self._session.commit()

    async def _reset_sequences(self) -> None:
        """Move each sequence past the ids that came from the source.

        No table name is ever interpolated into SQL: the maximum comes from the
        model, and the table name reaches setval as a bound parameter.
        """
        for table_name, model in SEQUENCED_MODELS:
            highest = await self._scalar(select(func.max(model.id)))
            await self._session.execute(
                text("SELECT setval(pg_get_serial_sequence(:table_name, 'id'), :value)").bindparams(
                    table_name=table_name, value=int(highest or 1)
                )
            )
        await self._session.commit()

    async def _scalar(self, statement: Any) -> Any:
        result = await self._session.execute(statement)
        return result.scalar()

    def _bump_skip(self, reason: str) -> None:
        self._report.skipped[reason] = self._report.skipped.get(reason, 0) + 1

    # ------------------------------------------------------------- verification

    async def _verify(self, connection: sqlite3.Connection) -> None:
        """Reconcile against the source, then against the documented profile."""
        report = self._report
        source = report.source_counts

        # Layer 1: what came out must match what went in. Always applicable.
        #
        # Two separate checks per table, because they answer different
        # questions. "count" asks whether every row we decided to write is
        # actually in the database. "reconcile" asks whether every source row
        # was accounted for — written or deliberately skipped — so a silently
        # dropped row cannot hide behind a matching count.
        for table_name, model in (
            ("catalog_items", CatalogItem),
            ("collection_items", CollectionItem),
            ("market_price_snapshots", MarketPriceSnapshot),
            ("expenses", Expense),
            ("exchange_rates", ExchangeRate),
            ("price_source_links", PriceSourceLink),
            ("media_files", MediaFile),
        ):
            written = report.migrated.get(table_name, 0)
            actual = (
                written
                if self._options.dry_run
                else int(await self._scalar(select(func.count()).select_from(model)) or 0)
            )
            report.add_check(f"count:{table_name}", written, actual)

            skipped = sum(
                count
                for reason, count in report.skipped.items()
                if reason.startswith(f"{table_name}_")
            )
            report.add_check(
                f"reconcile:{table_name}", source.get(table_name, 0), written + skipped
            )

        expected_sum = _sqlite_expense_sum(connection)
        actual_sum = (
            expected_sum
            if self._options.dry_run
            else (await self._scalar(select(func.sum(Expense.amount))) or Decimal(0))
        )
        report.add_check("sum:expenses.amount", str(expected_sum), str(Decimal(actual_sum)))

        if not self._options.dry_run:
            orphan_owner = int(
                await self._scalar(
                    select(func.count())
                    .select_from(CollectionItem)
                    .where(CollectionItem.owner_id.is_(None))
                )
                or 0
            )
            report.add_check("collection_items without owner", 0, orphan_owner)

            personal_catalog = int(
                await self._scalar(
                    select(func.count())
                    .select_from(CatalogItem)
                    .where(CatalogItem.created_by.is_not(None))
                )
                or 0
            )
            report.add_check("catalog_items with created_by", 0, personal_catalog)

        # Layer 2: the documented profile, only when one was supplied.
        expectations = self._options.expectations
        if expectations:
            for name, expected in (expectations.get("counts") or {}).items():
                report.add_check(f"expected:{name}", expected, source.get(name))
            expected_total = expectations.get("expenseSum")
            if expected_total is not None:
                report.add_check(
                    "expected:sum:expenses.amount", str(expected_total), str(expected_sum)
                )


def chunk_size_for(columns: int) -> int:
    """Rows per statement that keep the bind parameters under the limit."""
    return max(1, MAX_BIND_PARAMETERS // max(columns, 1))


def chunk_rows(rows: Sequence[dict[str, Any]]) -> Iterator[Sequence[dict[str, Any]]]:
    """Split rows into statement-sized batches, order preserved.

    The size comes from the width of the rows themselves, so a table gaining a
    column cannot quietly push a statement over the limit again.
    """
    if not rows:
        return
    size = chunk_size_for(len(rows[0]))
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def _sqlite_expense_sum(connection: sqlite3.Connection) -> Decimal:
    """Sum the source amounts the same way the target rounds them."""
    total = Decimal(0)
    for row in reader.read_table(connection, "expenses"):
        total += convert.to_money(row["amount"]) or Decimal(0)
    return total


def _unwrap_json(raw: Any) -> Any:
    payload, _ = convert.to_jsonb(raw)
    if isinstance(payload, dict) and set(payload) == {"value"}:
        return payload["value"]
    return payload


__all__ = [
    "MigrationError",
    "MigrationOptions",
    "MigrationRunner",
    "chunk_rows",
    "chunk_size_for",
]
