"""jubilee-bridge: the targeted NBU search for the six mispatriated records.

No database — this is the decision layer, exercised against a trimmed slice
of a live NBU search response (see the fixture's own header comment for the
URL and retrieval date). What is checked: the six-record shape is found by
its own attributes (not a hardcoded id list), scoring picks the closest
titles without inventing a match, the review CSV round-trips a person's
"yes", and applying writes price_source_links only — never source_key.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PriceSourceLink
from app.models.enums import CollectionGroup, TranslationSource
from app.ukraine_pipeline import jubilee_bridge
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.lexicon import load_lexicon
from app.ukraine_recon.models import SOURCE_NBU
from app.ukraine_recon.nbu import parse_search_page
from tests.seed import country_by_code, make_catalog_item, seed_currencies

LEXICON = load_lexicon()
FIXTURE = Path(__file__).parent / "fixtures" / "ukraine_recon" / "nbu_jubilee_search_sample.html"


def item(
    item_id: int,
    title: str,
    year: int,
    *,
    group: str = "commemorative",
    denomination: Decimal | None = Decimal(1),
    unit: str | None = "hryvnia",
    archived: bool = False,
    links: dict[str, str] | None = None,
) -> OurItem:
    return OurItem(
        id=item_id,
        title_original=title,
        title_uk=None,
        title_en=None,
        issue_year=year,
        denomination=denomination,
        denomination_id=1,
        collection_group=group,
        series_id=None,
        series_name=None,
        is_archived=archived,
        denomination_unit=unit,
        links=links or {},
    )


def test_eligible_items_finds_the_shape_not_a_hardcoded_id() -> None:
    jubilee = item(1330, "60-річчя визволення України", 2004)
    ordinary_circulation = item(500, "1 гривня", 2004, group="circulation")
    wrong_denomination = item(1331, "60-річчя визволення України", 2004, denomination=Decimal(2))
    already_linked = item(1332, "60-річчя визволення України", 2004, links={SOURCE_NBU: "999"})
    outside_years = item(1333, "щось інше", 2007)
    archived = item(1334, "60-річчя визволення України", 2004, archived=True)

    found = jubilee_bridge.eligible_items(
        [jubilee, ordinary_circulation, wrong_denomination, already_linked, outside_years, archived]
    )

    assert found == [jubilee]


def test_score_candidates_prefers_the_closer_title() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    cards = parse_search_page(html).cards
    assert len(cards) == 2  # the trimmed fixture keeps two of the live response's 13 cards

    football = item(1333, "Чемпіонат Європи з футболу", 2012)
    candidates = jubilee_bridge.score_candidates(
        football, jubilee_bridge.THEMES_BY_YEAR[2012], cards, LEXICON
    )

    assert candidates  # the fixture's own two cards are both football-themed
    assert candidates[0].card.title.startswith("Фінальний турнір")
    assert candidates == sorted(candidates, key=lambda c: -c.score)


def test_score_candidates_scores_an_unrelated_theme_lower_than_a_real_match() -> None:
    """bank.gov.ua's own `search` is a loose keyword match, not a phrase
    match (module docstring) — a search for an unrelated theme can still
    return the fixture's football cards and score above CANDIDATE_FLOOR by
    incidental word overlap ("років"). This tool does not pretend that noise
    is a real match by hiding it; it relies on always-review (never
    auto-apply) plus a visibly lower score to let a person tell the two
    apart, which this test checks instead of asserting an empty result.
    """
    html = FIXTURE.read_text(encoding="utf-8")
    cards = parse_search_page(html).cards
    football = item(1333, "Чемпіонат Європи з футболу", 2012)
    unrelated = item(1335, "20 років запровадження гривні", 2016)

    real_match = jubilee_bridge.score_candidates(
        football, jubilee_bridge.THEMES_BY_YEAR[2012], cards, LEXICON
    )
    noise = jubilee_bridge.score_candidates(
        unrelated, jubilee_bridge.THEMES_BY_YEAR[2016], cards, LEXICON
    )

    assert real_match
    if noise:
        assert real_match[0].score > noise[0].score


def test_review_csv_round_trips_a_persons_yes(tmp_path: Path) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    cards = parse_search_page(html).cards
    row = jubilee_bridge.ReviewRow(
        item=item(1333, "Чемпіонат Європи з футболу", 2012),
        search_term=jubilee_bridge.THEMES_BY_YEAR[2012],
        candidates=jubilee_bridge.score_candidates(
            item(1333, "Чемпіонат Європи з футболу", 2012),
            jubilee_bridge.THEMES_BY_YEAR[2012],
            cards,
            LEXICON,
        ),
    )
    outcome = jubilee_bridge.JubileeOutcome(eligible={1333: row.item}, review=[row])
    path = tmp_path / "jubilee-review.csv"

    written = jubilee_bridge.write_review_csv(path, outcome)
    assert written == len(row.candidates)

    chosen_nbu_id = row.candidates[0].card.nbu_id
    assert chosen_nbu_id is not None
    # Mark the first data row's decision column "yes" through csv itself,
    # not string surgery, so this does not depend on column order.
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["decision"] = "yes"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=jubilee_bridge.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    decisions = jubilee_bridge.read_review_csv(path)
    assert decisions == {1333: chosen_nbu_id}


def test_read_review_csv_rejects_a_yes_with_no_nbu_id(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "decision,itemId,ourTitle,ourYear,searchTerm,nbuId,nbuTitle,nbuNominal,thumbnailUrl,score\n"
        "yes,1330,x,2004,x,,,,, \n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no nbuId"):
        jubilee_bridge.read_review_csv(path)


async def test_write_links_touches_price_source_links_only(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    record = await make_catalog_item(
        db_session,
        country=country,
        title="60-річчя визволення України",
        year=2004,
        group=CollectionGroup.COMMEMORATIVE,
        source_key="ucoin:legacy-excel-key",
        title_uk_source=TranslationSource.MANUAL,
    )

    written = await jubilee_bridge.write_links(db_session, {record.id: "8080"})
    await db_session.commit()

    assert written == 1
    link = (
        await db_session.execute(
            select(PriceSourceLink).where(PriceSourceLink.catalog_item_id == record.id)
        )
    ).scalar_one()
    assert link.source == "NBU"
    assert link.external_id == "8080"

    refreshed = await db_session.get(type(record), record.id)
    assert refreshed is not None
    assert refreshed.source_key == "ucoin:legacy-excel-key"  # untouched, on purpose
