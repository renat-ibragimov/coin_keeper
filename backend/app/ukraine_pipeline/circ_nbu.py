"""The National Bank's "Про монети" page — circulation coins, not the catalogue.

bank.gov.ua/ua/uah/obig-coin/<slug> is a different page family from the
numismatic-products catalogue app/ukraine_recon/nbu.py already reads: no
search form, no per-card ids, and a denomination can show more than one
design stacked on the same page — the National Bank groups a coin's whole
history under one URL rather than giving each alloy its own address. Any of
the several numeric slugs a denomination answers to serves the same stack, so
app/ukraine_pipeline/circ_types.py only needs to name one per denomination.

Fetching the plain page (no query string) returns every design the National
Bank still tracks for that denomination, each as a `div.hide-show-currency`
block: a heading, a status tag ("В обігу" / "Поступово вилучається з обігу" /
"Вилучена з обігу"), a paragraph of "Label — value" lines separated by <br>,
and the obverse/reverse images, labelled by `alt` exactly the way
docs/05-integrations.md already prescribes for the other two sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from selectolax.parser import HTMLParser, Node

from app.ukraine_pipeline.circ_types import CoinType

BASE_URL = "https://bank.gov.ua"
FIELD_INTRO_DATE = "Дата введення в обіг"
FIELD_METAL = "Метал"
FIELD_DIAMETER = "Діаметр, мм"
FIELD_THICKNESS = "Товщина монети, мм"
FIELD_WEIGHT = "Вага, г"
FIELD_EDGE = "Гурт"
FIELD_YEARS = "Роки карбування"

ROLES = ("obverse", "reverse")


@dataclass
class ObigCard:
    """One design, as the page presents it: a heading and its own params."""

    title: str
    status: str
    fields: dict[str, str] = field(default_factory=dict)
    images: dict[str, str] = field(default_factory=dict)


def page_url(slug: str) -> str:
    return f"{BASE_URL}/ua/uah/obig-coin/{slug}"


def _text(node: Node | None) -> str:
    return node.text(strip=True) if node is not None else ""


def _absolute(src: str) -> str:
    return src if src.startswith("http") else BASE_URL + src


def parse_page(html: str) -> list[ObigCard]:
    tree = HTMLParser(html)
    cards: list[ObigCard] = []
    for block in tree.css("div.hide-show-currency"):
        title = _text(block.css_first("h3"))
        if not title:
            continue
        fields: dict[str, str] = {}
        paragraph = block.css_first("div.box p")
        if paragraph is not None:
            for part in paragraph.text(separator="|", strip=True).split("|"):
                label, separator, value = part.partition("—")
                if not separator:
                    continue
                fields[label.strip()] = value.strip()
        images: dict[str, str] = {}
        for img in block.css("img[alt]"):
            src = img.attributes.get("src") or ""
            alt = (img.attributes.get("alt") or "").casefold()
            if not src:
                continue
            if "авер" in alt:
                images.setdefault("obverse", _absolute(src))
            elif "ревер" in alt:
                images.setdefault("reverse", _absolute(src))
        cards.append(
            ObigCard(
                title=title, status=_text(block.css_first("div.tag")), fields=fields, images=images
            )
        )
    return cards


def pick_card(cards: list[ObigCard], coin_type: CoinType) -> ObigCard | None:
    """The one card among the page's stack that this type means.

    Most denominations have exactly one card, or fetch a page dedicated to
    one design (the four 2018-pattern hryvnia slugs), so no hint is needed.
    The one page that genuinely stacks two designs we track separately — the
    hryvnia at "100_1996" — is disambiguated by an exact title match, not a
    substring: "1 гривня" is a prefix of "1 гривня зразка 2018 року" and
    would otherwise match both.
    """
    if not cards:
        return None
    if coin_type.photo_title_hint is None:
        return cards[0]
    return next((card for card in cards if card.title == coin_type.photo_title_hint), None)
