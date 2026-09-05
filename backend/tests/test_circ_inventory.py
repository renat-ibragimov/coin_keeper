"""inventory-b: the survey CSV of what part B's bridge left unlinked.

No database and no network — build_inventory works on OurItem plus a
Sources object built by hand from real-shaped SourceRecord data, exactly the
way app/ukraine_pipeline/bridge.py's own tests do. What is checked: the metal
guess and yearly-set marker read off title text alone, a fuzzy NBU candidate
selects `link`, a title with a set marker and no candidate selects `archive`
(never a `set` action — collection_group has no such enum value), and the
CSV shape is exactly what jubilee_bridge.read_review_csv already expects.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from app.ukraine_pipeline import circ_inventory, jubilee_bridge
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.lexicon import load_lexicon
from app.ukraine_pipeline.sources import Sources
from app.ukraine_recon.models import SOURCE_NBU, SourceRecord

LEXICON = load_lexicon()


def item(
    item_id: int,
    title: str,
    year: int,
    *,
    group: str = "commemorative",
    archived: bool = False,
    links: dict[str, str] | None = None,
) -> OurItem:
    return OurItem(
        id=item_id,
        title_original=title,
        title_uk=None,
        title_en=None,
        issue_year=year,
        denomination=Decimal(5),
        denomination_id=1,
        collection_group=group,
        series_id=None,
        series_name=None,
        is_archived=archived,
        links=links or {},
    )


def nbu_record(source_id: str, title: str, year: int) -> SourceRecord:
    return SourceRecord(
        source=SOURCE_NBU,
        source_id=source_id,
        title_uk=title,
        denomination=Decimal(5),
        year=year,
        url="https://bank.gov.ua/ua/uah/numismatic-products/souvenier-coins",
    )


def test_metal_guess_reads_the_title_text() -> None:
    assert circ_inventory.metal_guess("Золота монета Ярослав Мудрий") == "золото"
    assert circ_inventory.metal_guess("Срібна монета") == "срібло"
    assert circ_inventory.metal_guess("Серебряная монета") == "срібло"
    assert circ_inventory.metal_guess("Мідно-нікелевий сплав") == "не визначено"


def test_is_set_recognizes_ukrainian_and_russian_markers() -> None:
    assert circ_inventory.is_set("Річний набір монет України 2015 року")
    assert circ_inventory.is_set("Годовой набор монет 2015 года")
    assert not circ_inventory.is_set("Ярослав Мудрий")


def test_build_inventory_links_a_record_a_fuzzy_candidate_clears() -> None:
    matching = item(1, "Ярослав Мудрий", 2015)
    sources = Sources(nbu=[nbu_record("777", "Ярослав Мудрий", 2015)])

    outcome = circ_inventory.build_inventory([matching], sources, LEXICON)

    assert len(outcome.rows) == 1
    row = outcome.rows[0]
    assert row.suggested_action == "link"
    assert row.candidates[0][0] == "777"


def test_build_inventory_suggests_archive_for_a_yearly_set_with_no_candidate() -> None:
    yearly_set = item(2, "Річний набір монет України 2015 року", 2015)
    sources = Sources(nbu=[nbu_record("777", "Щось зовсім інше", 1995)])

    outcome = circ_inventory.build_inventory([yearly_set], sources, LEXICON)

    assert outcome.rows[0].suggested_action == "archive"


def test_build_inventory_suggests_manual_for_everything_else() -> None:
    mystery = item(3, "Якась незрозуміла монета без аналогів", 2015)
    sources = Sources(nbu=[nbu_record("777", "Щось зовсім інше", 1995)])

    outcome = circ_inventory.build_inventory([mystery], sources, LEXICON)

    assert outcome.rows[0].suggested_action == "manual"


def test_build_inventory_skips_archived_and_already_nbu_linked_records() -> None:
    archived = item(4, "Ярослав Мудрий", 2015, archived=True)
    linked = item(5, "Ярослав Мудрий", 2015, links={SOURCE_NBU: "777"})
    circulation = item(6, "1 гривня", 2015, group="circulation")
    sources = Sources(nbu=[nbu_record("777", "Ярослав Мудрий", 2015)])

    outcome = circ_inventory.build_inventory([archived, linked, circulation], sources, LEXICON)

    assert outcome.rows == []


def test_write_csv_matches_jubilee_bridges_own_review_shape(tmp_path: Path) -> None:
    """The whole point of sharing a column shape: jubilee_bridge's own
    read_review_csv must accept a decision written against inventory-b's
    output unmodified.
    """
    matching = item(1, "Ярослав Мудрий", 2015)
    sources = Sources(nbu=[nbu_record("777", "Ярослав Мудрий", 2015)])
    outcome = circ_inventory.build_inventory([matching], sources, LEXICON)
    path = tmp_path / "inventory.csv"

    rows_written = circ_inventory.write_csv(path, outcome)
    assert rows_written == 1

    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["decision"] = "yes"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=circ_inventory.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    decisions = jubilee_bridge.read_review_csv(path)
    assert decisions == {1: "777"}
