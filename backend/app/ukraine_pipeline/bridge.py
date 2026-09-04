"""bridge — deciding which of our records is which coin.

The cluster built from the three sources is the unit of truth; this step says
which of our catalogue records it is. Two ways in:

A. a ua-coins.info reference we already hold — 594 of them came with the
   legacy database, and a reference is not a guess;
B. a score over the candidates of the same year and face value, comparing our
   Russian title with the Ukrainian one through the lexicon.

Above the confidence threshold the link is written; below it the pair goes to
a CSV for a person to decide, and `--apply-review` reads that decision back.
Nothing in between is invented: an item with no candidate is reported as
having none.

The links are written to price_source_links, one row per source, under the
names that table already uses.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceSourceLink
from app.models.enums import MatchStatus
from app.ukraine_pipeline.catalog import LINK_SOURCES, OurItem
from app.ukraine_pipeline.lexicon import Lexicon
from app.ukraine_pipeline.sources import Sources, cluster_key, coin_clusters
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA
from app.ukraine_recon.triangulate import Cluster

# A score at or above this is a link; below REVIEW_THRESHOLD the candidate is
# not even worth showing a person. Calibrated on the reconnaissance sample.
AUTO_THRESHOLD = 88.0
REVIEW_THRESHOLD = 55.0
# The year on the coin and the date it entered circulation can differ.
YEAR_TOLERANCE = 1
MAX_CANDIDATES = 5

_UA_COINS_ID_RE = re.compile(r"ua-coins\.info/(?:[a-z]{2}/)?list/(\d+)")

CSV_COLUMNS = (
    "decision",
    "itemId",
    "ourTitle",
    "ourYear",
    "ourDenomination",
    "clusterKey",
    "clusterTitle",
    "clusterYear",
    "clusterDenomination",
    "score",
    "sources",
    # Filled when another of our records was linked to this coin first: two
    # records for one coin is a duplicate, and only a person can say which.
    "claimedBy",
)
YES = frozenset({"y", "yes", "1", "true", "+", "так"})


@dataclass
class Candidate:
    cluster: Cluster
    score: float

    @property
    def key(self) -> str:
        return cluster_key(self.cluster)


@dataclass
class Decision:
    item: OurItem
    cluster: Cluster | None
    strategy: str
    score: float
    candidates: list[Candidate] = field(default_factory=list)


@dataclass
class BridgeOutcome:
    linked: list[Decision] = field(default_factory=list)
    review: list[Decision] = field(default_factory=list)
    without_candidates: list[OurItem] = field(default_factory=list)
    skipped_archived: int = 0
    # cluster key -> the record already linked to it.
    claimed: dict[str, int] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        by_strategy: dict[str, int] = {}
        for decision in self.linked:
            by_strategy[decision.strategy] = by_strategy.get(decision.strategy, 0) + 1
        return {
            "linked": len(self.linked),
            "byStrategy": by_strategy,
            "toReview": len(self.review),
            "withoutCandidates": len(self.without_candidates),
            "skippedArchived": self.skipped_archived,
        }


# ------------------------------------------------------------------ matching
def ua_coins_id(reference: str) -> str | None:
    match = _UA_COINS_ID_RE.search(reference)
    return match.group(1) if match else None


def _by_ua_coins_link(item: OurItem, sources: Sources) -> Cluster | None:
    reference = item.links.get(SOURCE_UA_COINS)
    if not reference:
        return None
    coin_id = ua_coins_id(reference)
    return None if coin_id is None else sources.cluster_of(SOURCE_UA_COINS, coin_id)


def _same_slot(item: OurItem, cluster: Cluster) -> bool:
    if cluster.year is None or abs(cluster.year - item.issue_year) > YEAR_TOLERANCE:
        return False
    if item.denomination is None or cluster.denomination is None:
        # An unknown face value on either side is not evidence against a match.
        return True
    return Decimal(cluster.denomination) == item.denomination


def score_candidates(
    item: OurItem, clusters: Sequence[Cluster], lexicon: Lexicon
) -> list[Candidate]:
    """Every plausible cluster for one record, best first."""
    scored: list[Candidate] = []
    for cluster in clusters:
        if not _same_slot(item, cluster):
            continue
        best = max(
            (
                lexicon.score(ours, cluster.title)
                for ours in (item.title_original, item.title_uk, item.title_en)
                if ours
            ),
            default=0.0,
        )
        if best >= REVIEW_THRESHOLD:
            scored.append(Candidate(cluster=cluster, score=best))
    scored.sort(key=lambda candidate: -candidate.score)
    return scored[:MAX_CANDIDATES]


def decide(items: Iterable[OurItem], sources: Sources, lexicon: Lexicon) -> BridgeOutcome:
    """Link what is certain, hand the rest to a person.

    A coin belongs to one of our records. When a second record scores well on
    a coin already linked, that is a duplicate in our catalogue, not a better
    match — so it goes to review with the record that took it named, rather
    than being reported as having no candidate at all.

    Existing ua-coins references are applied first, all of them, before
    anything is scored: a reference we already hold outranks a resemblance.
    """
    outcome = BridgeOutcome()
    clusters = coin_clusters(sources)
    claimed: dict[str, int] = {}
    to_score: list[OurItem] = []

    for item in items:
        if item.is_archived:
            outcome.skipped_archived += 1
            continue
        if not item.is_commemorative:
            # Circulation coins are not in the NBU numismatic catalogue.
            continue
        by_link = _by_ua_coins_link(item, sources)
        if by_link is None:
            to_score.append(item)
            continue
        outcome.linked.append(Decision(item, by_link, "link", 100.0))
        claimed.setdefault(cluster_key(by_link), item.id)

    for item in to_score:
        candidates = score_candidates(item, clusters, lexicon)
        if not candidates:
            outcome.without_candidates.append(item)
            continue
        best = candidates[0]
        runner_up = candidates[1].score if len(candidates) > 1 else 0.0
        # A clear winner, on a coin nobody has taken. Anything else — a tie, a
        # weak best, a coin already linked — is what a person has to look at.
        decided = (
            best.score >= AUTO_THRESHOLD and best.score > runner_up and best.key not in claimed
        )
        if decided:
            outcome.linked.append(Decision(item, best.cluster, "score", best.score))
            claimed[best.key] = item.id
        else:
            outcome.review.append(Decision(item, None, "review", best.score, candidates=candidates))
    outcome.claimed = claimed
    return outcome


# --------------------------------------------------------------------- review
def write_review_csv(path: Path, outcome: BridgeOutcome) -> int:
    """One row per candidate; a person writes "yes" in the first column."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for decision in outcome.review:
            for candidate in decision.candidates:
                writer.writerow(
                    {
                        "decision": "",
                        "itemId": decision.item.id,
                        "ourTitle": decision.item.title_original,
                        "ourYear": decision.item.issue_year,
                        "ourDenomination": decision.item.denomination or "",
                        "clusterKey": candidate.key,
                        "clusterTitle": candidate.cluster.title,
                        "clusterYear": candidate.cluster.year or "",
                        "clusterDenomination": candidate.cluster.denomination or "",
                        "score": round(candidate.score, 1),
                        "sources": " ".join(sorted(candidate.cluster.sources)),
                        "claimedBy": outcome.claimed.get(candidate.key, ""),
                    }
                )
                rows += 1
    return rows


