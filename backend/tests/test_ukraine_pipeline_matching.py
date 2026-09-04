"""The bridge: comparing a Russian title with a Ukrainian one, and reviewing.

No database and no network — this is the decision layer. What is checked is
what the step promises: the dictionary does the work a character ratio cannot,
the threshold holds, a coin belongs to one record, a reference we already hold
outranks any resemblance, and a person's decision in the CSV comes back
exactly as written.

Reading the sources is here too, for the parts a decision depends on: the
coin inside a roll card and the National Bank's own material words.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.models.enums import MetalKind
from app.ukraine_pipeline import bridge
from app.ukraine_pipeline.catalog import OurItem, source_key_reference
from app.ukraine_pipeline.lexicon import load_lexicon, strip_import_noise
from app.ukraine_pipeline.sources import (
    Sources,
    cluster_key,
    nbu_metal,
    official_title,
    roll_coin,
    roll_coin_english,
)
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


# ------------------------------------------------------------- source keys
def test_a_source_key_from_any_source_is_a_reference() -> None:
    """A record made from an NBU card carries that card, and that is a link."""
    assert source_key_reference("nbu:1307") == (SOURCE_NBU, "1307")
    assert source_key_reference("wiki:silver:12") == (SOURCE_WIKIPEDIA, "silver:12")
    assert source_key_reference("https://www.ua-coins.info/ua/list/42-x") == (
        SOURCE_UA_COINS,
        "https://www.ua-coins.info/ua/list/42-x",
    )
    assert source_key_reference("ucoin:ua-1234") is None
    assert source_key_reference(None) is None


def test_the_card_a_record_was_made_from_links_it_without_scoring() -> None:
    """The gaps step's own records must not be scored against ours.

    Both are called "Пектораль" in the same year and face value; the one that
    holds the card is that coin, and the other is what a person looks at.
    """
    sources = sources_of(record(SOURCE_NBU, "1307", "Пектораль", "20", 2021))
    made = item(3106, "Пектораль", "20", 2021, links={SOURCE_NBU: "1307"})
    ours = item(1122, "Пектораль", "20", 2021)
    outcome = bridge.decide([made, ours], sources, LEXICON)

    assert [(d.item.id, d.strategy) for d in outcome.linked] == [(3106, "link")]
    assert [d.item.id for d in outcome.review] == [1122]
    # The review file names the record that took the coin.
    assert outcome.claimed[f"{SOURCE_NBU}:1307"] == 3106


def test_a_wikipedia_article_address_resolves_to_its_cluster() -> None:
    wiki = record(SOURCE_WIKIPEDIA, "silver:12", "Соня садова", "2", 1999)
    sources = sources_of(wiki)
    ours = item(1, "Соня садовая", "2", 1999, links={SOURCE_WIKIPEDIA: wiki.url})
    outcome = bridge.decide([ours], sources, LEXICON)
    assert [d.strategy for d in outcome.linked] == ["link"]


def test_a_decision_rescues_a_record_the_run_gave_no_candidates(tmp_path: Path) -> None:
    """What the gaps step's would-duplicate file is for.

    The record and the coin never met on a score, so the run reports the one
    as having no candidate at all; a person's yes still has to link them.
    """
    sources = sources_of(record(SOURCE_NBU, "1307", "Пектораль з левом", "20", 2021))
    ours = item(1122, "Скіфська пектораль", "20", 2021)
    outcome = bridge.decide([ours], sources, LEXICON)
    assert [i.id for i in outcome.without_candidates] == [1122]

    applied, problems = bridge.apply_review(outcome, {1122: f"{SOURCE_NBU}:1307"}, sources)
    assert problems == []
    assert applied.without_candidates == []
    assert [d.item.id for d in applied.linked] == [1122]


# ------------------------------------------------------------------- rolls
def roll_record(
    source_id: str = "1740",
    *,
    title: str = (
        'Ролик обігових пам`ятних монет "Ми сильні. Ми разом. Запорізька область" '
        "(у ролику 25 монет)"
    ),
    denomination: str = "250",
    label: str = "250 грн",
) -> SourceRecord:
    return SourceRecord(
        source=SOURCE_NBU,
        source_id=source_id,
        title_uk=title,
        denomination=Decimal(denomination),
        denomination_label=label,
        year=2026,
        issue_date="2026-02-24",
        mintage=15_000,
        metal="не вказується (набір)",
        kind="souvenir",
        url="https://bank.gov.ua/ua/uah/numismatic-products/souvenier-coins",
        image_urls=["https://bank.gov.ua/files/coins_images/8GYa.png"],
    )


def test_the_coin_inside_a_roll_is_read_off_the_roll_card() -> None:
    """The catalogue has no card for a circulation commemorative — only for its roll."""
    coin = roll_coin(roll_record())

    assert coin is not None
    assert coin.title_uk == "Ми сильні. Ми разом. Запорізька область"
    assert coin.denomination == Decimal(10)
    assert coin.denomination_label == "10 грн"
    assert coin.kind == "coin"
    assert coin.year == 2026
    assert coin.extra["fromRoll"] == 25
    # The roll's mintage counts rolls, and its material says "набір": neither
    # belongs to the coin.
    assert coin.mintage is None
    assert coin.metal is None
    # The images on the card are the coin's own sides.
    assert coin.image_urls == ["https://bank.gov.ua/files/coins_images/8GYa.png"]


def test_a_roll_of_forty_divides_by_forty() -> None:
    forty = roll_record(
        "1578",
        title=(
            "Ролик обігових пам`ятних монет номіналом 10 гривень "
            "`Сили територіальної оборони Збройних Сил України` (у ролику 40 монет)"
        ),
        denomination="400",
        label="400 грн",
    )
    coin = roll_coin(forty)
    assert coin is not None
    assert coin.title_uk == "Сили територіальної оборони Збройних Сил України"
    assert coin.denomination == Decimal(10)


def test_a_souvenir_that_is_not_a_roll_stays_a_souvenir() -> None:
    packaging = roll_record(title="Сувенірна упаковка до Дня Незалежності", denomination="0")
    assert roll_coin(packaging) is None


def test_the_english_roll_title_names_the_coin() -> None:
    assert (
        roll_coin_english(
            "We Are Strong. We Are United. Zaporizhzhia Oblast "
            "(a roll of circulation commemorative coins) (25 coins to a roll)"
        )
        == "We Are Strong. We Are United. Zaporizhzhia Oblast"
    )
    assert (
        roll_coin_english(
            "The Territorial Defense Forces of Ukraine's Armed Forces "
            "(a roll of 10-hryvnia circulation commemorative coins) "
            "(each roll contains 40 coins)"
        )
        == "The Territorial Defense Forces of Ukraine's Armed Forces"
    )
    assert roll_coin_english(None) is None


def test_a_circulation_commemorative_matches_through_its_roll_card() -> None:
    """The defect: "Ми сильні. Ми разом" 2026 had no candidate at all.

    The numismatic catalogue has no card for a 10-hryvnia circulation coin, so
    until the roll cards were read the whole series arrived at the bridge with
    nothing to match against.
    """
    coin = roll_coin(roll_record())
    assert coin is not None
    sources = sources_of(coin)
    ours = item(
        1,
        "Ми сильні. Ми разом. Запорізька область",
        "10",
        2026,
        group="circulation",
    )
    outcome = bridge.decide([ours], sources, LEXICON)

    assert outcome.without_candidates == []
    assert [d.item.id for d in outcome.linked] == [1]
    assert outcome.summary()["linkedByGroup"] == {"circulation": 1}


def test_the_nbu_material_words_are_read() -> None:
    """Nine words, all Ukrainian; the general parser only knows the Russian ones."""
    assert nbu_metal("срібло") == (None, MetalKind.PRECIOUS)
    assert nbu_metal("золото") == (None, MetalKind.PRECIOUS)
    assert nbu_metal("нейзильбер") == ("nickel_silver", MetalKind.BASE)
    assert nbu_metal("біметалеві із недорогоцінних металів") == ("bimetal", MetalKind.BASE)
    assert nbu_metal("біметалеві із дорогоцінних металів") == ("bimetal", MetalKind.PRECIOUS)
    assert nbu_metal("не вказується (набір)") == (None, MetalKind.UNKNOWN)
    # An unreadable material is unknown, not base metal.
    assert nbu_metal(None) == (None, MetalKind.UNKNOWN)
    # The uCoin-shaped strings our own catalogue carries still work.
    assert nbu_metal("AgСеребро 0.925, 33.62g") == ("silver_925", MetalKind.PRECIOUS)
