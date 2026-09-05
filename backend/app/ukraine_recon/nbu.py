"""The NBU numismatic catalogue at bank.gov.ua.

What the reconnaissance established (docs/05-integrations.md):

* The catalogue page `/ua/uah/numismatic-products/souvenier-coins` is a
  search form. Results come from one POST endpoint,
  `/ua/component/source/searchSouvenierCoinResult`, with `page`, `perPage`
  (5/10/25/100) and optional filters (`category[]`, `serie[]`, `metal[]`,
  `nominal[]`, `from`, `to`, `search`). Plain HTML, no JavaScript needed.
* There are no per-coin pages: every result card already carries the full
  description, artists, mintage (announced/actual), mass, diameter, edge,
  quality, series and the images.
* Images: a thumbnail `/media/coins/{id}/avers.jpg` and the full-size
  `/files/coins_images/{code}a.png` / `{code}r.png` (about 1600 px, PNG);
  `{code}a0.png` and `{code}u.pdf` are extra views and a booklet, not always
  present.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from selectolax.parser import HTMLParser, Node

from app.ukraine_recon.models import SOURCE_NBU, SourceRecord
from app.ukraine_recon.normalize import (
    classify_kind,
    denomination_currency,
    denomination_value,
    parse_date,
    parse_int,
    parse_mintage,
)

BASE_URL = "https://bank.gov.ua"
LOCALE_UK = "ua"
LOCALE_EN = "en"
CATALOG_URL = f"{BASE_URL}/ua/uah/numismatic-products/souvenier-coins"
SEARCH_URL = f"{BASE_URL}/ua/component/source/searchSouvenierCoinResult"


def catalog_url(locale: str = LOCALE_UK) -> str:
    return f"{BASE_URL}/{locale}/uah/numismatic-products/souvenier-coins"


def search_url(locale: str = LOCALE_UK) -> str:
    """The same endpoint under the site's other language.

    Card ids are the same in both locales, which is what makes the English
    site usable as the source of official title_en (docs/05-integrations.md).
    """
    return f"{BASE_URL}/{locale}/component/source/searchSouvenierCoinResult"


PAGE_SIZE = 100
CATEGORY_COIN = "Coin"
CATEGORY_SOUVENIR = "Souvenir"

_FOUND_RE = re.compile(r"знайдено\s*<b>\s*(\d[\d\s]*)")
_IMAGE_ID_RE = re.compile(r"/media/coins/(\d+)/")
_IMAGE_CODE_RE = re.compile(r"/files/coins_images/([A-Za-z0-9]+?)([ar]\d*|u)\.(png|jpg|pdf)")

FIELD_DENOMINATION = "Номінал"
FIELD_DATE_CIRCULATION = "Дата введення в обіг"
FIELD_DATE_ISSUE = "Дата випуску"
FIELD_MATERIAL = "Матеріал"
FIELD_MINTAGE = "Тираж (оголошений/фактичний), шт."
FIELD_ARTIST = "Художник"
FIELD_SCULPTOR = "Скульптор"
FIELD_MASS = "Маса, г"
FIELD_FINE_MASS = "Маса дорогоцінного металу в чистоті, г"
FIELD_DIAMETER = "Діаметр, мм"
FIELD_QUALITY = "Категорія якості карбування"
FIELD_EDGE = "Гурт"


def search_form(
    page: int,
    *,
    per_page: int = PAGE_SIZE,
    category: str | None = CATEGORY_COIN,
    date_from: str | None = None,
    date_to: str | None = None,
    search: str | None = None,
    nominal: str | None = None,
) -> dict[str, str]:
    """The POST body. Empty filter values make the endpoint answer 404, so
    only the filters actually used are sent.

    `search` is a loose keyword match against the endpoint's own index (it
    is not a phrase match — confirmed live 2026-09-05: "20 років запровадження
    гривні" returned 213 unrelated results), so a caller narrows with other
    filters rather than relying on the search string alone to pin one card.
    """
    form = {"page": str(page), "perPage": str(per_page)}
    if category:
        form["category[]"] = category
    if date_from:
        form["from"] = date_from
    if date_to:
        form["to"] = date_to
    if search:
        form["search"] = search
    if nominal:
        form["nominal[]"] = nominal
    return form


@dataclass
class NbuCard:
    nbu_id: str | None
    code: str | None
    title: str
    series: str | None
    fields: dict[str, str] = field(default_factory=dict)
    description: list[str] = field(default_factory=list)
    thumbnails: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)


@dataclass
class SearchPage:
    total: int | None
    page_count: int | None
    cards: list[NbuCard]


def _text(node: Node | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", node.text(separator=" ", strip=True)).strip()


def _clean_label(text: str) -> str:
    return text.rstrip(":").strip()


def _absolute(path: str) -> str:
    path = path.split("?", 1)[0]
    return path if path.startswith("http") else BASE_URL + path


def parse_search_page(html: str) -> SearchPage:
    tree = HTMLParser(html)
    total_match = _FOUND_RE.search(html)
    total = parse_int(total_match.group(1)) if total_match else None
    pages = [int(a.attributes.get("data-page") or 0) for a in tree.css("a[data-page]")]
    page_count = max(pages) if pages else None
    cards: list[NbuCard] = []
    for block in tree.css("div.search-result"):
        title = _text(block.css_first("div.title"))
        if not title:
            continue
        series = _text(block.css_first("div.tag")) or None
        fields: dict[str, str] = {}
        for line in block.css("div.close-lines > div"):
            label = line.css_first("span.mark")
            value = line.css_first("span.mark-text")
            if label is None or value is None:
                continue
            fields[_clean_label(_text(label))] = _text(value)
        description = [
            _text(paragraph) for paragraph in block.css("div.description__text") if _text(paragraph)
        ]
        thumbnails: list[str] = []
        nbu_id: str | None = None
        for img in block.css("img[src]"):
            src = img.attributes.get("src") or ""
            if "/media/coins/" not in src:
                continue
            thumbnails.append(_absolute(src))
            id_match = _IMAGE_ID_RE.search(src)
            if id_match and nbu_id is None:
                nbu_id = id_match.group(1)
        if nbu_id is None:
            fancybox = block.css_first("[data-fancybox]")
            if fancybox is not None:
                marker = fancybox.attributes.get("data-fancybox") or ""
                nbu_id = marker.removeprefix("image_") or None
        images: list[str] = []
        code: str | None = None
        for link in block.css("a.big-image[href]"):
            href = link.attributes.get("href") or ""
            images.append(_absolute(href))
            code_match = _IMAGE_CODE_RE.search(href)
            if code_match and code is None:
                code = code_match.group(1)
        cards.append(
            NbuCard(
                nbu_id=nbu_id,
                code=code,
                title=title,
                series=series,
                fields=fields,
                description=description,
                thumbnails=thumbnails,
                images=images,
            )
        )
    return SearchPage(total=total, page_count=page_count, cards=cards)


def parse_series_options(catalog_html: str) -> list[str]:
    """The series filter of the search form: the NBU's own list of series."""
    tree = HTMLParser(catalog_html)
    select = tree.css_first("select[name='serie[]']")
    if select is None:
        return []
    names = []
    for option in select.css("option"):
        value = option.attributes.get("value") or ""
        if value:
            names.append(value)
    return names


