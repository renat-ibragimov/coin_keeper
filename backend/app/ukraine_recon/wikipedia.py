"""The Ukrainian Wikipedia lists of commemorative coins.

Two list pages, each a sequence of wikitables with the columns
`№ | Назва | Номінал | Тираж | [Маса] | Дата випуску | Аверс | Реверс`:

* precious metals: silver numbered 1..N straight through the tables,
  bimetal and gold with their own numbering (the group comes from the
  heading above the table);
* base metals: one sequence 1..N across all tables.

Plus the hryvnia article, whose "Монетні набори" table lists the mint sets
(`Рік | Назва | Тираж | Вміст`).

Tables are parsed as tables, with rowspan/colspan expanded; the text is never
scanned. Dates are dd.mm.yy.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from selectolax.parser import HTMLParser, Node

from app.ukraine_recon.models import SOURCE_WIKIPEDIA, SourceRecord
from app.ukraine_recon.normalize import (
    denomination_currency,
    denomination_value,
    parse_date,
    parse_int,
)

BASE_URL = "https://uk.wikipedia.org/wiki/"
PAGE_PRECIOUS = "Список_ювілейних_та_пам'ятних_монет_України_з_дорогоцінних_металів"
PAGE_BASE = "Список_ювілейних_та_пам'ятних_монет_України_з_недорогоцінних_металів"
PAGE_HRYVNIA = "Монети_української_гривні"

GROUP_SILVER = "silver"
GROUP_GOLD = "gold"
GROUP_BIMETAL = "bimetal"
GROUP_BASE = "base"


def page_url(title: str) -> str:
    return BASE_URL + title


@dataclass
class Cell:
    text: str
    link: str | None = None
    image: str | None = None


@dataclass
class Table:
    heading: str
    headers: list[str]
    rows: list[list[Cell]] = field(default_factory=list)


def _cell_text(node: Node) -> str:
    for sup in node.css("sup"):
        sup.decompose()
    for br in node.css("br"):
        br.replace_with(" ")
    return re.sub(r"\s+", " ", node.text(separator=" ", strip=True)).strip()


def _cell(node: Node) -> Cell:
    link = node.css_first("a[href]")
    img = node.css_first("img[src]")
    href = link.attributes.get("href") if link is not None else None
    src = img.attributes.get("src") if img is not None else None
    if src and src.startswith("//"):
        src = "https:" + src
    text = _cell_text(node)
    return Cell(text=text, link=href, image=src)


def _expand_table(table: Node) -> list[list[Cell]]:
    """Rows as a rectangular grid: rowspan/colspan cells are repeated."""
    grid: list[list[Cell | None]] = []
    pending: dict[int, tuple[Cell, int]] = {}
    for tr in table.css("tr"):
        row: list[Cell | None] = []
        column = 0
        cells = [child for child in tr.iter() if child.tag in ("td", "th")]
        cell_index = 0
        while cell_index < len(cells) or column in pending:
            if column in pending:
                cell, remaining = pending.pop(column)
                row.append(cell)
                if remaining > 1:
                    pending[column] = (cell, remaining - 1)
                column += 1
                continue
            node = cells[cell_index]
            cell_index += 1
            cell = _cell(node)
            rowspan = int(node.attributes.get("rowspan") or 1)
            colspan = int(node.attributes.get("colspan") or 1)
            for offset in range(colspan):
                row.append(cell)
                if rowspan > 1:
                    pending[column + offset] = (cell, rowspan - 1)
            column += colspan
        grid.append(row)
    return [[cell if cell is not None else Cell("") for cell in row] for row in grid]


def parse_tables(html: str) -> list[Table]:
    """Every wikitable with the heading that precedes it in document order."""
    tree = HTMLParser(html)
    tables: list[Table] = []
    heading = ""
    root = tree.body if tree.body is not None else tree.root
    if root is None:
        return tables
    # Document order matters: the heading that names a table is the closest
    # one above it. A CSS query would not guarantee that order.
    for node in root.traverse():
        if node.tag in ("h2", "h3", "h4"):
            heading = _cell_text(node)
            continue
        if node.tag != "table" or "wikitable" not in (node.attributes.get("class") or ""):
            continue
        rows = _expand_table(node)
        if not rows:
            continue
        headers = [cell.text for cell in rows[0]]
        body = [row for row in rows[1:] if any(cell.text for cell in row)]
        tables.append(Table(heading=heading, headers=headers, rows=body))
    return tables


def _is_list_table(table: Table) -> bool:
    return len(table.headers) >= 5 and table.headers[0] == "№" and table.headers[1] == "Назва"


def _group_for(heading: str, page: str) -> str:
    lowered = heading.casefold()
    if page == PAGE_BASE:
        return GROUP_BASE
    if "золот" in lowered:
        return GROUP_GOLD
    if "біметал" in lowered:
        return GROUP_BIMETAL
    return GROUP_SILVER


def _column(headers: list[str], *prefixes: str) -> int | None:
    for index, header in enumerate(headers):
        lowered = header.casefold()
        if any(lowered.startswith(prefix) for prefix in prefixes):
            return index
    return None


def parse_list_page(html: str, page: str) -> list[SourceRecord]:
    records: list[SourceRecord] = []
    for table in parse_tables(html):
        if not _is_list_table(table):
            continue
        group = _group_for(table.heading, page)
        col_denomination = _column(table.headers, "номінал")
        col_mintage = _column(table.headers, "тираж")
        col_mass = _column(table.headers, "маса")
        col_date = _column(table.headers, "дата")
        col_obverse = _column(table.headers, "аверс")
        col_reverse = _column(table.headers, "реверс")
        currency_hint = table.headers[col_denomination] if col_denomination is not None else ""
        currency = denomination_currency(currency_hint)
        unit = "крб" if currency == "UAK" else "грн"
        for row in table.rows:
            number = parse_int(row[0].text)
            title = row[1].text
            if number is None or not title:
                continue
            issued = parse_date(row[col_date].text) if col_date is not None else None
            denomination_text = row[col_denomination].text if col_denomination is not None else ""
            images = [
                row[col].image
                for col in (col_obverse, col_reverse)
                if col is not None and col < len(row) and row[col].image
            ]
            records.append(
                SourceRecord(
                    source=SOURCE_WIKIPEDIA,
                    source_id=f"{group}:{number}",
                    title_uk=title,
                    denomination=denomination_value(denomination_text),
                    denomination_label=f"{denomination_text} {unit}".strip(),
                    currency=currency,
                    year=issued.year if issued else None,
                    issue_date=issued.isoformat() if issued else None,
                    mintage=parse_int(row[col_mintage].text) if col_mintage is not None else None,
                    metal=group,
                    series=None,
                    url=row[1].link or page_url(page),
                    image_urls=[image for image in images if image],
                    extra={
                        "number": number,
                        "group": group,
                        "heading": table.heading,
                        "massGrams": row[col_mass].text if col_mass is not None else None,
                    },
                )
            )
    return records


@dataclass
class MintSet:
    year: int | None
    title: str
    mintage: int | None
    contents: str


def parse_sets(html: str) -> list[MintSet]:
    sets: list[MintSet] = []
    for table in parse_tables(html):
        if len(table.headers) < 4 or table.headers[:2] != ["Рік", "Назва"]:
            continue
        for row in table.rows:
            sets.append(
                MintSet(
                    year=parse_int(row[0].text),
                    title=row[1].text,
                    mintage=parse_int(row[2].text),
                    contents=row[3].text if len(row) > 3 else "",
                )
            )
    return sets
