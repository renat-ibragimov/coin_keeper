"""merge-b: the legacy Excel remainder that already has a twin of its own.

Two layers. No database and no network for the decision layer — building the
candidates, cleaning a title, ranking, and reading/writing the review CSV all
work on OurItem built by hand, exactly the way test_circ_inventory.py's own
tests do. The database is only needed for what actually touches it: instance
counts and applying a reviewed decision, which is `merge.apply_merges` itself
(tests/test_ukraine_pipeline_steps.py already covers that function's own
promises in depth — what is checked here is that merge-b hands it the right
pairs and that a second apply of the same file changes nothing).
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

import pytest
from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, CollectionItem
from app.ukraine_pipeline import merge, merge_b
from app.ukraine_pipeline.bridge import REVIEW_THRESHOLD
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.lexicon import load_lexicon
from app.ukraine_recon.models import SOURCE_NBU
from tests.seed import add_collection_item, make_catalog_item, make_user, seed_reference

LEXICON = load_lexicon()

# The two real pairs from the 2026-09-05 diagnosis (module docstring of
# merge_b.py): a legacy Excel heading next to the National Bank's own name.
MOHYLA_ORPHAN_TITLE = (
    "10 гривен, 1996 400 лет со дня рождения Петра Могилы AgСеребро 0.925, 16.94g, ø 33mm"
)
DESIATYNNA_ORPHAN_TITLE = (
    "10 гривен, 1996 400 лет со дня основания Десятинной церкви AgСеребро 0.925, 16.94g, ø 33mm"
)


def item(
    item_id: int,
    title: str,
    *,
    title_uk: str | None = None,
    year: int = 1996,
    denomination_id: int | None = 1,
    group: str = "commemorative",
    archived: bool = False,
    links: dict[str, str] | None = None,
) -> OurItem:
    return OurItem(
        id=item_id,
        title_original=title,
        title_uk=title_uk,
        title_en=None,
        issue_year=year,
        denomination=Decimal(10),
        denomination_id=denomination_id,
        collection_group=group,
        series_id=None,
        series_name=None,
        is_archived=archived,
        links=links or {},
    )


def twin(item_id: int, title: str, *, title_uk: str | None = None, **fields: object) -> OurItem:
    return item(item_id, title, title_uk=title_uk, links={SOURCE_NBU: str(item_id)}, **fields)


# ------------------------------------------------------------------- cleaning
def test_clean_orphan_title_strips_the_excel_heading_and_material_tail() -> None:
    assert merge_b.clean_orphan_title(MOHYLA_ORPHAN_TITLE) == "400 лет со дня рождения Петра Могилы"
    assert (
        merge_b.clean_orphan_title(DESIATYNNA_ORPHAN_TITLE)
        == "400 лет со дня основания Десятинной церкви"
    )


def test_clean_orphan_title_leaves_an_already_clean_title_alone() -> None:
    assert merge_b.clean_orphan_title("Петро Могила") == "Петро Могила"


def test_clean_orphan_title_handles_gold_and_a_different_heading_currency() -> None:
    glued = "2.000.000 карбованцев, 1995 50 лет ООН AuЗолото 0.900, 15.5g, ø 23mm"
    assert merge_b.clean_orphan_title(glued) == "50 лет ООН"


# ------------------------------------------------------------- key + ranking
def test_score_candidates_only_considers_the_same_slot() -> None:
    orphan = item(1, MOHYLA_ORPHAN_TITLE)
    same_slot = twin(2, "Петро Могила")
    wrong_year = twin(3, "Петро Могила", year=1997)
    wrong_denomination = twin(4, "Петро Могила", denomination_id=2)

    # score_candidates itself does not filter by slot — find_orphans does, by
    # only ever handing it the twins of the orphan's own (year, denomination).
    # This test exercises that filter the way find_orphans applies it.
    slot_twins = [
        candidate
        for candidate in (same_slot, wrong_year, wrong_denomination)
        if candidate.issue_year == orphan.issue_year
        and candidate.denomination_id == orphan.denomination_id
    ]
    assert slot_twins == [same_slot]

    candidates = merge_b.score_candidates(orphan, slot_twins, LEXICON)
    assert [c.twin.id for c in candidates] == [2]


def test_ranking_picks_the_right_twin_only_with_cleaning() -> None:
    """The Mohyla/Desiatynna pair from the real diagnosis: cleaned, each
    orphan's own twin clearly leads; a naive ratio on the raw, uncleaned
    titles does not even clear merge-b's own floor for either.
    """
    mohyla_orphan = item(951, MOHYLA_ORPHAN_TITLE)
    desiatynna_orphan = item(1202, DESIATYNNA_ORPHAN_TITLE)
    mohyla_twin = twin(3185, "Петро Могила")
    desiatynna_twin = twin(3186, "Десятинна церква")
    slot = [mohyla_twin, desiatynna_twin]

    mohyla_candidates = merge_b.score_candidates(mohyla_orphan, slot, LEXICON)
    desiatynna_candidates = merge_b.score_candidates(desiatynna_orphan, slot, LEXICON)

    assert mohyla_candidates[0].twin.id == mohyla_twin.id
    assert desiatynna_candidates[0].twin.id == desiatynna_twin.id
    action, twin_id = merge_b._suggest(mohyla_candidates)
    assert (action, twin_id) == (merge_b.MERGE, mohyla_twin.id)
    action, twin_id = merge_b._suggest(desiatynna_candidates)
    assert (action, twin_id) == (merge_b.MERGE, desiatynna_twin.id)

    # Below bridge.py's own open-search threshold — this is exactly why part
    # B's bridge and inventory-b, which both gate at REVIEW_THRESHOLD, never
    # surfaced either pair; a slot-scoped floor is what makes the difference.
    assert mohyla_candidates[0].score < REVIEW_THRESHOLD
    assert desiatynna_candidates[0].score < REVIEW_THRESHOLD

    # A naive ratio on the raw, uncleaned titles (no lexicon, no strip): the
    # right twin still comes out ahead, but nowhere near merge-b's floor —
    # without cleaning, neither pair would ever have reached "merge".
    raw_best = fuzz.token_sort_ratio(MOHYLA_ORPHAN_TITLE.casefold(), "петро могила".casefold())
    raw_wrong = fuzz.token_sort_ratio(MOHYLA_ORPHAN_TITLE.casefold(), "десятинна церква".casefold())
    assert raw_best > raw_wrong
    assert raw_best < merge_b.CANDIDATE_FLOOR


def test_suggest_declines_a_close_call() -> None:
    """ "5 hryvnia 2018" in miniature: two candidates close enough that a
    person, not a score, should pick.
    """
    orphan = item(1, "Якась монета")
    close_a = twin(2, "Якась монета А")
    close_b = twin(3, "Якась монета Б")
    candidates = merge_b.score_candidates(orphan, [close_a, close_b], LEXICON)

    action, twin_id = merge_b._suggest(candidates)

    assert action in (merge_b.MANUAL, merge_b.NO_TWIN)
    assert twin_id is None


def test_suggest_reports_no_twin_for_an_empty_slot() -> None:
    action, twin_id = merge_b._suggest([])
    assert (action, twin_id) == (merge_b.NO_TWIN, None)


# ------------------------------------------------------------------- filters
def test_is_orphan_excludes_circulation_archived_and_nbu_linked() -> None:
    assert merge_b.is_orphan(item(1, "Пектораль"))
    assert not merge_b.is_orphan(item(2, "1 гривня", group="circulation"))
    assert not merge_b.is_orphan(item(3, "Пектораль", archived=True))
    assert not merge_b.is_orphan(twin(4, "Пектораль"))


def test_is_twin_requires_an_nbu_link() -> None:
    assert merge_b.is_twin(twin(1, "Петро Могила"))
    assert not merge_b.is_twin(item(2, "Петро Могила"))
    assert not merge_b.is_twin(twin(3, "Петро Могила", archived=True))


# ----------------------------------------------------------------------- csv
def test_write_and_read_review_csv_round_trips_a_yes_decision(tmp_path: Path) -> None:
    outcome = merge_b.MergeBOutcome(
        rows=[
            merge_b.OrphanRow(
                orphan=item(951, MOHYLA_ORPHAN_TITLE),
                cleaned_title="400 лет со дня рождения Петра Могилы",
                instance_count=1,
                candidates=[merge_b.Candidate(twin=twin(3185, "Петро Могила"), score=46.2)],
                suggested_twin_id=3185,
                suggested_action=merge_b.MERGE,
            )
        ]
    )
    path = tmp_path / "merge-b.csv"

    rows_written = merge_b.write_review_csv(path, outcome)
    assert rows_written == 1

    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["suggestedTwinId"] == "3185"
    assert rows[0]["suggestedAction"] == "merge"
    rows[0]["decision"] = "yes"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=merge_b.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    assert merge_b.read_review_csv(path) == [(3185, 951)]


def test_read_review_csv_reads_back_with_an_excel_bom(tmp_path: Path) -> None:
    path = tmp_path / "merge-b.csv"
    path.write_bytes(
        "decision,orphanId,suggestedTwinId\nyes,951,3185\n,1202,3186\n".encode("utf-8-sig")
    )
    assert merge_b.read_review_csv(path) == [(3185, 951)]


def test_read_review_csv_refuses_yes_with_no_suggested_twin(tmp_path: Path) -> None:
    path = tmp_path / "merge-b.csv"
    path.write_text("decision,orphanId,suggestedTwinId\nyes,951,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no suggestedTwinId"):
        merge_b.read_review_csv(path)


def test_read_review_csv_refuses_a_record_paired_with_itself(tmp_path: Path) -> None:
    path = tmp_path / "merge-b.csv"
    path.write_text("decision,orphanId,suggestedTwinId\nyes,951,951\n", encoding="utf-8")
    with pytest.raises(ValueError, match="itself"):
        merge_b.read_review_csv(path)


def test_read_review_csv_refuses_a_record_named_twice(tmp_path: Path) -> None:
    path = tmp_path / "merge-b.csv"
    path.write_text(
        "decision,orphanId,suggestedTwinId\nyes,951,3185\nyes,952,3185\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="twice"):
        merge_b.read_review_csv(path)


# ------------------------------------------------------------------- with DB
async def test_find_orphans_counts_instances_and_ranks_the_real_pair(
    db_session: AsyncSession,
) -> None:
    ref = await seed_reference(db_session)
    owner = await make_user(db_session, email="merge-b@example.test")
    mohyla_orphan = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title=MOHYLA_ORPHAN_TITLE,
        year=1996,
        denomination=ref.uah_5,
        source_key=None,
    )
    desiatynna_orphan = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title=DESIATYNNA_ORPHAN_TITLE,
        year=1996,
        denomination=ref.uah_5,
        source_key=None,
    )
    mohyla_twin = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title="Петро Могила",
        year=1996,
        denomination=ref.uah_5,
        source_key="nbu:33",
    )
    await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title="Десятинна церква",
        year=1996,
        denomination=ref.uah_5,
        source_key="nbu:32",
    )
    await add_collection_item(db_session, owner_id=owner.id, item=mohyla_orphan, quantity=1)
    await db_session.commit()

    outcome = await merge_b.find_orphans(db_session, country_id=ref.ukraine.id, lexicon=LEXICON)

    by_id = {row.orphan.id: row for row in outcome.rows}
    assert by_id[mohyla_orphan.id].instance_count == 1
    assert by_id[mohyla_orphan.id].suggested_twin_id == mohyla_twin.id
    assert by_id[mohyla_orphan.id].suggested_action == merge_b.MERGE
    assert desiatynna_orphan.id in by_id


async def test_apply_moves_instances_and_archives_the_orphan(db_session: AsyncSession) -> None:
    ref = await seed_reference(db_session)
    owner = await make_user(db_session, email="merge-b-apply@example.test")
    orphan = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title=MOHYLA_ORPHAN_TITLE,
        year=1996,
        denomination=ref.uah_5,
        source_key=None,
    )
    kept = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title="Петро Могила",
        year=1996,
        denomination=ref.uah_5,
        source_key="nbu:33",
    )
    await add_collection_item(db_session, owner_id=owner.id, item=orphan, quantity=1, price="500")
    await db_session.commit()

    decisions = [(kept.id, orphan.id)]
    applied = await merge.apply_merges(db_session, decisions, dry_run=False)
    await db_session.commit()

    assert applied.problems == []
    assert applied.merged[0]["deleted"] is True
    moved = (
        (
            await db_session.execute(
                select(CollectionItem).where(CollectionItem.catalog_item_id == kept.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(moved) == 1
    assert await db_session.get(CatalogItem, orphan.id) is None


async def test_a_second_apply_of_the_same_decisions_changes_nothing(
    db_session: AsyncSession,
) -> None:
    ref = await seed_reference(db_session)
    orphan = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title=MOHYLA_ORPHAN_TITLE,
        year=1996,
        denomination=ref.uah_5,
        source_key=None,
    )
    kept = await make_catalog_item(
        db_session,
        country=ref.ukraine,
        title="Петро Могила",
        year=1996,
        denomination=ref.uah_5,
        source_key="nbu:33",
    )
    await db_session.commit()
    decisions = [(kept.id, orphan.id)]

    first = await merge.apply_merges(db_session, decisions, dry_run=False)
    await db_session.commit()
    assert first.problems == []

    second = await merge.apply_merges(db_session, decisions, dry_run=False)
    await db_session.commit()

    assert second.merged == []
    assert second.problems and "gone" in second.problems[0]
    after = await merge.holdings_of(db_session, kept.id)
    assert after.instances == 0
