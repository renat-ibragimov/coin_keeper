"""Normalisation, the matching strategies and the year table (app/ukraine_recon)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.ukraine_recon import triangulate
from app.ukraine_recon.catalog import CatalogEntry, SeriesEntry
from app.ukraine_recon.models import SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA, SourceRecord
from app.ukraine_recon.normalize import (
    bare_title,
    classify_kind,
    denomination_value,
    match_key,
    normalize_title,
    parse_date,
    parse_mintage,
    strip_source_suffix,
    titles_equivalent,
)
from app.ukraine_recon.ua_coins import SeriesCount


# --------------------------------------------------------------- normalise
def test_normalize_title_follows_the_integration_doc() -> None:
    assert normalize_title('"Ігри ХХХ Олімпіади" (Лондон)') == "ігри ххх олімпіади лондон"
    assert normalize_title("Кожум’яка, — Кирило!") == "кожум яка кирило"


def test_normalize_title_repairs_latin_letters_inside_cyrillic_words() -> None:
    assert normalize_title("Перемога у ВВВ 1941-1945 рокiв") == normalize_title(
        "рокiв".replace("i", "і")
    ) or (normalize_title("рокiв") == "років")
    assert normalize_title("80 років проголошення незалежності УHР") == normalize_title(
        "80 років проголошення незалежності УНР"
    )


def test_source_suffix_and_packaging_are_stripped() -> None:
    assert strip_source_suffix("Українська мова (c)") == "Українська мова"
    assert strip_source_suffix("Оранта (125)") == "Оранта (125)"
    assert bare_title("Українська мова у сувенірному пакованні (н)") == "Українська мова"
    assert bare_title("Захисниці у сувенірній упаковці") == "Захисниці"
    assert bare_title("Родившийся в Украине в сувенирной упаковке") == "Родившийся в Украине"


def test_titles_equivalent_prefix_rule() -> None:
    assert titles_equivalent("десятинна церква", "десятинна церква 1996")
    assert not titles_equivalent("десятинна церква", "десятинна церква1996")
    assert not titles_equivalent("", "x")


def test_denomination_mintage_and_dates() -> None:
    assert denomination_value("5 грн.") == Decimal("5")
    assert denomination_value("58,5 грн") == Decimal("58.5")
    assert denomination_value("") is None
    assert parse_mintage("75/50", thousands=True) == (75_000, 50_000)
    assert parse_mintage("2500/2500") == (2500, 2500)
    assert parse_mintage("30 000 шт.") == (30_000, None)
    assert parse_date("26.11.96") == date(1996, 11, 26)
    assert parse_date("16.01.20") == date(2020, 1, 16)
    assert parse_date("02.09.2026") == date(2026, 9, 2)
    assert parse_date("31.02.2020") is None


def test_match_key_and_kind() -> None:
    assert match_key(Decimal("5.0"), 2004, "350 років Харкову") == "5|2004|350 років харкову"
    assert classify_kind("Набір із двох монет у футлярі") == "set"
    assert classify_kind("Рік Дракона у сувенірному пакованні") == "souvenir"
    assert classify_kind("Рік Дракона") == "coin"


# ---------------------------------------------------------------- fixtures
def record(
    source: str,
    source_id: str,
    title: str,
    denomination: str,
    year: int,
    *,
    title_ru: str | None = None,
    kind: str = "coin",
    price: str | None = None,
) -> SourceRecord:
    return SourceRecord(
        source=source,
        source_id=source_id,
        title_uk=title,
        title_ru=title_ru,
        denomination=Decimal(denomination),
        year=year,
        url=f"https://example.test/{source}/{source_id}",
        kind=kind,
        price=Decimal(price) if price else None,
    )


def item(
    item_id: int,
    title: str,
    denomination: str,
    year: int,
    *,
    source_url: str | None = None,
    price: str | None = None,
) -> CatalogEntry:
    return CatalogEntry(
        id=item_id,
        title_original=title,
        title_uk=None,
        title_ru=None,
        title_en=None,
        denomination_label=f"{denomination} гривень",
        denomination=Decimal(denomination),
        issue_year=year,
        issue_date=None,
        collection_group="commemorative",
        series_id=None,
        series_name=None,
        source_url=source_url,
        source_key=None,
        source_links=[],
        catalog_km=None,
        catalog_uc=None,
        catalog_numista=None,
        mintage=None,
        material=None,
        has_photo=False,
        photo_sources=[],
        is_archived=False,
        last_price=Decimal(price) if price else None,
        last_price_source="ucoin" if price else None,
        last_price_at=None,
        last_price_suspect=False if price else None,
    )


def sources() -> dict[str, list[SourceRecord]]:
    return {
        SOURCE_NBU: [
            record(SOURCE_NBU, "n1", "Десятинна церква (c)", "20", 1996),
            record(SOURCE_NBU, "n2", "Петро Могила (c)", "10", 1996),
            record(
                SOURCE_NBU,
                "n3",
                "Рік Дракона у сувенірному пакованні (н)",
                "5",
                2023,
                kind="souvenir",
            ),
            record(SOURCE_NBU, "n4", "Ігри ХХХ Олімпіади (c)", "10", 2012),
        ],
        SOURCE_UA_COINS: [
            record(
                SOURCE_UA_COINS,
                "10",
                "Десятинна церква",
                "20",
                1996,
                title_ru="Десятинная церковь",
                price="900",
            ),
            record(
                SOURCE_UA_COINS,
                "11",
                "Петро Могила",
                "10",
                1996,
                title_ru="Петр Могила",
                price="400",
            ),
            record(
                SOURCE_UA_COINS, "12", "Рік Дракона", "5", 2023, title_ru="Год Дракона", price="80"
            ),
            record(
                SOURCE_UA_COINS,
                "13",
                "Рік Дракона у сувенірному пакованні",
                "5",
                2023,
                title_ru="Год Дракона в сувенирной упаковке",
                kind="souvenir",
            ),
            record(
                SOURCE_UA_COINS,
                "14",
                "Ігри ХХХ Олімпіади",
                "10",
                2012,
                title_ru="Игры ХХХ Олимпиады",
                price="1500",
            ),
            record(SOURCE_UA_COINS, "15", "Козак Мамай", "20", 1997, title_ru="Казак Мамай"),
        ],
        SOURCE_WIKIPEDIA: [
            record(SOURCE_WIKIPEDIA, "silver:10", "Десятинна церква", "20", 1996),
            record(SOURCE_WIKIPEDIA, "silver:11", "Петро Могила", "10", 1996),
            record(SOURCE_WIKIPEDIA, "base:500", "Рік Дракона", "5", 2023),
            record(SOURCE_WIKIPEDIA, "silver:200", "Ігри ХХХ Олімпіади в Лондоні", "10", 2012),
            record(SOURCE_WIKIPEDIA, "silver:20", "Козак Мамай", "20", 1997),
        ],
    }


# ---------------------------------------------------------------- matching
def test_strategies_apply_in_order_and_count_once() -> None:
    items = [
        item(
            1,
            "Десятинная церковь",
            "20",
            1996,
            source_url="https://www.ua-coins.info/ua/list/10-x",
            price="1000",
        ),
        item(2, "Петр Могила", "10", 1996),
        item(3, "Игры ХХХ Олимпиады (Лондон)", "10", 2012),
        item(4, "Рік Дракона", "5", 2024),
        item(5, "Щось зовсім інше", "2", 2001),
    ]
    result = triangulate.match_catalog(items, sources())
    by = {(m.item_id, m.source): m for m in result.matches}
    # A wins over B for ua-coins even though B would also hit.
    assert by[(1, SOURCE_UA_COINS)].strategy == "A"
    assert by[(1, SOURCE_WIKIPEDIA)].strategy == "C"  # ru vs uk title, fuzzy
    assert by[(2, SOURCE_UA_COINS)].strategy == "B"  # exact via the Russian title
    assert by[(3, SOURCE_UA_COINS)].strategy == "B"  # the prefix rule
    assert by[(4, SOURCE_UA_COINS)].strategy == "C1"  # year off by one
    assert by[(4, SOURCE_UA_COINS)].source_id == "12"  # the coin, not its packaging
    assert (5, SOURCE_UA_COINS) not in by
    counts = result.counts()
    assert sum(counts[SOURCE_UA_COINS].values()) == 4
    assert counts[SOURCE_UA_COINS]["D"] == 0
    assert len({(m.item_id, m.source) for m in result.matches}) == len(result.matches)
    unmatched = triangulate.unmatched_items(items, result)
    assert [u["id"] for u in unmatched] == [5]


def test_conflicts_are_reported_not_silently_resolved() -> None:
    items = [
        item(1, "Петр Могила", "10", 1996),
        item(2, "Петр Могила", "10", 1996),
    ]
    result = triangulate.match_catalog(items, sources())
    assert len(result.many_to_one) >= 1
    assert result.many_to_one[0]["sourceId"] in {"11", "n2", "silver:11"}


def test_packaged_only_rows_become_coins_when_no_bare_twin_exists() -> None:
    data = sources()
    promoted = triangulate.promote_packaged_coins(data[SOURCE_NBU])
    assert promoted == 1
    assert data[SOURCE_NBU][2].kind == "coin"
    assert data[SOURCE_NBU][2].extra["packagedOnly"] is True
    # ua-coins lists the bare coin too, so its packaged row stays a souvenir.
    assert triangulate.promote_packaged_coins(data[SOURCE_UA_COINS]) == 0


def test_clusters_and_year_table() -> None:
    data = sources()
    triangulate.promote_packaged_coins(data[SOURCE_NBU])
    clusters = triangulate.cluster_records(data)
    titles = {c.title: c.sources for c in clusters if c.kind == "coin"}
    assert titles["Десятинна церква"] == {SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA}
    assert titles["Ігри ХХХ Олімпіади"] == {SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA}
    assert titles["Козак Мамай"] == {SOURCE_UA_COINS, SOURCE_WIKIPEDIA}
    table = triangulate.build_year_table(data, clusters, [item(1, "Казак Мамай", "20", 1997)])
    rows = {row["year"]: row for row in table}
    assert (
        rows[1996][SOURCE_NBU] == rows[1996][SOURCE_UA_COINS] == rows[1996][SOURCE_WIKIPEDIA] == 2
    )
    assert rows[1996]["flag"] == ""
    assert rows[1997][SOURCE_NBU] == 0 and rows[1997]["ours"] == 1
    assert rows[1997]["flag"] == "~"
    assert rows[1997]["disputed"] == ["Козак Мамай [ua_coins, wikipedia]"]
    assert rows[2023][SOURCE_UA_COINS] == 1  # the packaged row is not a second coin


def test_candidates_need_two_sources_and_no_match() -> None:
    data = sources()
    items = [item(1, "Десятинная церковь", "20", 1996)]
    result = triangulate.match_catalog(items, data)
    clusters = triangulate.cluster_records(data)
    candidates = triangulate.candidate_additions(clusters, result)
    names = [c["title"] for c in candidates]
    assert "Десятинна церква" not in names
    assert "Козак Мамай" in names
    assert "Петро Могила" in names


def test_price_comparison_median_and_outliers() -> None:
    data = sources()
    items = [
        item(1, "Десятинная церковь", "20", 1996, price="1000"),
        item(2, "Петр Могила", "10", 1996, price="100"),
    ]
    result = triangulate.match_catalog(items, data)
    prices = triangulate.compare_prices(items, result, data[SOURCE_UA_COINS])
    assert prices["compared"] == 2
    assert prices["offByFactorOf3"] == 1
    assert prices["sample"][0]["ratio"] in (0.9, 4.0)


def test_series_table_uses_the_manual_map() -> None:
    ua = [
        SeriesCount(
            "Outstanding Personalities of Ukraine",
            "vydayuschiesya-lichnosti-ukrainy",
            177,
            146,
            31,
            1,
        )
    ]
    nbu = [record(SOURCE_NBU, f"n{i}", f"Хтось {i}", "2", 2000) for i in range(3)]
    for r in nbu:
        r.series = "Видатні особистості України"
    ours = [
        SeriesEntry(1, "Выдающиеся личности Украины", None, None, 144, 144),
        SeriesEntry(2, "Своя", None, None, 1, 1),
    ]
    table = triangulate.build_series_table(ua, nbu, ours, triangulate.load_series_map())
    row = next(r for r in table["rows"] if r["uaCoinsSlug"] == "vydayuschiesya-lichnosti-ukrainy")
    assert (row["uaCoins"], row["nbu"], row["ours"]) == (177, 3, 144)
    assert row["spread"] == 174
    assert [u["name"] for u in table["unmappedOurs"]] == ["Своя"]


def test_title_differences_are_categorised() -> None:
    data = sources()
    clusters = triangulate.cluster_records(data)
    result = triangulate.match_catalog([], data)
    titles = triangulate.compare_titles(clusters, [], result)
    assert titles["kinds"]["punctuation_or_quotes"] >= 1  # "(c)" suffix only
    assert titles["kinds"].get("prefix", 0) >= 1  # "… в Лондоні"
