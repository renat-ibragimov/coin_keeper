"""The circulation mini-pipeline: types, the mintage table, and circ-bridge,
circ-gaps, circ-titles, circ-mintage, circ-photos.

Fixture HTML is a small, hand-built stand-in for the real pages — the same
shape (a wikitable with a mint-name divider row, a "Про монети" page with two
stacked `div.hide-show-currency` cards) rather than the pages themselves, so
a test failure points at a real structural change instead of the size of the
download.
"""

from __future__ import annotations

import csv
import io
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogItem, Denomination, MediaFile, PriceSourceLink
from app.models.enums import CollectionGroup, MatchStatus, MediaSource, TranslationSource
from app.ukraine_pipeline import (
    circ_bridge,
    circ_gaps,
    circ_mintage,
    circ_photos,
    circ_reclassify,
    circ_titles,
)
from app.ukraine_pipeline.catalog import LINK_SOURCES, OurItem, load_items, ukraine_country_id
from app.ukraine_pipeline.circ_nbu import page_url, parse_page, pick_card
from app.ukraine_pipeline.circ_types import SUBTYPE_1992, SUBTYPE_2018, TYPES, type_for
from app.ukraine_recon.http import PoliteClient
from app.ukraine_recon.models import SOURCE_NBU
from app.ukraine_recon.wikipedia import parse_mintage_table
from tests.seed import country_by_code, make_catalog_item, seed_currencies

MINTAGE_TABLE_HTML = """
<table class="wikitable">
<tr><th>Рік на<br/>монеті</th><th>1 копійка</th><th>2 копійки</th><th>5 копійок</th>
<th>10 копійок</th><th>25 копійок</th><th>50 копійок</th><th>1 гривня</th>
<th>2 гривні</th><th>5 гривень</th><th>10 гривень</th><th>Загалом</th></tr>
<tr><th colspan="12">Тестовий монетний двір</th></tr>
<tr><td>1992</td><td>610 млн</td><td>Ні</td><td>446 млн</td><td>480 млн</td><td>402 млн</td>
<td>Ні</td><td>Ні</td><td>Ні</td><td>Ні</td><td>Ні</td><td>1938 млн</td></tr>
<tr><td>2004</td><td>Ні</td><td>Ні</td><td>Ні</td><td>Ні</td><td>Ні</td>
<td>Ні</td><td>10 млн</td><td>Ні</td><td>Ні</td><td>Ні</td><td>10 млн</td></tr>
<tr><td>2013</td><td>10 тис**</td><td>Ні</td><td>175 млн</td><td>210 млн</td><td>180 млн</td>
<td>60 млн</td><td>10 тис**</td><td>Ні</td><td>Ні</td><td>Ні</td><td>625 млн</td></tr>
<tr><td>2018</td><td>10 тис**</td><td>10 тис**</td><td>10 тис**</td><td>10 тис**</td>
<td>10 тис**</td><td>65 млн</td><td>140 млн***** 20 тис****</td><td>145 млн</td><td>Ні</td>
<td>Ні</td><td>350 млн</td></tr>
<tr><td>2019</td><td>?***</td><td>Ні</td><td>Ні</td><td>200 млн</td><td>Ні</td><td>20 тис**</td>
<td>50 млн</td><td>67 млн</td><td>20 млн</td><td>Ні</td><td>337 млн</td></tr>
</table>
"""


def obig_page_html(*cards: tuple[str, str, str]) -> str:
    """cards = (title, status, intro_date) -> a synthetic "Про монети" page."""
    blocks = []
    for index, (title, status, intro_date) in enumerate(cards):
        blocks.append(
            f"""
            <div class="hide-show-currency">
              <div class="box mt1"><h3>{title}</h3></div>
              <div class="tag">{status}</div>
              <div class="box"><p>
                Дата введення в обіг — {intro_date}<br>
                Метал — низьковуглецева сталь з нікелевим покривом<br>
                Роки карбування — 2018, 2019
              </p></div>
              <div class="box"><div class="row thin">
                <div class="col-sm-6"><div class="image">
                  <img src="/admin_uploads/coin/{index}a.png" alt="{title} (аверс)"></div></div>
                <div class="col-sm-6"><div class="image">
                  <img src="/admin_uploads/coin/{index}r.png" alt="{title} (реверс)"></div></div>
              </div></div>
            </div>
            """
        )
    return "<html><body>" + "".join(blocks) + "</body></html>"


