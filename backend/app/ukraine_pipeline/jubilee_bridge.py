"""jubilee-bridge — a targeted NBU match for six mispatriated jubilee coins.

Six shared Ukrainian records (jubilee 1-hryvnia coins, moved by hand from
`circulation` to `commemorative` outside `circ_reclassify.py` — see
docs/05-integrations.md, section 10) carry Russian Excel names and no NBU
numismatic catalogue link at all, so `OurItem.is_nbu_linked` cannot see them
and never will on its own: there is no `price_source_links` row and no
`nbu:<id>` source key to find. app/ukraine_pipeline/bridge.py (part B) cannot
help either — it matches against `Sources`, built from a full triangulated
scrape of all three sources, not a handful of named records — so this module
is a small, separate tool: one targeted search per record against the same
POST endpoint (app/ukraine_recon/nbu.py), not a second general bridge.

**Always to review, never auto-applied.** Unlike bridge.py's confidence
threshold, every candidate here goes to the review CSV regardless of score:
the handoff asked for "id -> nbu-карточка ... для мого рев'ю" explicitly, and
with only six records at stake there is no volume problem a threshold would
be solving — only a wrong silent link to avoid.

**Live reconnaissance, 2026-09-05 — an honest gap, not a placeholder.**
Searching bank.gov.ua's own numismatic-products endpoint for these six
themes ("60 років визволення України", "20 років ... гривні", "футбол")
found no 1-hryvnia card for any of them: matches that exist are 2, 5, 10, 20,
50, 100 or 250 hryvnia collector coins on unrelated or adjacent anniversaries
(the closest liberation-themed hit is "60 років визволення Києва", 5 hryvnia,
2003 — Kyiv specifically, not the whole country, and not 2004). This may mean
these six coins were never issued as souvenir/numismatic products at all (an
inexpensive circulation-quality jubilee coin, closer in spirit to the
kopiika/hryvnia mini-pipeline than to the collector catalogue), or that the
search terms below need broadening once run against the record's own stored
title. Either way this is not guessed at here: `THEMES_BY_YEAR` carries the
handoff's own Ukrainian phrasing as a search seed, and an empty or
low-scoring result for a given year is reported as such — see
`JubileeOutcome.no_candidates` — for a person to widen the search or decide
these six stay unlinked.
"""

from __future__ import annotations

import csv
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceSourceLink
from app.models.enums import MatchStatus
from app.ukraine_pipeline.catalog import LINK_SOURCES, OurItem
from app.ukraine_pipeline.lexicon import Lexicon
from app.ukraine_recon.http import PoliteClient, SourceUnreachableError
from app.ukraine_recon.models import SOURCE_NBU
from app.ukraine_recon.nbu import NbuCard, parse_search_page, search_form, search_url

HRYVNIA_UNIT = "hryvnia"
CATEGORY_COIN = "Coin"
MAX_CANDIDATES = 5
# A floor only against wildly unrelated noise — every candidate above it goes
# to review regardless, per the module's own "always review" rule above.
CANDIDATE_FLOOR = 30.0

# The handoff's own description of each record's theme, translated to the
# Ukrainian search text bank.gov.ua's own `search` field expects. Not the
# record's stored title (a Russian Excel name) — a starting point a reviewer
# widens if a year's search comes back empty (see the module docstring).
THEMES_BY_YEAR: dict[int, str] = {
    2004: "60 років визволення України від фашистських загарбників",
    2005: "60 років Перемоги",
    2010: "65 років Перемоги",
    2012: "Чемпіонат Європи з футболу",
    2015: "70 років Перемоги",
    2016: "20 років запровадження гривні",
}

CSV_COLUMNS = (
    "decision",
    "itemId",
    "ourTitle",
    "ourYear",
    "searchTerm",
    "nbuId",
    "nbuTitle",
    "nbuNominal",
    "thumbnailUrl",
    "score",
)
YES = frozenset({"y", "yes", "1", "true", "+", "так"})


@dataclass
class Candidate:
    card: NbuCard
    score: float


@dataclass
class ReviewRow:
    item: OurItem
    search_term: str
    candidates: list[Candidate] = field(default_factory=list)


@dataclass
class JubileeOutcome:
    # Every record matching the shape (commemorative, 1 hryvnia, an unlinked
    # jubilee-era year) this run considered — not all of them find a
    # candidate, see `review` / `no_candidates` below.
    eligible: dict[int, OurItem] = field(default_factory=dict)
    review: list[ReviewRow] = field(default_factory=list)
    no_candidates: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "eligible": len(self.eligible),
            "reviewRows": sum(len(row.candidates) for row in self.review),
            "noCandidates": len(self.no_candidates),
        }


