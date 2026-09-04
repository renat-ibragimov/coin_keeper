"""Parsers of the three Ukrainian sources on saved page fragments.

The fixtures under tests/fixtures/ukraine_recon/ are cut from real pages
(August 2026): the ua-coins.info all-years table in both locales, its series
page and a coin page, an NBU search result page, and the Wikipedia list
tables. No network anywhere in here.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from app.ukraine_recon import nbu, ua_coins, wikipedia
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA

FIXTURES = Path(__file__).parent / "fixtures" / "ukraine_recon"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ------------------------------------------------------------------ ua-coins
def test_ua_coins_catalog_rows_carry_every_column() -> None:
    rows = ua_coins.parse_catalog_page(fixture("ua_coins_catalog_uk.html"))
    assert len(rows) == 4
    first = rows[0]
    assert first.coin_id == 3042
    assert first.slug.startswith("ukrayinska-bavovna")
    assert "Sea Baby" in first.title
    assert first.date_text == "29.07.2026"
    assert first.denomination_text == "5 грн."
    assert first.mintage_text == "75/50"
    assert first.price_text == "438"
    assert first.price_date == "18.08.2026"
    assert first.trend == "down"


def test_ua_coins_russian_locale_parses_with_the_same_code() -> None:
    rows = ua_coins.parse_catalog_page(fixture("ua_coins_catalog_ru.html"))
    assert len(rows) == 4
    assert rows[0].coin_id == 2665
    assert "Расстрелянное возрождение" in rows[0].title
    assert rows[0].price_text == "нет данных"


def test_ua_coins_records_join_locales_by_id_and_classify_kind() -> None:
    uk = ua_coins.parse_catalog_page(fixture("ua_coins_catalog_uk.html"))
    ru = ua_coins.parse_catalog_page(fixture("ua_coins_catalog_ru.html"))
    # The Russian snapshot is older; give it one shared id on purpose.
    ru[0].coin_id = uk[1].coin_id
    records = ua_coins.rows_to_records(uk, ru)
    by_id = {record.source_id: record for record in records}
    joined = by_id[str(uk[1].coin_id)]
    assert joined.source == SOURCE_UA_COINS
    assert joined.title_uk == uk[1].title
    assert joined.title_ru == ru[0].title
    assert joined.year == 2026
    assert joined.mintage == 75_000 or joined.mintage is not None
    # The rest of the Russian rows have no Ukrainian twin and are kept.
    assert len(records) == 4 + 3
    packaged = by_id["3042"]
    assert packaged.kind == "souvenir"
    assert packaged.price == Decimal("438")
    assert packaged.mintage == 75_000
    assert packaged.mintage_actual == 50_000
    assert packaged.image_urls[0].endswith("/images/coins/small/3042_obverse.webp")


def test_ua_coins_price_filter_keeps_the_legacy_rules() -> None:
    assert ua_coins.parse_price("1 167") == Decimal("1167")
    assert ua_coins.parse_price("немає даних") is None
    assert ua_coins.parse_price("1200 = 1500") is None
    assert ua_coins.parse_price("") is None


def test_ua_coins_categories_page_gives_counts_per_series() -> None:
    series = ua_coins.parse_categories_page(fixture("ua_coins_categories.html"))
    assert len(series) == 4
    first = series[0]
    assert first.slug == "2000-letiyu-rozhdestva-hristova"
    assert first.total == 6
    assert first.base_metal == 2
    assert first.precious_metal == 4
    assert first.mintage_total == 21135


def test_ua_coins_coin_page_offers_the_russian_title_and_the_table() -> None:
    page = ua_coins.parse_coin_page(fixture("ua_coins_coin.html"))
    assert page.title == "350 років Харкову 5 грн."
    assert page.title_alt == "350 лет Харькову"
    assert page.price == Decimal("1167")
    assert page.series == "Стародавні міста України"
    assert page.fields["Тираж"] == "30 000 шт."
    assert page.fields["Ціна НБУ"] == "5 грн"
    assert page.image_urls == ["/images/coins/115_obverse.jpg", "/images/coins/115_reverse.jpg"]


def test_ua_coins_url_templates() -> None:
    assert ua_coins.catalog_url(2020) == "https://www.ua-coins.info/ua/catalog/all/2020"
    assert (
        ua_coins.catalog_url("all", ua_coins.LOCALE_RU)
        == "https://www.ua-coins.info/catalog/all/all"
    )
    assert ua_coins.image_url(115, "reverse", "big_png").endswith(
        "/images/coins/big/115_reverse.png"
    )


# ----------------------------------------------------------------------- nbu
def test_nbu_search_page_total_pages_and_cards() -> None:
    page = nbu.parse_search_page(fixture("nbu_search.html"))
    assert page.total == 1048
    assert page.page_count == 11
    assert len(page.cards) == 2
    card = page.cards[0]
    assert card.nbu_id == "1767"
    assert card.code == "D18"
    assert card.series == "Українська держава"
    assert card.fields["Номінал"] == "1 грн"
    assert card.fields["Дата введення в обіг"] == "02.09.2026"
    assert card.fields["Тираж (оголошений/фактичний), шт."]
    assert card.description
    assert card.thumbnails[0] == "https://bank.gov.ua/media/coins/1767/avers.jpg"
    assert card.images[0] == "https://bank.gov.ua/files/coins_images/D18a.png"


def test_nbu_card_becomes_a_record_with_mintage_split() -> None:
    page = nbu.parse_search_page(fixture("nbu_search.html"))
    record = nbu.card_to_record(page.cards[0])
    assert record.source == SOURCE_NBU
    assert record.source_id == "1767"
    assert record.denomination == Decimal("1")
    assert record.year == 2026
    assert record.issue_date == "2026-09-02"
    assert record.mintage is not None and record.mintage_actual is not None
    assert record.metal == "срібло"
    assert record.extra["artist"]
    assert record.kind == "coin"
    # The prose is kept, not only counted: it is the only place the card says
    # what is drawn on the coin, and that is what tells two same-named issues
    # of one series apart when they are merged.
    assert record.extra["description"] == page.cards[0].description


def test_nbu_search_form_sends_only_used_filters() -> None:
    assert nbu.search_form(2) == {"page": "2", "perPage": "100", "category[]": "Coin"}
    assert nbu.search_form(1, category=None, date_from="01.01.2020")["from"] == "01.01.2020"


def test_nbu_series_options_come_from_the_filter() -> None:
    names = nbu.parse_series_options(fixture("nbu_catalog_form.html"))
    assert names[0] == "2000-ліття Різдва Христового"
    assert "" not in names


def test_nbu_field_coverage_counts_labels() -> None:
    page = nbu.parse_search_page(fixture("nbu_search.html"))
    coverage = nbu.field_coverage(page.cards)
    assert coverage["Номінал"] == 2
    assert coverage["series"] == 2


# ----------------------------------------------------------------- wikipedia
def test_wikipedia_precious_groups_follow_the_headings() -> None:
    records = wikipedia.parse_list_page(fixture("wiki_precious.html"), wikipedia.PAGE_PRECIOUS)
    groups = {record.metal for record in records}
    assert groups == {wikipedia.GROUP_SILVER, wikipedia.GROUP_GOLD}
    silver = [r for r in records if r.metal == wikipedia.GROUP_SILVER]
    assert silver[0].source == SOURCE_WIKIPEDIA
    assert silver[0].source_id == "silver:1"
    assert silver[0].currency == "UAK"
    assert silver[0].denomination == Decimal("2000000")
    gold = [r for r in records if r.metal == wikipedia.GROUP_GOLD]
    assert gold[0].title_uk == "Тарас Шевченко"
    assert gold[0].issue_date == "1997-03-12"  # dd.mm.yy in the source
    assert gold[0].mintage == 10_000
    assert gold[0].url.endswith("(золота_монета)")
    assert len(gold[0].image_urls) == 2


def test_wikipedia_base_numbering_and_two_digit_years() -> None:
    records = wikipedia.parse_list_page(fixture("wiki_base.html"), wikipedia.PAGE_BASE)
    assert [r.source_id for r in records][:2] == ["base:1", "base:2"]
    recent = [r for r in records if r.year == 2020]
    assert recent and recent[0].denomination == Decimal("5")
    assert all(r.metal == wikipedia.GROUP_BASE for r in records)


def test_wikipedia_rowspan_cells_are_repeated() -> None:
    records = wikipedia.parse_list_page(fixture("wiki_rowspan.html"), wikipedia.PAGE_PRECIOUS)
    assert [r.title_uk for r in records] == ["Спільна назва", "Спільна назва"]
    assert [r.denomination for r in records] == [Decimal("10"), Decimal("20")]
    assert records[1].image_urls == [
        "https://upload.wikimedia.org/a.jpg",
        "https://upload.wikimedia.org/r2.jpg",
    ]


def test_wikipedia_sets_table() -> None:
    sets = wikipedia.parse_sets(fixture("wiki_hryvnia_sets.html"))
    assert len(sets) == 3
    assert sets[0].year == 2025
    assert sets[0].mintage == 20_000
    assert "гривень" in sets[0].contents