def png_bytes(side: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (side, side), (10, 20, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------------------------------------------------- circ_types
def test_every_year_of_every_denomination_matches_at_most_one_type() -> None:
    denominations = {(coin_type.value, coin_type.unit) for coin_type in TYPES}
    for value, unit in denominations:
        for year in range(1990, 2028):
            matches = [
                t
                for t in TYPES
                if t.value == value
                and t.unit == unit
                and year >= t.year_from
                and (t.year_to is None or year <= t.year_to)
            ]
            assert len(matches) <= 1, f"{value} {unit} {year} matches {len(matches)} types"


def test_the_2018_hryvnia_split_has_no_overlap() -> None:
    old = type_for(Decimal(1), "hryvnia", 2017)
    new = type_for(Decimal(1), "hryvnia", 2018)
    assert old is not None and old.subtype == SUBTYPE_1992
    assert new is not None and new.subtype == SUBTYPE_2018


def test_years_before_ukraine_existed_match_nothing() -> None:
    assert type_for(Decimal(1), "kopiika", 1990) is None
    assert type_for(Decimal(2), "hryvnia", 2010) is None


# --------------------------------------------------------------- wikipedia table
def test_the_mintage_table_reads_plain_and_glued_and_dual_cells() -> None:
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)
    by_key = {(c.value, c.unit, c.year): c for c in cells}

    plain = by_key[(Decimal(1), "kopiika", 1992)]
    assert plain.entries[0].count == 610_000_000

    zero = by_key[(Decimal(2), "kopiika", 1992)]
    assert zero.entries[0].count == 0

    collector = by_key[(Decimal(1), "kopiika", 2013)]
    assert collector.entries[0].count == 10_000
    assert collector.entries[0].collector_set

    dual = by_key[(Decimal(1), "hryvnia", 2018)]
    assert {(e.count, e.pattern) for e in dual.entries} == {(140_000_000, "2018"), (20_000, "2001")}

    unofficial = by_key[(Decimal(1), "kopiika", 2019)]
    assert unofficial.entries[0].unknown


def test_the_mint_name_divider_row_is_not_mistaken_for_a_year() -> None:
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)
    assert all(1900 < cell.year < 2100 for cell in cells)


# --------------------------------------------------------------------- circ_nbu
def test_the_page_stacks_every_card_and_pick_card_finds_the_right_one() -> None:
    html = obig_page_html(
        ("1 гривня зразка 2018 року", "В обігу", "27.04.2018"),
        ("1 гривня", "Поступово вилучається з обігу", "12.03.1997"),
    )
    cards = parse_page(html)
    assert [c.title for c in cards] == ["1 гривня зразка 2018 року", "1 гривня"]
    assert cards[0].images == {
        "obverse": "https://bank.gov.ua/admin_uploads/coin/0a.png",
        "reverse": "https://bank.gov.ua/admin_uploads/coin/0r.png",
    }

    old_type = type_for(Decimal(1), "hryvnia", 2017)
    new_type = type_for(Decimal(1), "hryvnia", 2018)
    assert old_type is not None and new_type is not None
    assert pick_card(cards, old_type).title == "1 гривня"  # type: ignore[union-attr]
    assert pick_card(cards, new_type).title == "1 гривня зразка 2018 року"  # type: ignore[union-attr]


def test_a_type_with_no_hint_takes_the_first_card() -> None:
    kopiika_type = type_for(Decimal(1), "kopiika", 2000)
    assert kopiika_type is not None
    cards = parse_page(obig_page_html(("1 копійка", "Вилучена з обігу", "02.09.1996")))
    assert pick_card(cards, kopiika_type).title == "1 копійка"  # type: ignore[union-attr]


def test_page_url_is_the_ua_uah_obig_coin_path() -> None:
    assert page_url("50_2013") == "https://bank.gov.ua/ua/uah/obig-coin/50_2013"


def test_pick_card_normalizes_nbsp_before_comparing_titles() -> None:
    """bank.gov.ua has been seen gluing a title with a non-breaking space."""
    glued_title = "1\xa0гривня зразка 2018 року"
    html = obig_page_html(
        (glued_title, "В обігу", "27.04.2018"),
        ("1 гривня", "Поступово вилучається з обігу", "12.03.1997"),
    )
    cards = parse_page(html)
    new_type = type_for(Decimal(1), "hryvnia", 2018)
    assert new_type is not None
    picked = pick_card(cards, new_type)
    assert picked is not None and picked.title == glued_title


