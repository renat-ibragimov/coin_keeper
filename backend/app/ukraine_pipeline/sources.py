"""The three sources, fetched once and clustered into coins.

Reuses the reconnaissance parsers wholesale (app/ukraine_recon/): the NBU
listing, the ua-coins.info tables and the Wikipedia lists, plus the union-find
clustering that decides which rows of different sites are the same coin.

What this module adds on top is the English pass over the NBU site. Its card
ids are the same in both locales, so the English listing gives an official
title_en and an official English series name for every card — with no
translation involved (docs/05-integrations.md, section 8).

And the rolls. Circulation commemoratives ("обігові пам'ятні монети", 10 UAH
since 2022) are not numismatic products, so the catalogue has no card for the
coin — only for the roll of 25 it is sold in. That card still names the coin,
dates it, pictures it and states the roll's face value, so the coin is read
off it: the denomination is the roll's divided by the number of coins in it.
Without this the whole series arrives at the bridge with no candidate at all.

Nothing here touches the database. Repeated runs cost no requests: every
response is on disk under --cache-dir.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date

from app.models.enums import MetalKind
from app.reference_data.materials import parse_material
from app.ukraine_recon import nbu, triangulate, ua_coins, wikipedia
from app.ukraine_recon.http import FetchResult, PoliteClient, SourceUnreachableError
from app.ukraine_recon.models import (
    SOURCE_NBU,
    SOURCE_UA_COINS,
    SOURCE_WIKIPEDIA,
    SourceRecord,
)
from app.ukraine_recon.normalize import bare_title, fix_homoglyphs
from app.ukraine_recon.triangulate import Cluster

FIRST_YEAR = 1992
MODE_AUTO = "auto"
MODE_LIVE = "live"
MODE_WAYBACK = "wayback"
MODE_SKIP = "skip"

# The obverse and reverse of an NBU card: "{code}a.png" and "{code}r.png".
# "{code}a0.png" and friends are extra views, and "u.pdf" is the booklet.
_NBU_SIDE_RE = re.compile(r"/files/coins_images/([A-Za-z0-9]+)([ar])\.png$")

PRECIOUS_CODES = ("silver", "gold", "platinum")

# What the National Bank writes in "Матеріал". A closed list: the search form
# of the site offers exactly these nine values, so they are mapped rather than
# guessed at. Silver and gold carry no fineness on the card, which is why they
# point at no dictionary row — the metal kind is known all the same, and that
# is what the collection value depends on.
NBU_METALS: dict[str, tuple[str | None, MetalKind]] = {
    "срібло": (None, MetalKind.PRECIOUS),
    "золото": (None, MetalKind.PRECIOUS),
    "біметалеві із дорогоцінних металів": ("bimetal", MetalKind.PRECIOUS),
    "біметалеві із недорогоцінних металів": ("bimetal", MetalKind.BASE),
    "нейзильбер": ("nickel_silver", MetalKind.BASE),
    "мельхіор": ("copper_nickel", MetalKind.BASE),
    "сплав на основі цинку": (None, MetalKind.BASE),
    "не вказується (набір)": (None, MetalKind.UNKNOWN),
    "інший (банкнота)": (None, MetalKind.UNKNOWN),
}

# "Ролик обігових пам'ятних монет [номіналом 10 гривень] «X» (у ролику 25 монет)"
_ROLL_HEAD_RE = re.compile(
    r"^Ролик\s+обігових\s+пам.?ятних\s+монет\s+(?:номіналом\s+[\d\s]+\S+\s+)?",
    re.IGNORECASE,
)
_ROLL_TAIL_RE = re.compile(r"\(\s*у\s+ролику\s+(?P<count>\d+)\s+монет\s*\)\s*$", re.IGNORECASE)
# The English site names the coin first and describes the roll in brackets
# after it, in half a dozen wordings; every trailing bracket is the roll.
_TRAILING_BRACKETS_RE = re.compile(r"(?:\s*\([^()]*\))+\s*$")
_LABEL_UNIT_RE = re.compile(r"[^\d\s.,]+")


@dataclass(frozen=True, slots=True)
class NbuEnglish:
    title: str
    series: str | None


@dataclass
class Sources:
    """Everything the steps need to know about the outside world."""

    nbu: list[SourceRecord] = field(default_factory=list)
    ua_coins: list[SourceRecord] = field(default_factory=list)
    wikipedia: list[SourceRecord] = field(default_factory=list)
    nbu_english: dict[str, NbuEnglish] = field(default_factory=dict)
    clusters: list[Cluster] = field(default_factory=list)
    access: dict[str, str] = field(default_factory=dict)

    def by_source(self) -> dict[str, list[SourceRecord]]:
        return {
            SOURCE_NBU: self.nbu,
            SOURCE_UA_COINS: self.ua_coins,
            SOURCE_WIKIPEDIA: self.wikipedia,
        }

    def cluster_by_key(self) -> dict[str, Cluster]:
        return {cluster_key(cluster): cluster for cluster in self.clusters}

    def cluster_of(self, source: str, source_id: str) -> Cluster | None:
        for cluster in self.clusters:
            record = cluster.record_of(source)
            if record is not None and record.source_id == source_id:
                return cluster
        return None

    def cluster_by_url(self, source: str, url: str) -> Cluster | None:
        """The same lookup for the sources we store a page address of.

        Wikipedia numbers its coins by its own sequence, so what goes into
        price_source_links is the article URL, not an id.
        """
        for cluster in self.clusters:
            record = cluster.record_of(source)
            if record is not None and record.url == url:
                return cluster
        return None


def cluster_key(cluster: Cluster) -> str:
    """A stable name for a cluster: the NBU card if there is one.

    The key goes into the review CSV and into the report, so it has to survive
    a re-run. Preference order is the order of trust — the issuer first.
    """
    for source in (SOURCE_NBU, SOURCE_UA_COINS, SOURCE_WIKIPEDIA):
        record = cluster.record_of(source)
        if record is not None:
            return f"{source}:{record.source_id}"
    return "empty"


def coin_clusters(sources: Sources) -> list[Cluster]:
    """Clusters that describe a coin — not a set, not souvenir packaging."""
    return [cluster for cluster in sources.clusters if cluster.kind == "coin"]


# Quotation marks the NBU wraps some names in. Stripped as a balanced pair
# only, so the inner quotes of `Морський дрон "Sea Baby"` survive.
_QUOTE_PAIRS = {
    '"': '"',
    "'": "'",
    "`": "`",
    "«": "»",
    "\u201c": "\u201d",
    "\u201e": "\u201c",
    "\u2018": "\u2019",
}
_MAX_STRIP_ROUNDS = 4


def official_title(raw: str | None) -> str:
    """The coin's name as the NBU means it: no marker, packaging or quotes.

    The two markers can come in either order — "… (н) у сувенірному пакованні"
    as well as "… у сувенірному пакованні (н)" — so stripping runs until the
    string stops changing rather than once.
    """
    text = fix_homoglyphs((raw or "").strip())
    for _ in range(_MAX_STRIP_ROUNDS):
        stripped = _unquote(bare_title(text).strip())
        if stripped == text:
            break
        text = stripped
    return text


def _unquote(text: str) -> str:
    if len(text) > 1 and _QUOTE_PAIRS.get(text[0]) == text[-1]:
        return text[1:-1].strip()
    return text


def nbu_title(record: SourceRecord) -> str:
    """The NBU name of the coin: no metal marker, no packaging phrase."""
    return official_title(record.title_uk)


def nbu_metal(text: str | None) -> tuple[str | None, MetalKind]:
    """(composition code, metal kind) out of an NBU "Матеріал".

    The nine words the site uses are mapped outright; anything else falls back
    to the general parser, which reads the uCoin-shaped strings our own
    catalogue carries. An unreadable material leaves the kind unknown rather
    than calling the coin base metal.
    """
    key = " ".join((text or "").casefold().split())
    if key in NBU_METALS:
        return NBU_METALS[key]
    code = parse_material(text).composition
    if code is None:
        return None, MetalKind.UNKNOWN
    return code, MetalKind.PRECIOUS if code.startswith(PRECIOUS_CODES) else MetalKind.BASE


def roll_coin(record: SourceRecord) -> SourceRecord | None:
    """The coin a roll card is a roll of, or None if the card is not a roll.

    Everything comes off the card: the name it quotes, the year it is dated,
    the images it shows (they are the coin's obverse and reverse, not a photo
    of the packaging) and the face value, which is the roll's divided by the
    number of coins the title states. The roll's own mintage counts rolls, so
    it is not carried over, and its material says "не вказується (набір)".
    """
    title = record.title_uk or ""
    tail = _ROLL_TAIL_RE.search(title)
    if tail is None or record.denomination is None:
        return None
    head = _ROLL_HEAD_RE.sub("", title[: tail.start()])
    if head == title[: tail.start()]:
        return None
    name = official_title(head)
    count = int(tail.group("count"))
    if not name or count <= 0:
        return None
    denomination = record.denomination / count
    unit = _LABEL_UNIT_RE.search(record.denomination_label or "")
    return replace(
        record,
        title_uk=name,
        title_ru=None,
        denomination=denomination,
        denomination_label=(
            f"{format(denomination.normalize(), 'f')} {unit.group(0)}" if unit else None
        ),
        mintage=None,
        mintage_actual=None,
        metal=None,
        series=None,
        kind="coin",
        image_urls=list(record.image_urls),
        extra={**record.extra, "fromRoll": count, "rollTitle": title},
    )


def roll_coin_english(title: str | None) -> str | None:
    """The coin's English name out of an English roll title.

    The English site puts the coin first and the roll in brackets after it —
    "(a roll of circulation commemorative coins) (25 coins to a roll)" — in
    half a dozen wordings, so every trailing bracket is dropped rather than
    any one of them matched.
    """
    if not title:
        return None
    name = _TRAILING_BRACKETS_RE.sub("", title).strip()
    return name or None


def nbu_sides(record: SourceRecord) -> dict[str, str]:
    """{'obverse': url, 'reverse': url} of the full-size NBU images.

    Only 389 of the 1048 cards have them; the rest offer the 198 px preview
    only, which nbu_thumbnails returns separately.
    """
    sides: dict[str, str] = {}
    for url in record.image_urls:
        match = _NBU_SIDE_RE.search(url)
        if match is None:
            continue
        side = "obverse" if match.group(2) == "a" else "reverse"
        sides.setdefault(side, url)
    return sides


def nbu_thumbnails(record: SourceRecord) -> dict[str, str]:
    """The 198 px previews every card has: /media/coins/{id}/avers.jpg."""
    sides: dict[str, str] = {}
    for url in record.extra.get("thumbnails") or []:
        if url.endswith("avers.jpg"):
            sides.setdefault("obverse", url)
        elif url.endswith("revers.jpg"):
            sides.setdefault("reverse", url)
    return sides


def ua_coins_sides(record: SourceRecord) -> dict[str, str]:
    """The 600 px WebP pair, the largest ua-coins really serves."""
    coin_id = int(record.source_id)
    return {
        "obverse": ua_coins.image_url(coin_id, "obverse", "middle_webp"),
        "reverse": ua_coins.image_url(coin_id, "reverse", "middle_webp"),
    }


# --------------------------------------------------------------------- fetch
def fetch_sources(
    client: PoliteClient,
    *,
    log: Callable[[str], None],
    warn: Callable[[str], None],
    ua_coins_mode: str = MODE_AUTO,
    since_year: int | None = None,
) -> Sources:
    sources = Sources()
    _fetch_nbu(client, sources, log=log, warn=warn, since_year=since_year)
    _fetch_ua_coins(client, sources, log=log, warn=warn, mode=ua_coins_mode)
    _fetch_wikipedia(client, sources, log=log, warn=warn)

    for name, records in sources.by_source().items():
        if since_year is not None:
            records[:] = [r for r in records if r.year is None or r.year >= since_year]
        promoted = triangulate.promote_packaged_coins(records)
        if promoted:
            log(f"{name}: {promoted} packaged-only rows counted as coins")

    sources.clusters = triangulate.cluster_records(sources.by_source())
    log(
        f"clusters: {len(sources.clusters)} "
        f"({sum(1 for c in sources.clusters if c.kind == 'coin')} coins)"
    )
    return sources


def _fetch_nbu(
    client: PoliteClient,
    sources: Sources,
    *,
    log: Callable[[str], None],
    warn: Callable[[str], None],
    since_year: int | None,
) -> None:
    date_from = f"01.01.{since_year}" if since_year else None
    try:
        cards = _nbu_cards(client, nbu.LOCALE_UK, date_from=date_from, warn=warn)
    except SourceUnreachableError as exc:
        warn(f"nbu unreachable: {exc}")
        sources.access[SOURCE_NBU] = "unreachable"
        return
    sources.nbu = [nbu.card_to_record(card) for card in cards]
    sources.access[SOURCE_NBU] = "live"
    log(f"nbu: {len(sources.nbu)} cards")

    try:
        english = _nbu_cards(client, nbu.LOCALE_EN, date_from=date_from, warn=warn)
    except SourceUnreachableError as exc:
        # An English title is worth having and no coin depends on it; the
        # rolls do carry coins, so they are read either way.
        warn(f"nbu english unreachable: {exc}")
        english = []
    sources.nbu_english = {
        card.nbu_id: NbuEnglish(title=official_title(card.title), series=_tidy_english(card.series))
        for card in english
        if card.nbu_id
    }
    log(f"nbu english: {len(sources.nbu_english)} cards")
    _fetch_nbu_rolls(client, sources, log=log, warn=warn, date_from=date_from)


def _fetch_nbu_rolls(
    client: PoliteClient,
    sources: Sources,
    *,
    log: Callable[[str], None],
    warn: Callable[[str], None],
    date_from: str | None,
) -> None:
    """The souvenir listing, read for the coins inside the rolls.

    Circulation commemoratives have no card of their own; the roll they are
    sold in does. Only roll cards are kept — the rest of the souvenir listing
    is packaging, and packaging is not a coin.
    """
    try:
        cards = _nbu_cards(
            client, nbu.LOCALE_UK, date_from=date_from, warn=warn, category=nbu.CATEGORY_SOUVENIR
        )
    except SourceUnreachableError as exc:
        warn(f"nbu souvenirs unreachable: {exc}")
        return
    try:
        english_cards = _nbu_cards(
            client, nbu.LOCALE_EN, date_from=date_from, warn=warn, category=nbu.CATEGORY_SOUVENIR
        )
    except SourceUnreachableError as exc:
        warn(f"nbu english souvenirs unreachable: {exc}")
        english_cards = []
    english = {card.nbu_id: card.title for card in english_cards if card.nbu_id}

    rolls = 0
    for card in cards:
        record = nbu.card_to_record(card)
        name_en = roll_coin_english(english.get(record.source_id))
        coin = roll_coin(record)
        if coin is None:
            continue
        sources.nbu.append(coin)
        if name_en:
            sources.nbu_english.setdefault(coin.source_id, NbuEnglish(title=name_en, series=None))
        rolls += 1
    log(f"nbu rolls: {rolls} circulation commemoratives read off their roll cards")


def _nbu_cards(
    client: PoliteClient,
    locale: str,
    *,
    date_from: str | None,
    warn: Callable[[str], None],
    category: str = nbu.CATEGORY_COIN,
) -> list[nbu.NbuCard]:
    cards: list[nbu.NbuCard] = []
    page_number = 1
    page_count: int | None = None
    url = nbu.search_url(locale)
    while page_count is None or page_number <= page_count:
        form = nbu.search_form(page_number, category=category, date_from=date_from)
        result = client.post(url, form)
        if not result.ok:
            warn(f"nbu {locale} {category} page {page_number}: HTTP {result.status}")
            break
        parsed = nbu.parse_search_page(result.text)
        page_count = parsed.page_count or 1 if page_count is None else page_count
        if not parsed.cards:
            warn(f"nbu {locale} {category} page {page_number}: no cards parsed")
            break
        cards.extend(parsed.cards)
        page_number += 1
    return cards


def _tidy_english(name: str | None) -> str | None:
    """The English site shouts some series names ("THE UKRAINIAN STATE")."""
    if not name:
        return None
    return name.title() if name.isupper() else name


def _fetch_ua_coins(
    client: PoliteClient,
    sources: Sources,
    *,
    log: Callable[[str], None],
    warn: Callable[[str], None],
    mode: str,
) -> None:
    if mode == MODE_SKIP:
        sources.access[SOURCE_UA_COINS] = "skipped"
        return
    fetch: Callable[[str], FetchResult] = client.get
    access = "live"
    if mode != MODE_LIVE:
        probe: FetchResult | None = None
        try:
            probe = client.get(ua_coins.catalog_url("all")) if mode == MODE_AUTO else None
        except SourceUnreachableError as exc:
            warn(f"ua-coins unreachable ({exc.reason}); using the Wayback Machine copy")
        if probe is None or not probe.ok:
            access, fetch = "wayback", client.get_archived

    def page(url: str, label: str) -> FetchResult | None:
        try:
            result = fetch(url)
        except SourceUnreachableError as exc:
            warn(f"ua-coins {label}: {exc}")
            return None
        if not result.ok:
            warn(f"ua-coins {label}: HTTP {result.status} for {url}")
            return None
        return result

    uk_page = page(ua_coins.catalog_url("all", ua_coins.LOCALE_UK), "catalog uk")
    rows_uk = ua_coins.parse_catalog_page(uk_page.text) if uk_page else []
    if not rows_uk:
        warn("ua-coins: the all-years page gave no rows, falling back to year pages")
        for year in range(FIRST_YEAR, date.today().year + 1):
            result = page(ua_coins.catalog_url(year, ua_coins.LOCALE_UK), f"catalog uk {year}")
            if result:
                rows_uk.extend(ua_coins.parse_catalog_page(result.text))
    ru_page = page(ua_coins.catalog_url("all", ua_coins.LOCALE_RU), "catalog ru")
    rows_ru = ua_coins.parse_catalog_page(ru_page.text) if ru_page else []

    sources.ua_coins = ua_coins.rows_to_records(rows_uk, rows_ru)
    sources.access[SOURCE_UA_COINS] = access
    log(f"ua-coins: {len(sources.ua_coins)} rows [{access}]")


def _fetch_wikipedia(
    client: PoliteClient,
    sources: Sources,
    *,
    log: Callable[[str], None],
    warn: Callable[[str], None],
) -> None:
    records: list[SourceRecord] = []
    for page_title in (wikipedia.PAGE_PRECIOUS, wikipedia.PAGE_BASE):
        try:
            result = client.get(wikipedia.page_url(page_title))
        except SourceUnreachableError as exc:
            warn(f"wikipedia unreachable: {exc}")
            sources.access[SOURCE_WIKIPEDIA] = "unreachable"
            return
        if not result.ok:
            warn(f"wikipedia {page_title}: HTTP {result.status}")
            continue
        records.extend(wikipedia.parse_list_page(result.text, page_title))
    sources.wikipedia = records
    sources.access[SOURCE_WIKIPEDIA] = "live"
    log(f"wikipedia: {len(records)} rows")