def read_review_csv(path: Path) -> dict[int, str]:
    """{catalog item id: cluster key} out of the rows marked yes."""
    chosen: dict[int, str] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() not in YES:
                continue
            item_id = int(str(row["itemId"]).strip())
            if item_id in chosen:
                message = f"review file marks two clusters for item #{item_id}"
                raise ValueError(message)
            chosen[item_id] = str(row["clusterKey"]).strip()
    return chosen


def apply_review(
    outcome: BridgeOutcome, decisions: dict[int, str], sources: Sources
) -> tuple[BridgeOutcome, list[str]]:
    """Move the reviewed pairs from `review` to `linked`."""
    by_key = sources.cluster_by_key()
    problems: list[str] = []
    still_open: list[Decision] = []
    for decision in outcome.review:
        key = decisions.get(decision.item.id)
        if key is None:
            still_open.append(decision)
            continue
        cluster = by_key.get(key)
        if cluster is None:
            problems.append(f"item #{decision.item.id}: unknown cluster {key!r}")
            still_open.append(decision)
            continue
        outcome.linked.append(Decision(decision.item, cluster, "review", decision.score))
    outcome.review = still_open
    return outcome, problems


# --------------------------------------------------------------------- writing
def links_of(cluster: Cluster) -> dict[str, str]:
    """What goes into price_source_links for a cluster, per source.

    ua-coins and Wikipedia have a page per coin, so the link is a URL. The NBU
    has none — its catalogue is one listing — so the card id is the reference.
    """
    links: dict[str, str] = {}
    for source in (SOURCE_UA_COINS, SOURCE_WIKIPEDIA):
        record = cluster.record_of(source)
        if record is not None and record.url:
            links[source] = record.url
    nbu_record = cluster.record_of(SOURCE_NBU)
    if nbu_record is not None:
        links[SOURCE_NBU] = nbu_record.source_id
    return links


async def write_links(session: AsyncSession, outcome: BridgeOutcome) -> int:
    """Upsert one row per (item, source). Re-running changes nothing."""
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for decision in outcome.linked:
        if decision.cluster is None:
            continue
        for source, external_id in links_of(decision.cluster).items():
            rows.append(
                {
                    "catalog_item_id": decision.item.id,
                    "source": LINK_SOURCES[source],
                    "external_id": external_id,
                    "match_status": MatchStatus.CONFIRMED,
                    "matched_at": now,
                }
            )
    if not rows:
        return 0
    statement = pg_insert(PriceSourceLink).values(rows)
    statement = statement.on_conflict_do_update(
        constraint="uq_price_source_links_catalog_item_id_source",
        set_={
            "external_id": statement.excluded.external_id,
            "match_status": statement.excluded.match_status,
            "matched_at": statement.excluded.matched_at,
        },
    )
    await session.execute(statement)
    return len(rows)


async def linked_pairs(session: AsyncSession, item_ids: Sequence[int]) -> dict[int, dict[str, str]]:
    """{item id: {source: external id}} as the database holds it now."""
    if not item_ids:
        return {}
    reverse = {name: source for source, name in LINK_SOURCES.items()}
    rows = await session.execute(
        select(
            PriceSourceLink.catalog_item_id, PriceSourceLink.source, PriceSourceLink.external_id
        ).where(PriceSourceLink.catalog_item_id.in_(item_ids))
    )
    result: dict[int, dict[str, str]] = {}
    for item_id, source, external_id in rows.all():
        canonical = reverse.get(source)
        if canonical is not None:
            result.setdefault(item_id, {})[canonical] = external_id
    return result