# ------------------------------------------------------------------- circ_bridge
def test_a_denomination_is_read_off_the_title() -> None:
    parsed = circ_bridge.parse_title_denomination("25 копеек, 1994")
    assert parsed is not None
    assert parsed.value == Decimal(25)
    assert parsed.unit == "kopiika"


def test_an_unreadable_title_is_left_alone() -> None:
    assert circ_bridge.parse_title_denomination("Пектораль") is None


async def test_repair_fills_denomination_id_only_where_it_is_missing(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    unresolved = await make_catalog_item(
        db_session,
        country=country,
        title="25 копеек, 1994",
        year=1994,
        group=CollectionGroup.CIRCULATION,
    )
    items = await load_items(db_session, country.id)

    outcome = await circ_bridge.repair_denominations(
        db_session, country_id=country.id, items=items, dry_run=False
    )
    await db_session.commit()

    assert len(outcome.filled) == 1
    refreshed = await db_session.get(CatalogItem, unresolved.id)
    assert refreshed is not None and refreshed.denomination_id is not None
    denomination = await db_session.get(Denomination, refreshed.denomination_id)
    assert denomination is not None
    assert denomination.value == Decimal(25) and denomination.unit == "kopiika"


def _item(item_id: int, *, value: str, unit: str, year: int, denomination_id: int = 1) -> OurItem:
    return OurItem(
        id=item_id,
        title_original=f"{value} {unit}",
        title_uk=None,
        title_en=None,
        issue_year=year,
        denomination=Decimal(value),
        denomination_id=denomination_id,
        collection_group=str(CollectionGroup.CIRCULATION),
        series_id=None,
        series_name=None,
        is_archived=False,
        denomination_unit=unit,
    )


def test_one_candidate_links_two_candidates_go_to_review() -> None:
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)
    unique = _item(1, value="1", unit="kopiika", year=1992)
    twin_a = _item(2, value="1", unit="hryvnia", year=2019)
    twin_b = _item(3, value="1", unit="hryvnia", year=2019)
    unmatched = _item(4, value="50", unit="hryvnia", year=1992)

    outcome = circ_bridge.decide([unique, twin_a, twin_b, unmatched], cells)

    assert [item.id for item in outcome.linked] == [1]
    assert {item.id for item, _count in outcome.review} == {2, 3}
    assert outcome.review[0][1] == 2
    assert unmatched in outcome.without_wikipedia_entry


def test_review_csv_round_trips(tmp_path: Path) -> None:
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)
    twin_a = _item(2, value="1", unit="hryvnia", year=2019)
    twin_b = _item(3, value="1", unit="hryvnia", year=2019)
    outcome = circ_bridge.decide([twin_a, twin_b], cells)

    path = tmp_path / "circ-review.csv"
    rows = circ_bridge.write_review_csv(path, outcome)
    assert rows == 2

    # Mark the first candidate yes, the way a person edits the CSV by hand.
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = list(csv.DictReader(handle))
    for row in reader:
        if int(row["itemId"]) == twin_a.id:
            row["decision"] = "yes"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=circ_bridge.CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(reader)

    chosen = circ_bridge.read_review_csv(path)
    assert chosen == {twin_a.id}

    applied = circ_bridge.apply_review(outcome, chosen)
    assert [item.id for item in applied.linked] == [twin_a.id]
    assert [item.id for item, _count in applied.review] == [twin_b.id]


# --------------------------------------------------------------------- circ_gaps
async def test_gaps_creates_a_kopiika_and_a_2018_hryvnia(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)

    outcome = await circ_gaps.create_missing(
        db_session, country_id=country.id, items=[], mintage=cells, dry_run=False
    )
    await db_session.commit()

    assert outcome.summary()["created"] >= 2
    kopiika = (
        await db_session.execute(
            select(CatalogItem).where(CatalogItem.source_key == "wiki-circ:1-kopiika:1992")
        )
    ).scalar_one()
    assert kopiika.title_uk == "1 копійка"
    assert kopiika.title_en == "1 kopiika"
    assert kopiika.collection_group is CollectionGroup.CIRCULATION
    assert kopiika.composition_id is not None
    assert kopiika.created_by is None

    hryvnia_2018 = (
        await db_session.execute(
            select(CatalogItem).where(CatalogItem.source_key == "wiki-circ:1-hryvnia:2018")
        )
    ).scalar_one()
    assert hryvnia_2018.subtype == SUBTYPE_2018


