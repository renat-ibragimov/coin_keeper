"""Country seed, denomination parsing and material parsing.

Pure data and pure functions, so no database is involved. What is checked is
what migration 0003 depends on: every template the legacy catalogue actually
contains parses, the seed holds no duplicates, and the labels come out in both
locales with the right plural form.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.reference_data.countries import (
    UKRAINE_CODE,
    find_by_code,
    find_by_name,
    load_countries,
)
from app.reference_data.denominations import (
    UNITS,
    DenominationParseError,
    parse_label,
    render_label,
)
from app.reference_data.materials import MATERIAL_CODES, MATERIALS, parse_material


# ------------------------------------------------------------------ countries
def test_seed_has_no_duplicate_codes_or_names() -> None:
    countries = load_countries()
    codes = [country.code for country in countries]
    names = [country.name_original for country in countries]
    assert len(set(codes)) == len(codes)
    assert len(set(names)) == len(names), "name_original is unique in the schema"
    assert len(countries) > 250


def test_ukraine_leads_and_is_the_only_active_one() -> None:
    active = [country for country in load_countries() if country.is_active]
    assert [country.code for country in active] == [UKRAINE_CODE]
    ukraine = find_by_code(UKRAINE_CODE)
    assert ukraine is not None
    assert ukraine.sort_order == 0
    assert (ukraine.name_original, ukraine.name_uk, ukraine.name_en) == (
        "Україна",
        "Україна",
        "Ukraine",
    )


def test_legacy_names_find_their_country() -> None:
    """The three countries in the legacy database, under their stored names."""
    assert find_by_name("Украина") is not None
    assert find_by_name("Украина").code == "UA"  # type: ignore[union-attr]
    assert find_by_name("США").code == "US"  # type: ignore[union-attr]
    assert find_by_name("СССР").code == "SUHH"  # type: ignore[union-attr]
    assert find_by_name("Atlantis") is None


def test_historical_issuers_are_seeded_with_their_own_names() -> None:
    ussr = find_by_code("SUHH")
    assert ussr is not None
    assert (ussr.name_original, ussr.original_lang) == ("СССР", "ru")
    assert (ussr.name_uk, ussr.name_en) == ("СРСР", "Soviet Union")
    austria_hungary = find_by_code("XAUH")
    assert austria_hungary is not None
    assert austria_hungary.name_uk == "Австро-Угорщина"


def test_every_country_carries_all_three_names() -> None:
    for country in load_countries():
        assert country.name_original.strip()
        assert country.name_uk.strip()
        assert country.name_en.strip()
        assert len(country.original_lang) >= 2


# --------------------------------------------------------------- denominations
# Every label the legacy database holds, by country: 52 rows, all templates.
UKRAINIAN_LABELS = (
    ("1 гривна", "1", "hryvnia"),
    ("2 гривны", "2", "hryvnia"),
    ("5 гривен", "5", "hryvnia"),
    ("10 гривен", "10", "hryvnia"),
    ("1000 гривен", "1000", "hryvnia"),
    ("1 копейка", "1", "kopiika"),
    ("50 копеек", "50", "kopiika"),
    ("200.000 карбованцев", "200000", "karbovanets"),
    ("1.000.000 карбованцев", "1000000", "karbovanets"),
    ("2.000.000 карбованцев", "2000000", "karbovanets"),
)
AMERICAN_LABELS = (
    ("1 цент", "1", "cent"),
    ("5 центов", "5", "cent"),
    ("25 центов", "25", "cent"),
    ("1 дайм", "1", "dime"),
    ("1 dime", "1", "dime"),
    ("¼ доллара", "0.25", "dollar"),
    ("¼ dollar", "0.25", "dollar"),
    ("½ доллара", "0.5", "dollar"),
    ("2½ dollars", "2.5", "dollar"),
    ("20 dollars", "20", "dollar"),
)
SOVIET_LABELS = (
    ("½ копейки", "0.5", "kopeck"),
    ("3 копейки", "3", "kopeck"),
    ("15 копеек", "15", "kopeck"),
    ("1 рубль", "1", "ruble"),
    ("5 рублей", "5", "ruble"),
    ("1 полтинник", "1", "poltinnik"),
    ("1 червонец", "1", "chervonets"),
)


@pytest.mark.parametrize(
    ("country", "label", "value", "unit"),
    [("UA", *row) for row in UKRAINIAN_LABELS]
    + [("US", *row) for row in AMERICAN_LABELS]
    + [("SUHH", *row) for row in SOVIET_LABELS],
)
def test_every_legacy_template_parses(country: str, label: str, value: str, unit: str) -> None:
    parsed = parse_label(label, country_code=country)
    assert (parsed.value, parsed.unit) == (Decimal(value), unit)
    assert parsed.currency_code == UNITS[unit].currency_code


def test_the_same_word_means_two_coins_in_two_countries() -> None:
    """Ukrainian копійка and Soviet копейка are spelled alike in the legacy base."""
    assert parse_label("5 копеек", country_code="UA").unit == "kopiika"
    assert parse_label("5 копеек", country_code="SUHH").unit == "kopeck"
    assert parse_label("5 копеек", country_code="UA").currency_code == "UAH"
    assert parse_label("5 копеек", country_code="SUHH").currency_code == "SUR"


def test_sort_order_puts_the_smaller_coin_first() -> None:
    kopiika = parse_label("50 копеек", country_code="UA")
    hryvnia = parse_label("1 гривна", country_code="UA")
    assert kopiika.minor_units < hryvnia.minor_units


@pytest.mark.parametrize("label", ["", "гривень", "5 талерів", "0 гривень", "5.5 гривень"])
def test_an_unreadable_label_is_an_error_not_a_guess(label: str) -> None:
    with pytest.raises(DenominationParseError):
        parse_label(label, country_code="UA")


@pytest.mark.parametrize(
    ("value", "unit", "uk", "en"),
    [
        ("1", "hryvnia", "1 гривня", "1 hryvnia"),
        ("2", "hryvnia", "2 гривні", "2 hryvnias"),
        ("5", "hryvnia", "5 гривень", "5 hryvnias"),
        ("11", "hryvnia", "11 гривень", "11 hryvnias"),
        ("21", "hryvnia", "21 гривня", "21 hryvnias"),
        ("1000", "hryvnia", "1 000 гривень", "1,000 hryvnias"),
        ("2000000", "karbovanets", "2 000 000 карбованців", "2,000,000 karbovantsi"),
        ("0.25", "dollar", "¼ долара", "¼ dollars"),
        ("2.5", "dollar", "2½ долара", "2½ dollars"),
        ("3", "ruble", "3 рублі", "3 rubles"),
    ],
)
def test_label_is_rendered_per_locale(value: str, unit: str, uk: str, en: str) -> None:
    assert render_label(Decimal(value), unit, "uk") == uk
    assert render_label(Decimal(value), unit, "en") == en


# -------------------------------------------------------------------- material
@pytest.mark.parametrize(
    ("text", "code", "mass", "diameter"),
    [
        ("Цинк с медным покрытием, 2.5g, ø 19mm", "copper_plated_zinc", "2.5", "19"),
        ("Медь-Цинк-Никель", "nickel_silver", None, None),
        ("Нейзильбер", "nickel_silver", None, None),
        ("Silver 0.900", "silver_900", None, None),
        ("AgСеребро 0.925", "silver_925", None, None),
        ("AgСеребро с золотым покрытием 0.999", "silver_gilded_999", None, None),
        ("AuЗолото 1.000", "gold_1000", None, None),
        ("Copper-Nickel plated Copper", "copper_nickel_plated_copper", None, None),
        (
            "Медь с медно-никелевым покрытием, 5.67g, ø 24.26mm",
            "copper_nickel_plated_copper",
            "5.67",
            "24.26",
        ),
        ("Zinc plated Steel", "zinc_plated_steel", None, None),
        ("10 гривен, 2023 Звонок - Концерт AgСеребро 0.999, 31.1g", "silver_999", "31.1", None),
    ],
)
def test_material_is_read_from_the_end_of_the_string(
    text: str, code: str, mass: str | None, diameter: str | None
) -> None:
    """The uCoin importer glued the coin heading in front of the material."""
    parsed = parse_material(text)
    assert parsed.composition == code
    assert parsed.weight_grams == (None if mass is None else Decimal(mass))
    assert parsed.diameter_mm == (None if diameter is None else Decimal(diameter))


def test_a_longer_phrase_wins_over_a_shorter_one() -> None:
    assert parse_material("Copper-Nickel plated Copper").composition != "copper"
    assert parse_material("Copper").composition == "copper"


@pytest.mark.parametrize("text", [None, "", "   ", "Unobtainium"])
def test_an_unknown_material_stays_unrecognised(text: str | None) -> None:
    assert parse_material(text).composition is None


def test_the_dictionary_is_consistent() -> None:
    codes = [material.code for material in MATERIALS]
    assert len(set(codes)) == len(codes)
    assert set(codes) == set(MATERIAL_CODES)
    for material in MATERIALS:
        assert material.name_uk.strip() and material.name_en.strip()