def eligible_items(items: list[OurItem]) -> list[OurItem]:
    """The six (or however many) records this tool is for, found by shape —
    not by a hardcoded id list, since ids are not stable across databases.
    """
    found: list[OurItem] = []
    for item in items:
        if item.is_archived or item.is_nbu_linked:
            continue
        if item.collection_group != "commemorative":
            continue
        if item.denomination != Decimal(1) or item.denomination_unit != HRYVNIA_UNIT:
            continue
        if item.issue_year in THEMES_BY_YEAR:
            found.append(item)
    return found


def _search(client: PoliteClient, theme: str, *, log: Callable[[str], None]) -> list[NbuCard]:
    form = search_form(1, per_page=25, category=CATEGORY_COIN, search=theme)
    try:
        result = client.post(search_url(), form)
    except SourceUnreachableError as exc:
        log(f"jubilee-bridge: nbu search unreachable for {theme!r}: {exc}")
        return []
    if not result.ok:
        log(f"jubilee-bridge: nbu search {theme!r}: HTTP {result.status}")
        return []
    return parse_search_page(result.text).cards


def score_candidates(
    item: OurItem, theme: str, cards: list[NbuCard], lexicon: Lexicon
) -> list[Candidate]:
    scored: list[Candidate] = []
    for card in cards:
        text = " ".join([card.title, *card.description])
        best = max(
            lexicon.score(theme, card.title),
            lexicon.score(item.title_original, text),
        )
        if best >= CANDIDATE_FLOOR:
            scored.append(Candidate(card=card, score=best))
    scored.sort(key=lambda candidate: -candidate.score)
    return scored[:MAX_CANDIDATES]


def find_candidates(
    client: PoliteClient, *, items: list[OurItem], lexicon: Lexicon, log: Callable[[str], None]
) -> JubileeOutcome:
    outcome = JubileeOutcome()
    for item in eligible_items(items):
        outcome.eligible[item.id] = item
        # eligible_items() only returns years that are keys of THEMES_BY_YEAR.
        theme = THEMES_BY_YEAR[item.issue_year]
        cards = _search(client, theme, log=log)
        candidates = score_candidates(item, theme, cards, lexicon)
        if not candidates:
            outcome.no_candidates.append(
                {"itemId": item.id, "title": item.title_original, "searchTerm": theme}
            )
            continue
        outcome.review.append(ReviewRow(item=item, search_term=theme, candidates=candidates))
    return outcome


def write_review_csv(path: Path, outcome: JubileeOutcome) -> int:
    """One row per candidate; a person writes "yes" against the one card, if any."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in outcome.review:
            for candidate in row.candidates:
                card = candidate.card
                writer.writerow(
                    {
                        "decision": "",
                        "itemId": row.item.id,
                        "ourTitle": row.item.title_original,
                        "ourYear": row.item.issue_year,
                        "searchTerm": row.search_term,
                        "nbuId": card.nbu_id or "",
                        "nbuTitle": card.title,
                        "nbuNominal": card.fields.get("Номінал", ""),
                        "thumbnailUrl": card.thumbnails[0] if card.thumbnails else "",
                        "score": round(candidate.score, 1),
                    }
                )
                rows += 1
    return rows


def read_review_csv(path: Path) -> dict[int, str]:
    """{catalog item id: nbu card id} out of the rows marked yes."""
    chosen: dict[int, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("decision") or "").strip().casefold() not in YES:
                continue
            item_id = int(str(row["itemId"]).strip())
            nbu_id = str(row["nbuId"]).strip()
            if not nbu_id:
                message = f"review file marks item #{item_id} yes with no nbuId"
                raise ValueError(message)
            if item_id in chosen:
                message = f"review file marks two cards for item #{item_id}"
                raise ValueError(message)
            chosen[item_id] = nbu_id
    return chosen


async def write_links(session: AsyncSession, decisions: dict[int, str]) -> int:
    """Upsert price_source_links only — source_key is left alone.

    Matches app/ukraine_pipeline/bridge.py's own convention for linking an
    *existing* record to a cluster: source_key is reserved for records a step
    created itself (circ_gaps.py's "wiki-circ:...", gaps.py's "nbu:<id>"),
    and OurItem.is_nbu_linked already treats a price_source_links row alone
    as sufficient proof of the link (app/ukraine_pipeline/catalog.py).
    """
    if not decisions:
        return 0
    now = datetime.now(UTC)
    rows = [
        {
            "catalog_item_id": item_id,
            "source": LINK_SOURCES[SOURCE_NBU],
            "external_id": nbu_id,
            "match_status": MatchStatus.CONFIRMED,
            "matched_at": now,
        }
        for item_id, nbu_id in decisions.items()
    ]
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
