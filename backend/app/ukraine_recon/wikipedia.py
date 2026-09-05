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
from decimal import Decimal

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


MINTAGE_HEADING = "Тиражі та хронологія випуску розмінних та обігових монет"

# The table's own column headers -> our (value, unit). Matched by exact text
# rather than by position: the table also carries a leading "Рік на монеті"
# and a trailing "Загалом" this dict has no entry for, and a name lookup
# survives the sources adding a column more gracefully than a fixed index
# would.
_HEADER_UNITS: dict[str, tuple[Decimal, str]] = {
    "1 копійка": (Decimal(1), "kopiika"),
    "2 копійки": (Decimal(2), "kopiika"),
    "5 копійок": (Decimal(5), "kopiika"),
    "10 копійок": (Decimal(10), "kopiika"),
    "25 копійок": (Decimal(25), "kopiika"),
    "50 копійок": (Decimal(50), "kopiika"),
    "1 гривня": (Decimal(1), "hryvnia"),
    "2 гривні": (Decimal(2), "hryvnia"),
    "5 гривень": (Decimal(5), "hryvnia"),
    "10 гривень": (Decimal(10), "hryvnia"),
}

# One entry inside a cell: "140 млн" (a plain count), "5 тис**" (a count made
# only for collector sets), "Так***" (issued, no number given) or "Ні"
# (nothing that year). A cell can hold two of these side by side — the 2018
# row prints "140 млн***** 20 тис****" because both hryvnia patterns were
# struck that year — which is exactly why this returns a tuple, not one value.
_MULTIPLIER = {"млн": 1_000_000, "тис": 1_000, "шт": 1}
_ENTRY_RE = re.compile(
    r"(?:(?P<num>\d+(?:[.,]\d+)?)\s*(?P<unit>млн|тис|шт)\.?|(?P<word>Так|Ні)|(?P<unknown>\?))"
    r"(?P<stars>\*{1,5})?"
)
# The table's own note legend: * trial, ** collector-set-only, *** issued but
# not officially released, **** the 2001 hryvnia pattern, ***** the 2018 one.
PATTERN_2001 = "2001"
PATTERN_2018 = "2018"


@dataclass(frozen=True, slots=True)
class MintageEntry:
    count: int | None
    # "Так" with no number: the table says the coin exists but gives no
    # figure. Kept apart from `unknown` — a "?" cell is not even sure of
    # that much — so a consumer can tell "issued, count not given" from
    # "the table itself does not know".
    issued_no_count: bool
    unknown: bool
    trial: bool
    collector_set: bool
    unofficial: bool
    # Which hryvnia pattern this number belongs to, when the cell names one;
    # None everywhere except the double-valued cells of the 2018 changeover.
    pattern: str | None


@dataclass(frozen=True, slots=True)
class MintageCell:
    year: int
    value: Decimal
    unit: str
    entries: tuple[MintageEntry, ...]


def _parse_entries(text: str) -> tuple[MintageEntry, ...]:
    entries = []
    for match in _ENTRY_RE.finditer(text):
        stars = match.group("stars") or ""
        pattern = PATTERN_2018 if len(stars) >= 5 else PATTERN_2001 if len(stars) == 4 else None
        issued_no_count = False
        unknown = False
        count: int | None
        if match.group("num"):
            value = Decimal(match.group("num").replace(",", "."))
            count = int(value * _MULTIPLIER[match.group("unit")])
        elif match.group("word"):
            issued_no_count = match.group("word") == "Так"
            count = None if issued_no_count else 0
        else:
            unknown = True
            count = None
        entries.append(
            MintageEntry(
                count=count,
                issued_no_count=issued_no_count,
                unknown=unknown,
                trial=len(stars) == 1,
                collector_set=len(stars) == 2,
                unofficial=len(stars) == 3,
                pattern=pattern,
            )
        )
    return tuple(entries)


def parse_mintage_table(html: str) -> list[MintageCell]:
    """The "Тиражі та хронологія" table: one cell per (denomination, year) *row*.

    Rows are read through parse_tables, which already expands rowspan and
    colspan — including the mint-name divider rows the table uses to group
    years by where they were struck ("Італійський монетний двір", ...). Such
    a row has no year in its first cell after expansion and is skipped along
    with any row a cell carries no entry for.

    1992 is the one year the live page (checked 2026-09-05) splits across two
    such divider sections — Istituto Poligrafico e Zecca dello Stato struck
    the bulk of that year's kopecks, the Луганський верстатобудівний завод
    struck a separate, smaller run (real production for 10/25/50 kopecks,
    trial batches only for 1/2/5 kopecks and 1 hryvnia) — so this function can
    return *more than one* `MintageCell` for the same (value, unit, year): one
    per row that names it, not one per key. A caller that needs a single
    number for a year must add these together (app/ukraine_pipeline/
    circ_mintage.py:usable_count) rather than take the last one parsed — doing
    the latter is exactly the bug that shipped 1 kopiika 1992 as 300 (the
    Luhansk trial count alone) instead of 610,000,300 (Italian mint plus that
    trial). Every other year on the page names exactly one row.

    Units are read per cell (млн=10⁶, тис=10³, шт=1, see `_MULTIPLIER`), not
    from a table-wide header note — checked directly against the live page,
    not assumed: every cell that carries a number spells out its own unit.
    """
    cells: list[MintageCell] = []
    for table in parse_tables(html):
        if not table.headers or not table.headers[0].startswith("Рік"):
            continue
        columns = [_HEADER_UNITS.get(header.strip()) for header in table.headers]
        for row in table.rows:
            year = parse_int(row[0].text)
            if year is None:
                continue
            for index, column in enumerate(columns):
                if column is None or index >= len(row):
                    continue
                entries = _parse_entries(row[index].text)
                if not entries:
                    continue
                value, unit = column
                cells.append(MintageCell(year=year, value=value, unit=unit, entries=entries))
    return cells


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
