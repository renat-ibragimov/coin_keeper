"""series — our series renamed to the National Bank's own names.

The NBU is the issuer: its wording is the series name, and the English site
gives the English one. app/ukraine_recon/series_map.json is the map from our
names (in either language) to the NBU ones; anything it does not cover is
reported rather than guessed at, and the fix is a line in that JSON.

Two of our "series" are not series at all and are handled by name:
"Государство Украина (1992 - 2026)" is a bucket ua-coins keeps for circulation
coinage, and "сил" is a fragment of a title the importer stored as a series.
Neither is deleted while anything still points at it — a series is detached
from its coins first, and only an empty row goes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, CoinSeries
from app.models.enums import TranslationSource
from app.ukraine_recon.models import SourceRecord
from app.ukraine_recon.normalize import normalize_title
from app.ukraine_recon.triangulate import load_series_map

# Not series: rows the importers left behind. Matched on the normalised name.
NOT_A_SERIES = ("Государство Украина (1992 - 2026)", "Держава Україна", "сил")


@dataclass
class SeriesOutcome:
    renamed: list[dict[str, Any]] = field(default_factory=list)
    merged: list[dict[str, Any]] = field(default_factory=list)
    detached: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unmapped: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "renamed": len(self.renamed),
            "merged": len(self.merged),
            "detached": len(self.detached),
            "deleted": len(self.deleted),
            "unmapped": len(self.unmapped),
            "unmappedNames": [row["name"] for row in self.unmapped],
        }


def english_series_names(
    nbu_records: list[SourceRecord], english: dict[str, Any]
) -> dict[str, str]:
    """{Ukrainian series name: English series name}, joined on the card id.

    The two locales of the NBU site number their cards the same way, so a card
    carries both names without anything being translated.
    """
    names: dict[str, str] = {}
    for record in nbu_records:
        card = english.get(record.source_id)
        if record.series and card is not None and card.series:
            names.setdefault(record.series, card.series)
    return names


async def rename_series(
    session: AsyncSession,
    *,
    country_id: int,
    nbu_records: list[SourceRecord],
    nbu_english: dict[str, Any],
    dry_run: bool,
) -> SeriesOutcome:
    outcome = SeriesOutcome()
    canon = {
        normalize_title(alias): entry["nbu"]
        for entry in load_series_map()
        if entry.get("nbu")
        for alias in entry.get("ours", [])
    }
    english = english_series_names(nbu_records, nbu_english)
    not_a_series = {normalize_title(name) for name in NOT_A_SERIES}

    rows = (
        (await session.execute(select(CoinSeries).where(CoinSeries.country_id == country_id)))
        .scalars()
        .all()
    )
    by_name = {series.name_original: series for series in rows}

    for series in rows:
        key = normalize_title(series.name_original)
        if key in not_a_series:
            await _detach(session, series, outcome, dry_run=dry_run)
            continue
        target = canon.get(key)
        if target is None:
            outcome.unmapped.append({"id": series.id, "name": series.name_original})
            continue
        holder = by_name.get(target)
        if holder is not None and holder.id != series.id:
            # Two of our series are the same NBU one under two names. The
            # coins move to the row that already carries the right name.
            await _merge(session, series, holder, outcome, dry_run=dry_run)
            continue
        name_en = english.get(target)
        unchanged = (
            series.name_original == target
            and series.name_uk == target
            and series.name_en == name_en
        )
        if unchanged:
            continue
        outcome.renamed.append(
            {
                "id": series.id,
                "from": series.name_original,
                "to": target,
                "nameEn": name_en,
            }
        )
        if dry_run:
            continue
        series.name_original = target
        series.name_uk = target
        series.original_lang = "uk"
        series.name_uk_source = TranslationSource.OFFICIAL
        if name_en:
            series.name_en = name_en
            series.name_en_source = TranslationSource.OFFICIAL
        by_name[target] = series
    if not dry_run:
        await session.flush()
    return outcome


async def _merge(
    session: AsyncSession,
    series: CoinSeries,
    holder: CoinSeries,
    outcome: SeriesOutcome,
    *,
    dry_run: bool,
) -> None:
    used = (
        await session.execute(
            select(func.count(CatalogItem.id)).where(CatalogItem.series_id == series.id)
        )
    ).scalar_one()
    outcome.merged.append(
        {
            "from": series.name_original,
            "into": holder.name_original,
            "items": int(used),
        }
    )
    if dry_run:
        return
    if used:
        await session.execute(
            update(CatalogItem)
            .where(CatalogItem.series_id == series.id)
            .values(series_id=holder.id)
        )
    await session.execute(delete(CoinSeries).where(CoinSeries.id == series.id))
    await session.flush()


async def _detach(
    session: AsyncSession, series: CoinSeries, outcome: SeriesOutcome, *, dry_run: bool
) -> None:
    """Take a non-series off its coins, then drop the empty row."""
    used = (
        await session.execute(
            select(func.count(CatalogItem.id)).where(CatalogItem.series_id == series.id)
        )
    ).scalar_one()
    outcome.detached.append({"id": series.id, "name": series.name_original, "items": int(used)})
    if dry_run:
        return
    if used:
        await session.execute(
            update(CatalogItem).where(CatalogItem.series_id == series.id).values(series_id=None)
        )
    await session.execute(delete(CoinSeries).where(CoinSeries.id == series.id))
    outcome.deleted.append(series.name_original)
    await session.flush()


async def series_by_name(session: AsyncSession, country_id: int) -> dict[str, CoinSeries]:
    """Existing series of the country, keyed by the normalised name."""
    rows = (
        (await session.execute(select(CoinSeries).where(CoinSeries.country_id == country_id)))
        .scalars()
        .all()
    )
    found: dict[str, CoinSeries] = {}
    for series in rows:
        for name in (series.name_original, series.name_uk, series.name_en):
            if name:
                found.setdefault(normalize_title(name), series)
    return found


async def ensure_series(
    session: AsyncSession,
    *,
    country_id: int,
    name_uk: str,
    name_en: str | None,
    cache: dict[str, CoinSeries],
) -> CoinSeries:
    """The NBU series, created if the catalogue does not have it yet."""
    key = normalize_title(name_uk)
    existing = cache.get(key)
    if existing is not None:
        return existing
    series = CoinSeries(
        country_id=country_id,
        name_original=name_uk,
        original_lang="uk",
        name_uk=name_uk,
        name_uk_source=TranslationSource.OFFICIAL,
        name_en=name_en,
        name_en_source=TranslationSource.OFFICIAL if name_en else None,
    )
    session.add(series)
    await session.flush()
    cache[key] = series
    return series
