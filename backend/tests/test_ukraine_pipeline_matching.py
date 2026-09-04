"""The bridge: comparing a Russian title with a Ukrainian one, and reviewing.

No database and no network — this is the decision layer. What is checked is
what the step promises: the dictionary does the work a character ratio cannot,
the threshold holds, a coin belongs to one record, and a person's decision in
the CSV comes back exactly as written.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.ukraine_pipeline import bridge
from app.ukraine_pipeline.catalog import OurItem
from app.ukraine_pipeline.lexicon import load_lexicon, strip_import_noise
from app.ukraine_pipeline.sources import Sources, cluster_key, official_title
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA, SourceRecord
from app.ukraine_recon.triangulate import cluster_records

LEXICON = load_lexicon()


def record(
    source: str,
    source_id: str,
    title: str,
    denomination: str,
    year: int,
    *,
    kind: str = "coin",
    price: str | None = None,
    series: str | None = None,
    images: list[str] | None = None,
) -> SourceRecord:
    return SourceRecord(
        source=source,
        source_id=source_id,
        title_uk=title,
        denomination=Decimal(denomination),
        year=year,
        url=f"https://example.test/{source}/{source_id}",
        kind=kind,
        price=None if price is None else Decimal(price),
        series=series,
        image_urls=images or [],
    )


def item(
    item_id: int,
    title: str,
    denomination: str | None,
    year: int,
    *,
    group: str = "commemorative",
    links: dict[str, str] | None = None,
    archived: bool = False,
) -> OurItem:
    return OurItem(
        id=item_id,
        title_original=title,
        title_uk=None,
        title_en=None,
        issue_year=year,
        denomination=None if denomination is None else Decimal(denomination),
        denomination_id=1,
        collection_group=group,
        series_id=None,
        series_name=None,
        is_archived=archived,
        links=links or {},
    )


def sources_of(*records: SourceRecord) -> Sources:
    by_source: dict[str, list[SourceRecord]] = {
        SOURCE_NBU: [],
        SOURCE_UA_COINS: [],
        SOURCE_WIKIPEDIA: [],
    }
    for entry in records:
        by_source[entry.source].append(entry)
    found = Sources(
        nbu=by_source[SOURCE_NBU],
        ua_coins=by_source[SOURCE_UA_COINS],
        wikipedia=by_source[SOURCE_WIKIPEDIA],
    )
    found.clusters = cluster_records(found.by_source())
    return found


# ------------------------------------------------------------------- lexicon
@pytest.mark.parametrize(
    ("ours", "theirs"),
    [
        ("Богдан Хмельницкий", "Богдан Хмельницький"),
        ("150 лет со дня рождения Ивана Труша", "150 років від дня народження Івана Труша"),
        ("Десятинная церковь", "Десятинна церква"),
        ("70 лет освобождению Харькова", "70 років визволення Харкова"),
        ("10 лет независимости Украины", "10 років незалежності України"),
        ('Ледокол "Капитан Белоусов"', "Криголам «Капітан Бєлоусов»"),
    ],
)
def test_the_same_coin_in_two_languages_scores_as_a_match(ours: str, theirs: str) -> None:
    assert LEXICON.score(ours, theirs) >= bridge.AUTO_THRESHOLD


@pytest.mark.parametrize(
    ("ours", "theirs"),
    [("Дельфін", "Козак Мамай"), ("Знаки зодиака - Овен", "Рік Дракона")],
)
def test_different_coins_stay_far_apart(ours: str, theirs: str) -> None:
    assert LEXICON.score(ours, theirs) < bridge.REVIEW_THRESHOLD


def test_the_series_prefix_and_the_terse_official_name() -> None:
    """Our titles carry the series; the NBU names the coin as tersely as it can."""
    assert LEXICON.score("Флора и фауна - Соня садовая", "Соня садова") >= bridge.AUTO_THRESHOLD
    assert LEXICON.score("Князь Кий", "Кий") >= bridge.AUTO_THRESHOLD
    assert LEXICON.score("Княгиня Ольга", "Ольга") >= bridge.AUTO_THRESHOLD


def test_the_importer_heading_is_not_part_of_the_name() -> None:
    glued = "2.000.000 карбованцев, 1995 50 лет ООН AgСеребро 0.925, 33.62g, ø 38.61mm"
    assert strip_import_noise(glued) == "50 лет ООН"
    assert LEXICON.score(glued, "50 років ООН") == 100.0
    # A title with nothing glued on is left alone.
    assert strip_import_noise("Дельфін") == "Дельфін"


def test_the_official_title_loses_the_marker_the_packaging_and_the_quotes() -> None:
    assert (
        official_title('"До 35-річчя Незалежності України"') == "До 35-річчя Незалежності України"
    )
    packaged = '"150 років від дня народження Олександра Кошиця" у сувенірному пакованні (н)'
    assert official_title(packaged) == "150 років від дня народження Олександра Кошиця"
    # The two markers come in either order.
    assert (
        official_title('`Морський дрон "Sea Baby"` (н) у сувенірному пакованні')
        == 'Морський дрон "Sea Baby"'
    )
    # A Latin letter inside a Cyrillic word is the same word.
    assert official_title("Перемога у ВВВ 1941-1945 рокiв") == "Перемога у ВВВ 1941-1945 років"


# -------------------------------------------------------------------- bridge
def test_a_reference_we_hold_outranks_a_resemblance() -> None:
    sources = sources_of(
        record(SOURCE_UA_COINS, "42", "Козак Мамай", "20", 1997),
        record(SOURCE_NBU, "7", "Дельфін", "2", 1997),
    )
    ours = item(
        1,
        "Дельфин",
        "2",
        1997,
        links={SOURCE_UA_COINS: "https://www.ua-coins.info/ua/list/42-kozak-mamay"},
    )
    outcome = bridge.decide([ours], sources, LEXICON)
    assert [d.strategy for d in outcome.linked] == ["link"]
    assert cluster_key(outcome.linked[0].cluster) == f"{SOURCE_UA_COINS}:42"


def test_a_clear_winner_is_linked_and_a_tie_is_reviewed() -> None:
    sources = sources_of(
        record(SOURCE_NBU, "1", "Соня садова", "2", 1999),
        record(SOURCE_NBU, "2", "Орел степовий", "2", 1999),
        # The mint struck the same name twice; nothing in the title separates
        # them, so no score can choose and a person has to.
        record(SOURCE_NBU, "3", "Місто-герой Київ", "200000", 1995),
        record(SOURCE_NBU, "4", "Місто-герой Київ", "200000", 1995),
    )
    clear = item(1, "Флора и фауна - Соня садовая", "2", 1999)
    ambiguous = item(2, "Города-герои Украины - Киев", "200000", 1995)
    outcome = bridge.decide([clear, ambiguous], sources, LEXICON)

    assert [d.item.id for d in outcome.linked] == [1]
    assert [d.item.id for d in outcome.review] == [2]


def test_a_coin_belongs_to_one_record_and_the_second_goes_to_review() -> None:
    """Two of our records matching one coin is a duplicate, not a better match."""
    sources = sources_of(record(SOURCE_NBU, "1", "Соня садова", "2", 1999))
    first = item(1, "Соня садовая", "2", 1999)
    second = item(2, "Соня садовая", "2", 1999)
    outcome = bridge.decide([first, second], sources, LEXICON)

    assert [d.item.id for d in outcome.linked] == [1]
    assert [d.item.id for d in outcome.review] == [2]
    assert outcome.claimed[f"{SOURCE_NBU}:1"] == 1


def test_archived_records_are_left_alone() -> None:
    sources = sources_of(record(SOURCE_NBU, "1", "Соня садова", "2", 1999))
    outcome = bridge.decide(
        [item(1, "Соня садовая", "2", 1999, archived=True)],
        sources,
        LEXICON,
    )
    assert outcome.linked == []
    assert outcome.skipped_archived == 1


def test_a_circulation_coin_with_an_nbu_card_is_linked_like_any_other() -> None:
    """ "обігові пам'ятні" — a circulation coin the NBU still catalogues by name.

    The bridge no longer restricts itself to `commemorative`/`collector`
    records: a circulation coin with a matching cluster gets a title from the
    NBU exactly like a commemorative one does.
    """
    sources = sources_of(record(SOURCE_NBU, "1", "Області України", "10", 2026))
    ours = item(1, "Області України", "10", 2026, group="circulation")
    outcome = bridge.decide([ours], sources, LEXICON)

    assert [d.item.id for d in outcome.linked] == [1]
    assert outcome.summary()["linkedByGroup"] == {"circulation": 1}


def test_a_circulation_coin_with_no_matching_cluster_has_no_candidates() -> None:
    """Widening the bridge's scope does not invent matches out of nothing."""
    sources = sources_of(record(SOURCE_NBU, "1", "Соня садова", "2", 1999))
    ours = item(1, "Гривня обігова", "1", 2010, group="circulation")
    outcome = bridge.decide([ours], sources, LEXICON)

    assert outcome.linked == []
    assert [i.id for i in outcome.without_candidates] == [1]


