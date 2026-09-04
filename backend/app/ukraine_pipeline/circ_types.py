"""The circulation coin type map: denomination + year -> design, material, photo.

A catalogue record is "denomination + year"; a coin's look and composition live
in ranges of years, not in the record. This module is the explicit table the
handoff asked for rather than a guess: every entry below is read off the
National Bank's own "Про монети" page (bank.gov.ua/ua/uah/obig-coin), which
gives each design its own "Дата введення в обіг", material, mass, diameter and
an explicit "Роки карбування" year list — verified against the Wikipedia
mintage table (docs/05-integrations.md, circulation section) rather than
assumed.

Granularity is deliberately coarse. The National Bank's own page goes further
than this: 10 and 50 kopecks each went through two or three alloy changes
under the same coin, with cards giving each its own material and, for 50
kopecks, overlapping years across mints (both a Luhansk-struck and an
Italian-struck 1992 kopeck exist). That is mint-and-alloy variety, exactly
what docs/04-business-rules.md defers to `catalog_variants` and this task
explicitly excludes ("«англійський тип» 1992 и прочие разновідності карбування
— НЕ здесь"). One type per denomination is kept here except where the National
Bank itself gives a coin a second, non-overlapping "Дата введення в обіг": the
2013 restrike of 50 kopecks and, above all, the 2018 hryvnia — the one
overlap this table cannot flatten away, because the handoff asks for it by
name ("зразок 1992/1995-2018 и зразок 2018").

Two coin sources use these types differently:

* photos reads `photo_slug` and `photo_title_hint`, fetches the "Про монети"
  page once per denomination and picks the one card among the (possibly
  several) stacked on it that this type means — see
  app/ukraine_pipeline/circ_nbu.py;
* gaps and mintage only need `composition_code`, `metal_kind`, the physical
  dimensions and the year range; they never touch the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.models.enums import MetalKind

KOPIIKA = "kopiika"
HRYVNIA = "hryvnia"

# The two subtype labels the handoff itself names. Nothing else in the map
# carries a subtype: 2018 is the only year two of our types could both claim,
# and that is exactly why the field exists.
SUBTYPE_1992 = "зразка 1992 року"
SUBTYPE_2018 = "зразка 2018 року"


@dataclass(frozen=True, slots=True)
class CoinType:
    key: str
    unit: str
    value: Decimal
    year_from: int
    # None = still minted; open-ended on purpose rather than guessing a
    # closing year the National Bank has not announced.
    year_to: int | None
    subtype: str | None
    composition_code: str | None
    metal_kind: MetalKind
    weight_grams: Decimal
    diameter_mm: Decimal
    thickness_mm: Decimal | None
    edge: str | None
    # Where to read the photograph: the "Про монети" page for this
    # denomination, and — only where that page stacks more than one design
    # under the same denomination — a substring that picks this type's card
    # out of the others (see app/ukraine_pipeline/circ_nbu.py:pick_card).
    photo_slug: str
    photo_title_hint: str | None = None


# year_to for the kopecks is the last year the Wikipedia mintage table
# (app/ukraine_recon/wikipedia.py:parse_mintage_table) actually reports a
# mintage for, not the shorter "Роки карбування" list the "Про монети" page
# gives — that page tracks circulation years only, and several of these later
# years minted collector-set pieces the mintage table still counts as real,
# dated coins (docs/05-integrations.md).
# fmt: off
TYPES: tuple[CoinType, ...] = (
    CoinType(
        "kopiika_1", KOPIIKA, Decimal(1), 1992, 2018, None,
        "stainless_steel", MetalKind.BASE,
        Decimal("1.5"), Decimal("16"), Decimal("1.2"), "гладкий",
        "1_1996",
    ),
    CoinType(
        "kopiika_2", KOPIIKA, Decimal(2), 1992, 2018, None,
        "stainless_steel", MetalKind.BASE,
        Decimal("1.8"), Decimal("17.3"), Decimal("1.2"), "гладкий",
        "2_1996",
    ),
    CoinType(
        "kopiika_5", KOPIIKA, Decimal(5), 1992, 2018, None,
        "stainless_steel", MetalKind.BASE,
        Decimal("4.3"), Decimal("24"), Decimal("1.5"), "рифлений",
        "5_1996",
    ),
    CoinType(
        # The National Bank stacks three alloys under this denomination (1992
        # Italian brass, 1996 Luhansk aluminium bronze, 2014 brass-plated
        # steel); the representative photo is the current one, which is what
        # circ_nbu.pick_card returns without a title hint (the first card).
        "kopiika_10", KOPIIKA, Decimal(10), 1992, 2022, None,
        "brass_plated_steel", MetalKind.BASE,
        Decimal("1.7"), Decimal("16.3"), Decimal("1.25"), "рифлений",
        "10_1992",
    ),
    CoinType(
        "kopiika_25", KOPIIKA, Decimal(25), 1992, 2018, None,
        "brass_plated_steel", MetalKind.BASE,
        Decimal("2.9"), Decimal("20.8"), Decimal("1.35"), "секторальне рифлення",
        "25_1996",
    ),
    CoinType(
        "kopiika_50", KOPIIKA, Decimal(50), 1992, None, None,
        "brass_plated_steel", MetalKind.BASE,
        Decimal("4.2"), Decimal("23"), Decimal("1.55"), "секторальне рифлення",
        "50_2013",
    ),
    CoinType(
        # 1992/1995 in the handoff's own words: coins carrying 1992 exist
        # (Italian mint) alongside the 1995 aluminium-bronze card the National
        # Bank keeps a "Дата введення в обіг" for (12.03.1997). year_to stops
        # at 2017, one year short of the 2018 pattern change, so this type and
        # hryvnia_1_2018 below never claim the same year.
        "hryvnia_1_1992", HRYVNIA, Decimal(1), 1992, 2017, SUBTYPE_1992,
        "aluminium_bronze", MetalKind.BASE,
        Decimal("7.1"), Decimal("26"), Decimal("1.85"), "напис",
        "100_1996", "1 гривня",
    ),
    CoinType(
        "hryvnia_1_2018", HRYVNIA, Decimal(1), 2018, None, SUBTYPE_2018,
        "nickel_plated_steel", MetalKind.BASE,
        Decimal("3.3"), Decimal("18.9"), Decimal("1.7"), "рифлений",
        "1-grivnya-zrazka-2018-roku", "1 гривня зразка 2018 року",
    ),
    CoinType(
        "hryvnia_2_2018", HRYVNIA, Decimal(2), 2018, None, SUBTYPE_2018,
        "nickel_plated_steel", MetalKind.BASE,
        Decimal("4"), Decimal("20.2"), Decimal("1.8"), "рифлений",
        "2-grivni-zrazka-2018-roku", "2 гривні зразка 2018 року",
    ),
    CoinType(
        "hryvnia_5_2018", HRYVNIA, Decimal(5), 2018, None, SUBTYPE_2018,
        "nickel_plated_zinc", MetalKind.BASE,
        Decimal("5.2"), Decimal("22.1"), Decimal("2.1"), "напис",
        "5-grivni-zrazka-2018-roku", "5 гривень зразка 2018 року",
    ),
    CoinType(
        "hryvnia_10_2018", HRYVNIA, Decimal(10), 2018, None, SUBTYPE_2018,
        "nickel_plated_zinc", MetalKind.BASE,
        Decimal("6.4"), Decimal("23.5"), Decimal("2.3"), "рифлений",
        "10-grivni-zrazka-2018-roku", "10 гривень зразка 2018 року",
    ),
)
# fmt: on

BY_KEY: dict[str, CoinType] = {coin_type.key: coin_type for coin_type in TYPES}


def type_for(value: Decimal, unit: str, year: int) -> CoinType | None:
    """The one type a (denomination, year) belongs to, or None outside all of them.

    At most one type ever matches: the ranges above do not overlap (that is
    what the 2017/2018 split on the hryvnia is for), so this never has to
    choose between two candidates.
    """
    for coin_type in TYPES:
        if coin_type.unit != unit or coin_type.value != value:
            continue
        if year < coin_type.year_from:
            continue
        if coin_type.year_to is not None and year > coin_type.year_to:
            continue
        return coin_type
    return None


def denominations() -> tuple[tuple[Decimal, str], ...]:
    """Every (value, unit) pair the map knows, in table order, deduplicated."""
    seen: list[tuple[Decimal, str]] = []
    for coin_type in TYPES:
        pair = (coin_type.value, coin_type.unit)
        if pair not in seen:
            seen.append(pair)
    return tuple(seen)


def photo_pages() -> dict[str, list[CoinType]]:
    """Types grouped by the "Про монети" page that carries their photo.

    Several types can share one page — the National Bank stacks a
    denomination's whole history under one slug — so photos fetches each page
    once and serves every type that reads from it.
    """
    pages: dict[str, list[CoinType]] = {}
    for coin_type in TYPES:
        pages.setdefault(coin_type.photo_slug, []).append(coin_type)
    return pages
