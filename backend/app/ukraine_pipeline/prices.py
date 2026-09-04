"""prices — one snapshot per linked coin, from ua-coins.info.

A single pass, not the daily job: the job belongs to stage 5, and what this
step does is give the Ukrainian part of the catalogue a price at all. Snapshots
are written with created_by NULL, so they are the shared ones everyone sees
(docs/04-business-rules.md, rule 7).

Every price goes through the checks of docs/05-integrations.md before it is
written; the ones that fail are stored flagged rather than dropped, exactly as
the legacy migration did, so a person can look at what the parser produced.
The snapshots already marked suspect are re-checked against the new price.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.legacy_migration import prices as checks
from app.models import CatalogItem, MarketPriceSnapshot
from app.ukraine_pipeline.catalog import LINK_SOURCES
from app.ukraine_recon.models import SOURCE_UA_COINS
from app.ukraine_recon.normalize import parse_date
from app.ukraine_recon.triangulate import Cluster

SNAPSHOT_SOURCE = LINK_SOURCES[SOURCE_UA_COINS]
CURRENCY = "UAH"


@dataclass
class PricesOutcome:
    written: int = 0
    suspect: int = 0
    without_price: int = 0
    already_recorded: int = 0
    recheck_cleared: list[int] = field(default_factory=list)
    recheck_still_suspect: list[int] = field(default_factory=list)
    by_rule: dict[str, int] = field(default_factory=dict)
    examples: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "written": self.written,
            "suspect": self.suspect,
            "withoutPrice": self.without_price,
            "alreadyRecorded": self.already_recorded,
            "recheckedCleared": len(self.recheck_cleared),
            "recheckedStillSuspect": len(self.recheck_still_suspect),
            "byRule": self.by_rule,
        }


async def _issue_years(session: AsyncSession, item_ids: list[int]) -> dict[int, int]:
    rows = await session.execute(
        select(CatalogItem.id, CatalogItem.issue_year).where(CatalogItem.id.in_(item_ids))
    )
    return {int(item_id): int(year) for item_id, year in rows.all()}


def observed_at(cluster: Cluster) -> datetime:
    """The date ua-coins prints over its price column, or today."""
    record = cluster.record_of(SOURCE_UA_COINS)
    day = parse_date(record.price_date) if record is not None else None
    if day is None:
        return datetime.now(UTC)
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


async def record_prices(
    session: AsyncSession,
    *,
    pairs: dict[int, Cluster],
    currencies: list[str],
    dry_run: bool,
) -> PricesOutcome:
    outcome = PricesOutcome()
    if not pairs:
        return outcome

    years = await _issue_years(session, list(pairs))

    candidates: list[checks.SnapshotUnderTest] = []
    payloads: dict[int, dict[str, Any]] = {}
    for item_id, cluster in pairs.items():
        record = cluster.record_of(SOURCE_UA_COINS)
        if record is None or record.price is None:
            outcome.without_price += 1
            continue
        when = observed_at(cluster)
        if await _already_recorded(session, item_id, when):
            outcome.already_recorded += 1
            continue
        candidates.append(
            checks.SnapshotUnderTest(
                snapshot_id=item_id,
                catalog_item_id=item_id,
                price=Decimal(record.price),
                currency_code=CURRENCY,
                issue_year=years.get(item_id),
            )
        )
        payloads[item_id] = {
            "price": Decimal(record.price),
            "observed_at": when,
            "url": record.url,
            "raw": {
                "source": "ua-coins.info",
                "sourceId": record.source_id,
                "priceDate": record.price_date,
                "trend": record.extra.get("trend"),
            },
        }

    verdicts = checks.evaluate_all(candidates, currencies)
    for candidate in candidates:
        verdict = verdicts[candidate.snapshot_id]
        payload = payloads[candidate.snapshot_id]
        for rule in verdict.rules:
            outcome.by_rule[rule] = outcome.by_rule.get(rule, 0) + 1
        outcome.written += 1
        if verdict.is_suspect:
            outcome.suspect += 1
            if len(outcome.examples) < 20:
                outcome.examples.append(
                    {
                        "itemId": candidate.catalog_item_id,
                        "price": str(candidate.price),
                        "rules": verdict.rules,
                    }
                )
        if dry_run:
            continue
        session.add(
            MarketPriceSnapshot(
                catalog_item_id=candidate.catalog_item_id,
                source=SNAPSHOT_SOURCE,
                price=candidate.price,
                currency_code=CURRENCY,
                observed_at=payload["observed_at"],
                source_url=payload["url"],
                raw_payload=payload["raw"],
                created_by=None,
                is_suspect=verdict.is_suspect,
            )
        )

    await _recheck_suspects(session, pairs, currencies, outcome, dry_run=dry_run)
    if not dry_run:
        await session.flush()
    return outcome


async def _already_recorded(session: AsyncSession, item_id: int, when: datetime) -> bool:
    """The unique key is (item, source, grade, observed_at): a second run of
    the same day's price would collide, so it is skipped instead."""
    found = await session.execute(
        select(MarketPriceSnapshot.id).where(
            MarketPriceSnapshot.catalog_item_id == item_id,
            MarketPriceSnapshot.source == SNAPSHOT_SOURCE,
            MarketPriceSnapshot.observed_at == when,
            MarketPriceSnapshot.created_by.is_(None),
        )
    )
    return found.first() is not None


async def _recheck_suspects(
    session: AsyncSession,
    pairs: dict[int, Cluster],
    currencies: list[str],
    outcome: PricesOutcome,
    *,
    dry_run: bool,
) -> None:
    """The snapshots the legacy migration flagged, judged again.

    A snapshot was flagged on the evidence available at migration time. With a
    price from the issuer's own market in hand the deviation rule can say
    something it could not then, so the flag is worth re-deciding rather than
    left standing for ever.
    """
    suspects = (
        (
            await session.execute(
                select(MarketPriceSnapshot).where(
                    MarketPriceSnapshot.is_suspect,
                    MarketPriceSnapshot.catalog_item_id.in_(pairs),
                )
            )
        )
        .scalars()
        .all()
    )
    if not suspects:
        return
    years = await _issue_years(session, [snapshot.catalog_item_id for snapshot in suspects])
    under_test = [
        checks.SnapshotUnderTest(
            snapshot_id=snapshot.id,
            catalog_item_id=snapshot.catalog_item_id,
            price=snapshot.price,
            currency_code=snapshot.currency_code,
            issue_year=years.get(snapshot.catalog_item_id),
        )
        for snapshot in suspects
    ]
    verdicts = checks.evaluate_all(under_test, currencies)
    for snapshot in suspects:
        verdict = verdicts[snapshot.id]
        if verdict.is_suspect:
            outcome.recheck_still_suspect.append(snapshot.id)
            continue
        outcome.recheck_cleared.append(snapshot.id)
        if not dry_run:
            snapshot.is_suspect = False