def test_a_coin_of_another_year_is_not_a_candidate() -> None:
    sources = sources_of(record(SOURCE_NBU, "1", "Соня садова", "2", 1990))
    outcome = bridge.decide([item(1, "Соня садовая", "2", 1999)], sources, LEXICON)
    assert outcome.without_candidates and not outcome.linked


def test_the_year_may_be_off_by_one() -> None:
    """The year struck and the date of entering circulation differ at New Year."""
    sources = sources_of(record(SOURCE_NBU, "1", "Соня садова", "2", 2000))
    outcome = bridge.decide([item(1, "Соня садовая", "2", 1999)], sources, LEXICON)
    assert [d.item.id for d in outcome.linked] == [1]


# -------------------------------------------------------------------- review
def test_the_review_file_is_written_read_and_applied(tmp_path: Path) -> None:
    sources = sources_of(
        record(SOURCE_NBU, "3", "Місто-герой Київ", "200000", 1995),
        record(SOURCE_NBU, "4", "Місто-герой Київ", "200000", 1995),
    )
    ours = item(2, "Города-герои Украины - Киев", "200000", 1995)
    outcome = bridge.decide([ours], sources, LEXICON)
    assert len(outcome.review) == 1

    path = tmp_path / "bridge-review.csv"
    rows = bridge.write_review_csv(path, outcome)
    assert rows == len(outcome.review[0].candidates)

    text = path.read_text(encoding="utf-8")
    chosen = f"{SOURCE_NBU}:4"
    marked = "\n".join(
        ("yes" + line[len("") :] if line.startswith(",2,") and chosen in line else line)
        for line in text.splitlines()
    )
    path.write_text(marked, encoding="utf-8")

    decisions = bridge.read_review_csv(path)
    assert decisions == {2: chosen}

    applied, problems = bridge.apply_review(outcome, decisions, sources)
    assert problems == []
    assert applied.review == []
    assert cluster_key(applied.linked[0].cluster) == chosen