def card_to_record(card: NbuCard) -> SourceRecord:
    fields = card.fields
    date_text = fields.get(FIELD_DATE_CIRCULATION) or fields.get(FIELD_DATE_ISSUE)
    issued = parse_date(date_text)
    announced, actual = parse_mintage(fields.get(FIELD_MINTAGE))
    denomination_text = fields.get(FIELD_DENOMINATION)
    source_id = card.nbu_id or card.code or card.title
    return SourceRecord(
        source=SOURCE_NBU,
        source_id=source_id,
        title_uk=card.title,
        denomination=denomination_value(denomination_text),
        denomination_label=denomination_text,
        currency=denomination_currency(denomination_text),
        year=issued.year if issued else None,
        issue_date=issued.isoformat() if issued else None,
        mintage=announced,
        mintage_actual=actual,
        metal=fields.get(FIELD_MATERIAL),
        series=card.series,
        kind=classify_kind(card.title),
        url=CATALOG_URL,
        image_urls=card.images or card.thumbnails,
        extra={
            "nbuId": card.nbu_id,
            "code": card.code,
            "dateField": (
                FIELD_DATE_CIRCULATION if FIELD_DATE_CIRCULATION in fields else FIELD_DATE_ISSUE
            ),
            "artist": fields.get(FIELD_ARTIST),
            "sculptor": fields.get(FIELD_SCULPTOR),
            "massGrams": fields.get(FIELD_MASS) or fields.get(FIELD_FINE_MASS),
            "diameterMm": fields.get(FIELD_DIAMETER),
            "quality": fields.get(FIELD_QUALITY),
            "edge": fields.get(FIELD_EDGE),
            "thumbnails": card.thumbnails,
            "hasDescription": bool(card.description),
            # The card's own prose. It is the only place the NBU says what is
            # drawn on the coin, which is what tells two same-year, same-value
            # issues of one series apart.
            "description": card.description,
        },
    )


def field_coverage(cards: list[NbuCard]) -> dict[str, int]:
    """How many cards carry each field: tells part B what it can rely on."""
    coverage: dict[str, int] = {}
    for card in cards:
        for label in card.fields:
            coverage[label] = coverage.get(label, 0) + 1
        if card.description:
            coverage["description"] = coverage.get("description", 0) + 1
        if card.series:
            coverage["series"] = coverage.get("series", 0) + 1
        if card.images:
            coverage["images"] = coverage.get("images", 0) + 1
    return dict(sorted(coverage.items(), key=lambda item: -item[1]))