async def test_gaps_does_not_duplicate_an_unlinked_record_in_the_same_slot(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(1), unit="kopiika", sort_order=1
    )
    db_session.add(denomination)
    await db_session.commit()
    await make_catalog_item(
        db_session,
        country=country,
        title="1 копейка",
        year=1992,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)

    items = await load_items(db_session, country.id)
    outcome = await circ_gaps.create_missing(
        db_session, country_id=country.id, items=items, mintage=cells, dry_run=False
    )
    await db_session.commit()

    assert outcome.summary()["skippedAlreadyPresent"] >= 1
    total = (
        (
            await db_session.execute(
                select(CatalogItem).where(
                    CatalogItem.country_id == country.id,
                    CatalogItem.issue_year == 1992,
                    CatalogItem.denomination_id == denomination.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(total) == 1


async def test_gaps_run_twice_creates_nothing_the_second_time(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)

    first = await circ_gaps.create_missing(
        db_session, country_id=country.id, items=[], mintage=cells, dry_run=False
    )
    await db_session.commit()
    items = await load_items(db_session, country.id)
    second = await circ_gaps.create_missing(
        db_session, country_id=country.id, items=items, mintage=cells, dry_run=False
    )
    await db_session.commit()

    assert first.summary()["created"] > 0
    assert second.summary()["created"] == 0


# ------------------------------------------------------------------- circ_titles
async def test_titles_are_the_official_declined_numeral(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(25), unit="kopiika", sort_order=25
    )
    db_session.add(denomination)
    await db_session.commit()
    item = await make_catalog_item(
        db_session,
        country=country,
        title="25 копеек",
        year=1996,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )

    outcome = await circ_titles.apply_titles(db_session, country_id=country.id, dry_run=False)
    await db_session.commit()

    assert outcome.updated == 1
    refreshed = await db_session.get(CatalogItem, item.id)
    assert refreshed is not None
    assert refreshed.title_uk == "25 копійок"
    assert refreshed.title_original == "25 копійок"
    assert refreshed.title_en == "25 kopiikas"
    assert refreshed.title_uk_source is TranslationSource.OFFICIAL


async def test_titles_do_not_overwrite_a_manual_correction(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(1), unit="hryvnia", sort_order=100
    )
    db_session.add(denomination)
    await db_session.commit()
    item = await make_catalog_item(
        db_session,
        country=country,
        title="Одна гривня (правка адміна)",
        year=2010,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
        title_uk="Одна гривня (правка адміна)",
        title_uk_source=TranslationSource.MANUAL,
    )

    await circ_titles.apply_titles(db_session, country_id=country.id, dry_run=False)
    await db_session.commit()

    refreshed = await db_session.get(CatalogItem, item.id)
    assert refreshed is not None
    assert refreshed.title_uk == "Одна гривня (правка адміна)"


async def test_titles_run_twice_change_nothing_the_second_time(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(5), unit="kopiika", sort_order=5
    )
    db_session.add(denomination)
    await db_session.commit()
    await make_catalog_item(
        db_session,
        country=country,
        title="5 копеек",
        year=2005,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )

    await circ_titles.apply_titles(db_session, country_id=country.id, dry_run=False)
    await db_session.commit()
    second = await circ_titles.apply_titles(db_session, country_id=country.id, dry_run=False)
    await db_session.commit()

    assert second.updated == 0
    assert second.unchanged == 1


# ------------------------------------------------------------------ circ_mintage
async def test_mintage_fills_an_empty_field_only(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(1), unit="kopiika", sort_order=1
    )
    db_session.add(denomination)
    await db_session.commit()
    empty = await make_catalog_item(
        db_session,
        country=country,
        title="1 копійка",
        year=1992,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )
    filled = await make_catalog_item(
        db_session,
        country=country,
        title="1 копійка",
        year=1992,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
        mintage_actual=999,
    )
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)

    outcome = await circ_mintage.apply_mintage(
        db_session, country_id=country.id, mintage=cells, dry_run=False
    )
    await db_session.commit()

    refreshed_empty = await db_session.get(CatalogItem, empty.id)
    refreshed_filled = await db_session.get(CatalogItem, filled.id)
    assert refreshed_empty is not None and refreshed_empty.mintage_actual == 610_000_000
    assert refreshed_filled is not None and refreshed_filled.mintage_actual == 999
    assert outcome.discrepancies and outcome.discrepancies[0]["itemId"] == filled.id


async def test_mintage_resolves_the_2018_hryvnia_split_by_subtype(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(1), unit="hryvnia", sort_order=100
    )
    db_session.add(denomination)
    await db_session.commit()
    old_pattern = await make_catalog_item(
        db_session,
        country=country,
        title="1 гривня",
        year=2018,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
        subtype=SUBTYPE_1992,
    )
    new_pattern = await make_catalog_item(
        db_session,
        country=country,
        title="1 гривня зразка 2018 року",
        year=2018,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
        subtype=SUBTYPE_2018,
    )
    no_subtype = await make_catalog_item(
        db_session,
        country=country,
        title="1 гривня (?)",
        year=2018,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)

    outcome = await circ_mintage.apply_mintage(
        db_session, country_id=country.id, mintage=cells, dry_run=False
    )
    await db_session.commit()

    assert (await db_session.get(CatalogItem, old_pattern.id)).mintage_actual == 20_000  # type: ignore[union-attr]
    assert (await db_session.get(CatalogItem, new_pattern.id)).mintage_actual == 140_000_000  # type: ignore[union-attr]
    assert (await db_session.get(CatalogItem, no_subtype.id)).mintage_actual is None  # type: ignore[union-attr]
    assert any(row["itemId"] == no_subtype.id for row in outcome.ambiguous)


# -------------------------------------------------------------------- circ_photos
@pytest.fixture
def obig_client(tmp_path: Path) -> PoliteClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/ua/uah/obig-coin/"):
            return httpx.Response(
                200,
                text=obig_page_html(("1 копійка", "Вилучена з обігу", "02.09.1996")),
            )
        if "admin_uploads" in request.url.path:
            return httpx.Response(200, content=png_bytes(400))
        return httpx.Response(404)

    return PoliteClient(
        cache_dir=tmp_path / "cache",
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
    )


class RecordingStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, key: str, payload: bytes, content_type: str) -> None:
        self.objects[key] = payload

    def ensure_bucket(self) -> None:
        return None


async def test_photos_are_stored_once_per_item_of_a_type(
    db_session: AsyncSession, obig_client: PoliteClient
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(1), unit="kopiika", sort_order=1
    )
    db_session.add(denomination)
    await db_session.commit()
    first = await make_catalog_item(
        db_session,
        country=country,
        title="1 копійка",
        year=1992,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )
    second = await make_catalog_item(
        db_session,
        country=country,
        title="1 копійка",
        year=1996,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )
    storage = RecordingStorage()

    outcome = await circ_photos.download_photos(
        db_session,
        client=obig_client,
        storage=storage,
        country_id=country.id,  # type: ignore[arg-type]
        dry_run=False,
        limit=None,
        log=lambda _msg: None,
    )
    await db_session.commit()

    assert outcome.stored == 4  # two sides, two items
    assert outcome.items_touched == 2
    files = (
        (
            await db_session.execute(
                select(MediaFile).where(MediaFile.catalog_item_id.in_([first.id, second.id]))
            )
        )
        .scalars()
        .all()
    )
    assert {f.catalog_item_id for f in files} == {first.id, second.id}
    assert all(f.source is MediaSource.NBU for f in files)
    assert len(storage.objects) > 0


async def test_photos_are_not_downloaded_twice(
    db_session: AsyncSession, obig_client: PoliteClient
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(1), unit="kopiika", sort_order=1
    )
    db_session.add(denomination)
    await db_session.commit()
    await make_catalog_item(
        db_session,
        country=country,
        title="1 копійка",
        year=1992,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )
    storage = RecordingStorage()

    await circ_photos.download_photos(
        db_session,
        client=obig_client,
        storage=storage,
        country_id=country.id,  # type: ignore[arg-type]
        dry_run=False,
        limit=None,
        log=lambda _msg: None,
    )
    await db_session.commit()
    second = await circ_photos.download_photos(
        db_session,
        client=obig_client,
        storage=storage,
        country_id=country.id,  # type: ignore[arg-type]
        dry_run=False,
        limit=None,
        log=lambda _msg: None,
    )
    await db_session.commit()

    assert second.stored == 0
    assert second.already_stored == 1


# --------------------------------------------------------------- circ_reclassify
async def test_reclassify_moves_a_nbu_linked_jubilee_and_the_belt_holds_before_it_runs(
    db_session: AsyncSession,
) -> None:
    """The main scenario: a jubilee 1-hryvnia the legacy import misfiled as
    circulation (docs/04-business-rules.md, rule 11), already linked to the
    NBU numismatic catalogue and carrying an official name.

    Every other circ-* step is exercised first, while the jubilee is still
    sitting in `circulation` — proving the belt holds even if circ-reclassify
    were skipped in a partial `--steps` run — before circ-reclassify itself
    moves it out.
    """
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(1), unit="hryvnia", sort_order=100
    )
    db_session.add(denomination)
    await db_session.commit()
    jubilee = await make_catalog_item(
        db_session,
        country=country,
        title="Помаранчева революція",
        year=2004,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
        source_key="nbu:123",
        title_uk="Помаранчева революція",
        title_uk_source=TranslationSource.OFFICIAL,
    )
    cells = parse_mintage_table(MINTAGE_TABLE_HTML)

    # circ-titles leaves it alone.
    titles_outcome = await circ_titles.apply_titles(
        db_session, country_id=country.id, dry_run=False
    )
    await db_session.commit()
    assert titles_outcome.summary()["skippedNbuLinked"] == 1
    refreshed = await db_session.get(CatalogItem, jubilee.id)
    assert refreshed is not None and refreshed.title_uk == "Помаранчева революція"

    # circ-mintage leaves it alone (a 2004 hryvnia cell now exists and would
    # otherwise fill mintage_actual on the jubilee).
    mintage_outcome = await circ_mintage.apply_mintage(
        db_session, country_id=country.id, mintage=cells, dry_run=False
    )
    await db_session.commit()
    assert mintage_outcome.summary()["skippedNbuLinked"] == 1
    refreshed = await db_session.get(CatalogItem, jubilee.id)
    assert refreshed is not None and refreshed.mintage_actual is None

    # circ-photos does not offer it to any type.
    by_type, skipped = await circ_photos._items_by_type(db_session, country.id)
    assert skipped == 1
    assert jubilee.id not in {item_id for ids in by_type.values() for item_id in ids}

    # circ-bridge does not try to link it to Wikipedia.
    items = await load_items(db_session, country.id)
    bridge_outcome = circ_bridge.decide(items, cells)
    assert bridge_outcome.summary()["skippedNbuLinked"] == 1
    assert jubilee.id not in {item.id for item in bridge_outcome.linked}
    assert jubilee.id not in {item.id for item in bridge_outcome.without_wikipedia_entry}

    # circ-gaps creates the real 1 hryvnia 2004 despite the jubilee occupying
    # the year in title only, not the slot.
    gaps_outcome = await circ_gaps.create_missing(
        db_session, country_id=country.id, items=items, mintage=cells, dry_run=False
    )
    await db_session.commit()
    assert gaps_outcome.summary()["created"] >= 1
    real_hryvnia_2004 = (
        await db_session.execute(
            select(CatalogItem).where(CatalogItem.source_key == "wiki-circ:1-hryvnia:2004")
        )
    ).scalar_one()
    assert real_hryvnia_2004.id != jubilee.id
    assert real_hryvnia_2004.collection_group is CollectionGroup.CIRCULATION

    # Now circ-reclassify moves the jubilee, and only the jubilee.
    items = await load_items(db_session, country.id)
    reclassify_outcome = await circ_reclassify.apply_reclassify(
        db_session, items=items, dry_run=False
    )
    await db_session.commit()

    assert reclassify_outcome.reclassified == [
        {"itemId": jubilee.id, "title": "Помаранчева революція", "year": 2004}
    ]
    refreshed = await db_session.get(CatalogItem, jubilee.id)
    assert refreshed is not None
    assert refreshed.collection_group is CollectionGroup.COMMEMORATIVE
    assert refreshed.title_uk == "Помаранчева революція"
    assert refreshed.source_key == "nbu:123"


async def test_reclassify_catches_a_price_source_link_without_a_source_key(
    db_session: AsyncSession,
) -> None:
    """A karbovanets commemorative (1995-1996) has no "грив" in its face value
    at all, so groupFor's own logic never had a reason to route it to
    circulation — it is caught here purely by its NBU link.
    """
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    karbovanets = await make_catalog_item(
        db_session,
        country=country,
        title="2 000 000 карбованців",
        year=1995,
        group=CollectionGroup.CIRCULATION,
    )
    db_session.add(
        PriceSourceLink(
            catalog_item_id=karbovanets.id,
            source=LINK_SOURCES[SOURCE_NBU],
            external_id="777",
            match_status=MatchStatus.CONFIRMED,
        )
    )
    await db_session.commit()

    items = await load_items(db_session, country.id)
    outcome = circ_reclassify.decide(items)

    assert [row["itemId"] for row in outcome.reclassified] == [karbovanets.id]


async def test_reclassify_leaves_an_honest_circulation_coin_alone(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    denomination = Denomination(
        country_id=country.id, currency_code="UAH", value=Decimal(25), unit="kopiika", sort_order=25
    )
    db_session.add(denomination)
    await db_session.commit()
    await make_catalog_item(
        db_session,
        country=country,
        title="25 копеек",
        year=1996,
        denomination=denomination,
        group=CollectionGroup.CIRCULATION,
    )
    items = await load_items(db_session, country.id)

    outcome = circ_reclassify.decide(items)

    assert outcome.reclassified == []
    assert outcome.official_without_nbu_link == []

    titles_outcome = await circ_titles.apply_titles(
        db_session, country_id=country.id, dry_run=False
    )
    assert titles_outcome.summary()["skippedNbuLinked"] == 0


async def test_reclassify_reports_but_does_not_move_an_official_title_without_nbu_link(
    db_session: AsyncSession,
) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    item = await make_catalog_item(
        db_session,
        country=country,
        title="1 гривня",
        year=2010,
        group=CollectionGroup.CIRCULATION,
        title_uk="1 гривня",
        title_uk_source=TranslationSource.OFFICIAL,
    )
    items = await load_items(db_session, country.id)

    outcome = circ_reclassify.decide(items)

    assert outcome.reclassified == []
    assert [row["itemId"] for row in outcome.official_without_nbu_link] == [item.id]

    await circ_reclassify.apply_reclassify(db_session, items=items, dry_run=False)
    await db_session.commit()
    refreshed = await db_session.get(CatalogItem, item.id)
    assert refreshed is not None and refreshed.collection_group is CollectionGroup.CIRCULATION


async def test_reclassify_dry_run_writes_nothing(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    jubilee = await make_catalog_item(
        db_session,
        country=country,
        title="Помаранчева революція",
        year=2004,
        group=CollectionGroup.CIRCULATION,
        source_key="nbu:123",
    )
    items = await load_items(db_session, country.id)

    outcome = await circ_reclassify.apply_reclassify(db_session, items=items, dry_run=True)

    assert outcome.summary()["reclassified"] == 1
    refreshed = await db_session.get(CatalogItem, jubilee.id)
    assert refreshed is not None and refreshed.collection_group is CollectionGroup.CIRCULATION


async def test_reclassify_is_idempotent(db_session: AsyncSession) -> None:
    await seed_currencies(db_session)
    country = await country_by_code(db_session, "UA")
    await make_catalog_item(
        db_session,
        country=country,
        title="Помаранчева революція",
        year=2004,
        group=CollectionGroup.CIRCULATION,
        source_key="nbu:123",
    )

    items = await load_items(db_session, country.id)
    first = await circ_reclassify.apply_reclassify(db_session, items=items, dry_run=False)
    await db_session.commit()
    assert first.summary()["reclassified"] == 1

    items = await load_items(db_session, country.id)
    second = await circ_reclassify.apply_reclassify(db_session, items=items, dry_run=False)
    await db_session.commit()
    assert second.summary()["reclassified"] == 0


# -------------------------------------------------------------------------- misc
async def test_ukraine_country_id_is_found(db_session: AsyncSession) -> None:
    country_id = await ukraine_country_id(db_session)
    assert country_id is not None
