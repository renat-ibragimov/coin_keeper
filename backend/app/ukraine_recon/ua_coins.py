"""ua-coins.info: the catalogue table, the series page, a coin page.

What the reconnaissance established (docs/05-integrations.md):

* `/ua/catalog/all/{year}` is one table per year; `/ua/catalog/all/all` is the
  same table for every year at once, one request instead of thirty.
* The Russian locale has no prefix: `/catalog/all/all`. Same ids, Russian
  titles — which is what our catalogue holds in `title_original`.
* Rows carry date, denomination, mintage in thousands (announced/actual),
  the title linking to `/ua/list/{id}-{slug}`, and the price of the day.
  Neither series nor metal is in the table; both are on the coin page.
* `/en/categories/all` and `/ua/categories/all` list every series with its
  coin counts: all, base metal, precious metal, and total mintage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from selectolax.parser import HTMLParser, Node

from app.ukraine_recon.models import SOURCE_UA_COINS, SourceRecord
from app.ukraine_recon.normalize import (
    classify_kind,
    denomination_currency,
    denomination_value,
    parse_date,
    parse_int,
    parse_mintage,
)

BASE_URL = "https://www.ua-coins.info"
LOCALE_UK = "ua"
LOCALE_RU = ""  # the Russian locale is the bare path
LOCALE_EN = "en"

_LIST_HREF_RE = re.compile(r"/list/(\d+)-([^/?#\s]*)")
_PRICE_HEADER_RE = re.compile(r"(\d{2}\.\d{2}\.\d{4})")
_NO_DATA = ("немає даних", "нет данных", "no data")

# Column names by locale, as they appear in data-title attributes.
_COLUMNS = {
    "date": ("Дата", "Date"),
    "denomination": ("Номінал", "Номинал", "Denomination", "Face value"),
    "mintage": ("Тираж тис.", "Тираж тыс.", "Mintage ths."),
    "title": ("Назва", "Название", "Name", "Title"),
}

IMAGE_VARIANTS: dict[str, str] = {
    # Older, always present in the archive: JPEG of a few kilobytes.
    "legacy_jpg": "/images/coins/{id}_{side}.jpg",
    "small_webp": "/images/coins/small/{id}_{side}.webp",
    "middle_webp": "/images/coins/middle/{id}_{side}.webp",
    "big_webp": "/images/coins/big/{id}_{side}.webp",
    "big_png": "/images/coins/big/{id}_{side}.png",
}


def catalog_url(year: int | str, locale: str = LOCALE_UK) -> str:
    prefix = f"/{locale}" if locale else ""
    return f"{BASE_URL}{prefix}/catalog/all/{year}"


def categories_url(locale: str = LOCALE_EN) -> str:
    prefix = f"/{locale}" if locale else ""
    return f"{BASE_URL}{prefix}/categories/all"


def plan_url(locale: str = LOCALE_UK) -> str:
    prefix = f"/{locale}" if locale else ""
    return f"{BASE_URL}{prefix}/nbu-plan-list"


def coin_url(coin_id: int, slug: str, locale: str = LOCALE_UK) -> str:
    prefix = f"/{locale}" if locale else ""
    return f"{BASE_URL}{prefix}/list/{coin_id}-{slug}"


def image_url(coin_id: int, side: str, variant: str) -> str:
    return BASE_URL + IMAGE_VARIANTS[variant].format(id=coin_id, side=side)


@dataclass
class CatalogRow:
    coin_id: int
    slug: str
    title: str
    date_text: str
    denomination_text: str
    mintage_text: str
    price_text: str
    price_date: str | None
    trend: str | None


def _cell_text(node: Node) -> str:
    return re.sub(r"\s+", " ", node.text(separator=" ", strip=True)).strip()


def _find_cell(row: Node, column: str) -> Node | None:
    names = _COLUMNS[column]
    for cell in row.css("td[data-title]"):
        title = cell.attributes.get("data-title") or ""
        if title in names:
            return cell
    return None


def _price_cell(row: Node) -> Node | None:
    for cell in row.css("td[data-title]"):
        title = cell.attributes.get("data-title") or ""
        if title.startswith(("Вартість", "Цена", "Price")):
            return cell
    return None


def parse_catalog_page(html: str) -> list[CatalogRow]:
    """Every coin row of a year page or of the all-years page. Locale-agnostic."""
    tree = HTMLParser(html)
    rows: list[CatalogRow] = []
    for tr in tree.css("tr"):
        title_cell = _find_cell(tr, "title")
        if title_cell is None:
            continue
        link = title_cell.css_first("a[href]")
        if link is None:
            continue
        match = _LIST_HREF_RE.search(link.attributes.get("href") or "")
        if match is None:
            continue
        date_cell = _find_cell(tr, "date")
        date_text = ""
        if date_cell is not None:
            desktop = date_cell.css_first(".desktop")
            date_text = _cell_text(desktop if desktop is not None else date_cell)
        denomination_cell = _find_cell(tr, "denomination")
        mintage_cell = _find_cell(tr, "mintage")
        price_cell = _price_cell(tr)
        price_text, trend, price_date = "", None, None
        if price_cell is not None:
            price_date_match = _PRICE_HEADER_RE.search(
                price_cell.attributes.get("data-title") or ""
            )
            price_date = price_date_match.group(1) if price_date_match else None
            price_link = price_cell.css_first("a.list_price")
            price_node = price_link if price_link is not None else price_cell
            arrow = price_node.css_first("span")
            if arrow is not None:
                arrow_text = arrow.text(strip=True)
                arrow_class = arrow.attributes.get("class") or ""
                if "↑" in arrow_text or "up" in arrow_class:
                    trend = "up"
                elif "↓" in arrow_text or "down" in arrow_class:
                    trend = "down"
                arrow.decompose()
            price_text = _cell_text(price_node)
        rows.append(
            CatalogRow(
                coin_id=int(match.group(1)),
                slug=match.group(2),
                title=_cell_text(link),
                date_text=date_text,
                denomination_text=_cell_text(denomination_cell) if denomination_cell else "",
                mintage_text=_cell_text(mintage_cell) if mintage_cell else "",
                price_text=price_text,
                price_date=price_date,
                trend=trend,
            )
        )
    return rows


def parse_price(text: str) -> Decimal | None:
    lowered = text.casefold()
    if not text or any(marker in lowered for marker in _NO_DATA):
        return None
    if "=" in text or "x" in lowered or "**" in text:
        # docs/05-integrations.md, section 6: the legacy filter, kept.
        return None
    value = parse_int(text)
    return None if value is None else Decimal(value)


def rows_to_records(
    rows_uk: list[CatalogRow], rows_ru: list[CatalogRow] | None = None
) -> list[SourceRecord]:
    """One record per coin id; Russian titles joined in when available."""
    russian = {row.coin_id: row for row in rows_ru or []}
    records: list[SourceRecord] = []
    seen: set[int] = set()
    for row in rows_uk:
        if row.coin_id in seen:
            continue
        seen.add(row.coin_id)
        issued = parse_date(row.date_text)
        announced, actual = parse_mintage(row.mintage_text, thousands=True)
        ru_row = russian.get(row.coin_id)
        records.append(
            SourceRecord(
                source=SOURCE_UA_COINS,
                source_id=str(row.coin_id),
                title_uk=row.title,
                title_ru=ru_row.title if ru_row else None,
                denomination=denomination_value(row.denomination_text),
                denomination_label=row.denomination_text or None,
                currency=denomination_currency(row.denomination_text),
                year=issued.year if issued else None,
                issue_date=issued.isoformat() if issued else None,
                mintage=announced,
                mintage_actual=actual,
                price=parse_price(row.price_text),
                price_date=row.price_date,
                kind=classify_kind(row.title),
                url=coin_url(row.coin_id, row.slug),
                image_urls=[
                    image_url(row.coin_id, "obverse", "small_webp"),
                    image_url(row.coin_id, "reverse", "small_webp"),
                ],
                extra={"trend": row.trend, "slug": row.slug},
            )
        )
    # Coins present only in the Russian table (the snapshots differ in age).
    for coin_id, ru_row in russian.items():
        if coin_id in seen:
            continue
        issued = parse_date(ru_row.date_text)
        announced, actual = parse_mintage(ru_row.mintage_text, thousands=True)
        records.append(
            SourceRecord(
                source=SOURCE_UA_COINS,
                source_id=str(coin_id),
                title_uk=None,
                title_ru=ru_row.title,
                denomination=denomination_value(ru_row.denomination_text),
                denomination_label=ru_row.denomination_text or None,
                currency=denomination_currency(ru_row.denomination_text),
                year=issued.year if issued else None,
                issue_date=issued.isoformat() if issued else None,
                mintage=announced,
                mintage_actual=actual,
                price=parse_price(ru_row.price_text),
                price_date=ru_row.price_date,
                kind=classify_kind(ru_row.title),
                url=coin_url(coin_id, ru_row.slug, LOCALE_RU),
                extra={"trend": ru_row.trend, "slug": ru_row.slug, "russian_only": True},
            )
        )
    return records


@dataclass
class SeriesCount:
    name: str
    slug: str
    total: int
    base_metal: int | None
    precious_metal: int | None
    mintage_total: int | None


def parse_categories_page(html: str) -> list[SeriesCount]:
    """The series table: name, all, base, precious, total mintage."""
    tree = HTMLParser(html)
    result: list[SeriesCount] = []
    for tr in tree.css("tr"):
        cells = tr.css("td")
        if len(cells) < 2:
            continue
        link = cells[0].css_first("a[href*='/category/']")
        if link is None:
            continue
        href = link.attributes.get("href") or ""
        slug = href.rstrip("/").rsplit("/", 1)[-1]
        numbers = [parse_int(_cell_text(cell)) for cell in cells[1:]]
        total = numbers[0] if numbers else None
        if total is None:
            continue
        result.append(
            SeriesCount(
                name=_cell_text(link),
                slug=slug,
                total=total,
                base_metal=numbers[1] if len(numbers) > 1 else None,
                precious_metal=numbers[2] if len(numbers) > 2 else None,
                mintage_total=numbers[3] if len(numbers) > 3 else None,
            )
        )
    return result


@dataclass
class CoinPage:
    title: str | None
    title_alt: str | None
    price: Decimal | None
    series: str | None
    fields: dict[str, str] = field(default_factory=dict)
    image_urls: list[str] = field(default_factory=list)


def parse_coin_page(html: str) -> CoinPage:
    """The coin page: heading, the characteristics table, series, images.

    Used for a sample only; the reconnaissance needs it to learn what the page
    offers beyond the catalogue table: the Russian title line under the
    heading, the NBU retail price, the series link, the image paths.
    """
    tree = HTMLParser(html)
    for node in tree.css("script, style"):
        node.decompose()
    heading = tree.css_first("h1")
    title = _cell_text(heading) if heading is not None else None
    if title:
        title = re.sub(r"^Монета\s+", "", title)
        title = re.sub(r",\s*ціна.*$", "", title)
    subtitle = tree.css_first("h6")
    title_alt = _cell_text(subtitle) if subtitle is not None else None
    fields: dict[str, str] = {}
    table = tree.css_first("table.coin-info")
    if table is not None:
        rows = [[_cell_text(td) for td in tr.css("td")] for tr in table.css("tr")]
        if len(rows) >= 2:
            fields = dict(zip(rows[0], rows[1], strict=False))
    series = None
    for link in tree.css("a[href*='/category/']"):
        text = _cell_text(link)
        if text and not text.startswith("Всі монети"):
            series = text
            break
    price = None
    for node in tree.css("div"):
        text = _cell_text(node)
        if re.fullmatch(r"\d[\d\s   ]*\s*грн\.?", text):
            price = parse_price(text)
            break
    images = sorted(
        {
            src
            for img in tree.css("img[src]")
            for src in [img.attributes.get("src") or ""]
            if "/images/coins" in src
        }
    )
    return CoinPage(
        title=title,
        title_alt=title_alt,
        price=price,
        series=series,
        fields=fields,
        image_urls=images,
    )


def catalog_summary(records: list[SourceRecord]) -> dict[str, Any]:
    with_price = sum(1 for record in records if record.price is not None)
    with_russian = sum(1 for record in records if record.title_ru)
    return {
        "records": len(records),
        "coins": sum(1 for record in records if record.kind == "coin"),
        "sets": sum(1 for record in records if record.kind == "set"),
        "souvenirs": sum(1 for record in records if record.kind == "souvenir"),
        "withPrice": with_price,
        "withRussianTitle": with_russian,
        "priceDates": sorted({record.price_date for record in records if record.price_date}),
    }