def test_the_review_file_reads_back_with_an_excel_bom(tmp_path: Path) -> None:
    """Excel saves a reviewed CSV back with a UTF-8 BOM; it must not break the header."""
    path = tmp_path / "review.csv"
    path.write_bytes("decision,itemId,clusterKey\nyes,2,nbu:4\n".encode("utf-8-sig"))
    assert bridge.read_review_csv(path) == {2: "nbu:4"}


def test_two_decisions_for_one_record_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "review.csv"
    path.write_text(
        "decision,itemId,clusterKey\nyes,2,nbu:3\nyes,2,nbu:4\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="two clusters"):
        bridge.read_review_csv(path)


def test_an_unknown_cluster_in_the_review_is_reported_not_applied(tmp_path: Path) -> None:
    sources = sources_of(
        record(SOURCE_NBU, "3", "Місто-герой Київ", "200000", 1995),
        record(SOURCE_NBU, "4", "Місто-герой Київ", "200000", 1995),
    )
    outcome = bridge.decide(
        [item(2, "Города-герои Украины - Киев", "200000", 1995)], sources, LEXICON
    )
    applied, problems = bridge.apply_review(outcome, {2: "nbu:999"}, sources)
    assert problems and "nbu:999" in problems[0]
    assert len(applied.review) == 1


def test_the_links_a_cluster_yields() -> None:
    sources = sources_of(
        record(SOURCE_NBU, "5", "Соня садова", "2", 1999),
        record(SOURCE_UA_COINS, "77", "Соня садова", "2", 1999),
        record(SOURCE_WIKIPEDIA, "9", "Соня садова", "2", 1999),
    )
    links = bridge.links_of(sources.clusters[0])
    # ua-coins and Wikipedia have a page per coin; the NBU has none, so its
    # reference is the card id.
    assert links[SOURCE_UA_COINS].startswith("https://")
    assert links[SOURCE_WIKIPEDIA].startswith("https://")
    assert links[SOURCE_NBU] == "5"
