"""Build a miniature legacy database for the migration tests.

The owner's real database is not in the repository and never will be, so the
migration is developed against this synthetic fixture. The DDL is the real one
from legacy/legacy-schema.sql; only the rows are invented.

Rows are chosen to cover the edge cases the migration has to survive:

* a glued price and a price that is really a year (is_suspect rules),
* a timestamp without a zone next to one with a zone,
* invalid JSON in raw_payload_json,
* media as an external URL, as a local file that exists, and as a local file
  that is gone -- local paths are full Windows paths, the way the desktop
  application actually stored them, plus one with forward slashes,
* a catalog row with a NULL metal_kind, which is NOT NULL in the new schema,
* a price snapshot whose currency_code is not in `currencies` — SQLite leaves
  foreign keys unenforced by default, so the real database may hold one,
* a coin whose catalog row is known to come from uCoin, and one that is not.

Enum values are all lower case here, because the legacy CHECK constraints only
ever allowed lower case — the schema physically could not hold anything else.
The case-normalising in convert.to_enum_value stays as a cheap guard and is
covered by its own unit test rather than through this fixture.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LEGACY_SCHEMA = REPO_ROOT / "legacy" / "legacy-schema.sql"

# Kept in sync with the fixture rows below; the tests assert against these.
EXPECTED_EXPENSE_SUM = "1234.56"
EXPECTED_COUNTS = {
    "catalog_items": 6,
    "collection_items": 3,
    "market_price_snapshots": 8,
    "expenses": 3,
    "exchange_rates": 2,
    "price_source_links": 2,
    "media_files": 6,
    "ucoin_catalog_sources": 1,
    "countries": 2,
    "currencies": 2,
    "denominations": 2,
    "coin_series": 2,
}

# What the migration is expected to actually write, which is not always the
# source count:
#   * one price snapshot references a currency that is not in `currencies`.
#     SQLite does not enforce foreign keys unless asked, so the real database
#     can hold such a row; PostgreSQL would refuse it, so the migration drops
#     it and says so.
#   * one media row points at a file that no longer exists, so it is dropped:
#     no file and no link means nothing to point at.
EXPECTED_MIGRATED = {
    **EXPECTED_COUNTS,
    "market_price_snapshots": 7,
    "media_files": 5,
}
# --skip-media defers the media step entirely, so no rows are written.
EXPECTED_MIGRATED_SKIP_MEDIA = {
    **EXPECTED_MIGRATED,
    "media_files": 0,
}

# Ids used by the handwritten catalog rows; filler starts after them.
FIXTURE_CATALOG_IDS = (1, 2, 3, 4, 5, 6)

MISSING_MEDIA_FILENAME = "404_obverse_ffffffffffffffffffffffffffffffff.jpg"
PRESENT_MEDIA_FILENAME = "1023_obverse_eb5c6f1c1ed041d9bbf86fe77855243b.jpg"
COLLECTION_MEDIA_FILENAME = "2001_reverse_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg"
POSIX_MEDIA_FILENAME = "3005_obverse_bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.jpg"

# The desktop application ran on Windows and stored absolute paths, not bare
# file names: drive letter, backslashes, and a space in "CoinKeeper Data". The
# fixture uses that shape because the first real dry run found not a single
# file when it did not.
WINDOWS_MEDIA_ROOT = r"C:\Users\<user>\AppData\Roaming\CoinKeeper Data\media"
# One row with forward slashes, in case the collection is ever exported from a
# machine that writes them.
POSIX_MEDIA_ROOT = "/home/<user>/.config/CoinKeeper Data/media"


def windows_path(file_name: str) -> str:
    return f"{WINDOWS_MEDIA_ROOT}\\{file_name}"


def posix_path(file_name: str) -> str:
    return f"{POSIX_MEDIA_ROOT}/{file_name}"


def _schema_statements() -> list[str]:
    """Real DDL from the repository, minus the parts SQLite cannot re-run."""
    raw = LEGACY_SCHEMA.read_text(encoding="utf-8")
    statements = [chunk.strip() for chunk in raw.split(";") if chunk.strip()]
    return [
        statement
        for statement in statements
        if statement.upper().startswith(("CREATE TABLE", "CREATE INDEX"))
        and "sqlite_" not in statement
    ]


def build(path: Path, *, extra_catalog_items: int = 0) -> Path:
    """Create the fixture database at `path` and return it.

    `extra_catalog_items` pads catalog_items with filler rows. It exists for one
    reason: a multi-row INSERT spends a bind parameter per column per row, and
    PostgreSQL caps a statement at 32767 of them. catalog_items is 32 columns
    wide, so anything past roughly a thousand rows has to be split across
    statements. Padding lets a test reach that size without carrying a real
    database around.
    """
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        for statement in _schema_statements():
            connection.execute(statement)
        _insert_rows(connection)
        if extra_catalog_items:
            _insert_filler_catalog_items(connection, extra_catalog_items)
        connection.commit()
    finally:
        connection.close()
    return path


def _insert_filler_catalog_items(connection: sqlite3.Connection, count: int) -> None:
    """Plain, valid catalog rows whose only job is to make the table large.

    Ids start above the handwritten ones so nothing collides, and every row is
    complete enough to migrate: the point is the row count, not new edge cases.
    """
    first_id = max(FIXTURE_CATALOG_IDS) + 1
    connection.executemany(
        "INSERT INTO catalog_items (id, country_id, series_id, denomination_id, "
        "collection_group, title_original, issue_year, source_key, metal_kind, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                first_id + offset,
                1,
                None,
                1,
                "circulation",
                f"Filler coin {offset}",
                2000 + offset % 25,
                f"fixture:filler:{offset}",
                "base",
                "2024-02-01 09:00:00",
                "2024-02-01 09:00:00",
            )
            for offset in range(count)
        ],
    )


def _insert_rows(connection: sqlite3.Connection) -> None:
    cur = connection.cursor()

    cur.executemany(
        "INSERT INTO currencies (code, name, symbol, decimal_places) VALUES (?,?,?,?)",
        [("UAH", "Hryvnia", "UAH", 2), ("USD", "US Dollar", "$", 2)],
    )
    cur.executemany(
        "INSERT INTO countries (id, code, name_original, name_ru, name_en, "
        "collect_variants, is_active, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (
                1,
                "UA",
                "Ukraine",
                "Украина",
                "Ukraine",
                0,
                1,
                "2024-01-01 10:00:00",
                "2024-01-01 10:00:00",
            ),
            (2, "US", "USA", "США", "USA", 0, 1, "2024-01-01T10:00:00Z", "2024-01-01T10:00:00Z"),
        ],
    )
    cur.executemany(
        "INSERT INTO denominations (id, country_id, currency_code, value_minor_units, "
        "label_original, label_ru, label_en, sort_order, is_active) VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (1, 1, "UAH", 200, "2 гривні", "2 гривны", "2 hryvnia", 1, 1),
            (2, 2, "USD", 1, "1 cent", "1 цент", "1 cent", 2, 1),
        ],
    )
    cur.executemany(
        "INSERT INTO coin_series (id, country_id, name_original, name_ru, name_en, "
        "description, start_year, end_year, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            (
                1,
                1,
                "Флора і фауна",
                "Флора и фауна",
                "Flora and fauna",
                None,
                2010,
                2020,
                "2024-01-01 10:00:00",
                "2024-01-01 10:00:00",
            ),
            (
                2,
                2,
                "American Women",
                None,
                "American Women",
                None,
                2022,
                2025,
                "2024-01-01 10:00:00",
                "2024-01-01 10:00:00",
            ),
        ],
    )

    catalog = [
        # id, country, series, denom, group, title, year, source_key, metal_kind
        (1, 1, 1, 1, "commemorative", "Дельфін", 2018, "ucoin:ua|2 гривні|2018||дельфін|", "base"),
        (
            2,
            1,
            1,
            1,
            "circulation",
            "Обігова",
            2015,
            "ucoin:uk.ucoin.net/coin/ua-2uah-2015",
            "base",
        ),
        # No source key and no uCoin link: its local photo is the owner's own.
        (3, 1, None, 1, "collector", "Власна монета", 2020, None, "precious"),
        (4, 2, 2, 2, "circulation", "Lincoln cent", 2009, "ucoin:us|1 cent|2009||lincoln|", "base"),
        # metal_kind NULL: nullable in the legacy schema, NOT NULL in the new
        # one, so the migration has to supply 'unknown'.
        (5, 2, 2, 2, "circulation", "Quarter", 2022, None, None),
        (6, 1, None, 1, "other", "Дублікат ключа", 2019, None, "unknown"),
    ]
    cur.executemany(
        "INSERT INTO catalog_items (id, country_id, series_id, denomination_id, "
        "collection_group, title_original, issue_year, source_key, metal_kind, "
        "created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [(*row, "2024-02-01 09:00:00", "2024-02-01 09:00:00") for row in catalog],
    )

    cur.executemany(
        "INSERT INTO exchange_rates (id, currency_code, rate_uah, effective_date, "
        "fetched_at, source) VALUES (?,?,?,?,?,?)",
        [
            (1, "USD", 41.123456, "2026-08-06", "2026-08-06T12:00:00Z", "NBU"),
            (2, "USD", 40.5, "2026-08-05", "2026-08-05 12:00:00", "NBU"),
        ],
    )

    snapshots = [
        # Three sane prices on item 1 give a median for the deviation rule.
        (1, 1, "uCoin", 666.00, "UAH", "2026-08-01T10:00:00Z", '{"text":"666 грн"}'),
        (2, 1, "uCoin", 700.00, "UAH", "2026-08-02T10:00:00Z", '{"text":"700 грн"}'),
        (3, 1, "uCoin", 650.00, "UAH", "2026-08-03T10:00:00Z", None),
        # Glued number: range + digit run + deviation.
        (4, 1, "uCoin", 12001500.00, "UAH", "2026-08-04T10:00:00Z", '{"text":"12001500"}'),
        # Price equal to the coin's own issue year.
        (5, 2, "uCoin", 2015.00, "UAH", "2026-08-04 11:00:00", None),
        # Zero: out of range.
        (6, 3, "Manual", 0.00, "UAH", "2026-08-04 12:00:00", None),
        # Invalid JSON payload.
        (7, 4, "uCoin", 12.50, "USD", "2026-08-05T10:00:00Z", "{not valid json"),
        # Unknown currency code: currency rule.
        (8, 5, "uCoin", 30.00, "XYZ", "2026-08-05 13:00:00", None),
    ]
    cur.executemany(
        "INSERT INTO market_price_snapshots (id, catalog_item_id, source, price, "
        "currency_code, observed_at, raw_payload_json) VALUES (?,?,?,?,?,?,?)",
        snapshots,
    )

    cur.executemany(
        "INSERT INTO price_source_links (id, catalog_item_id, source, external_id, "
        "match_status, matched_at) VALUES (?,?,?,?,?,?)",
        [
            (
                1,
                1,
                "uCoin",
                "https://uk.ucoin.net/coin/ua-2uah-2018-dolphin",
                "confirmed",
                "2026-08-01T10:00:00Z",
            ),
            (
                2,
                4,
                "uCoin",
                "https://ru.ucoin.net/coin/usa-1-cent-2009",
                "confirmed",
                "2026-08-01 10:00:00",
            ),
        ],
    )

    cur.executemany(
        "INSERT INTO collection_items (id, catalog_item_id, quantity, acquisition_date, "
        "purchase_price, purchase_currency, purchase_rate_uah, is_for_swap, "
        "needs_replacement, is_for_sale, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                1,
                1,
                1,
                "2021-05-01",
                666.00,
                "UAH",
                1.0,
                0,
                0,
                0,
                "2021-05-01 12:00:00",
                "2021-05-01 12:00:00",
            ),
            (
                2,
                3,
                1,
                "2022-06-15",
                500.00,
                "UAH",
                1.0,
                1,
                0,
                0,
                "2022-06-15T12:00:00Z",
                "2022-06-15T12:00:00Z",
            ),
            (
                3,
                4,
                1,
                "2023-07-20",
                68.56,
                "UAH",
                1.0,
                0,
                1,
                0,
                "2023-07-20 12:00:00",
                "2023-07-20 12:00:00",
            ),
        ],
    )
    cur.executemany(
        "INSERT INTO expenses (id, category, amount, currency_code, rate_uah, "
        "expense_date, catalog_item_id, collection_item_id, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [
            (1, "coin_purchase", 666.00, "UAH", 1.0, "2021-05-01", 1, 1, "2021-05-01 12:00:00"),
            (2, "coin_purchase", 500.00, "UAH", 1.0, "2022-06-15", 3, 2, "2022-06-15 12:00:00"),
            (3, "coin_purchase", 68.56, "UAH", 1.0, "2023-07-20", 4, 3, "2023-07-20 12:00:00"),
        ],
    )

    cur.executemany(
        "INSERT INTO media_files (id, catalog_item_id, collection_item_id, role, "
        "original_path, thumbnail_path, mime_type, width, height, sha256, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            # External hotlink on i.ucoin.net.
            (
                1,
                1,
                None,
                "obverse",
                "https://i.ucoin.net/coin/50/796/50796073-1s/usa-1-cent-2009.jpg",
                None,
                "image/jpeg",
                200,
                200,
                None,
                "2024-03-01 09:00:00",
            ),
            # Local file that exists, on a coin known to come from uCoin.
            (
                2,
                1,
                None,
                "reverse",
                windows_path(PRESENT_MEDIA_FILENAME),
                None,
                "image/jpeg",
                300,
                300,
                None,
                "2024-03-01 09:00:00",
            ),
            # Local file that exists, on a coin with no uCoin trace: owner's own.
            (
                3,
                3,
                None,
                "obverse",
                windows_path(COLLECTION_MEDIA_FILENAME),
                None,
                "image/jpeg",
                300,
                300,
                None,
                "2024-03-01 09:00:00",
            ),
            # Local file that is gone: one of the 842 lost in the archive.
            (
                4,
                4,
                None,
                "obverse",
                windows_path(MISSING_MEDIA_FILENAME),
                None,
                "image/jpeg",
                300,
                300,
                None,
                "2024-03-01 09:00:00",
            ),
            # Another external link, different domain.
            (
                5,
                5,
                None,
                "reverse",
                "http://example.com/photo.jpg",
                None,
                "image/jpeg",
                100,
                100,
                None,
                "2024-03-01 09:00:00",
            ),
            # Forward slashes with a space in the directory: the same file name
            # has to come out of either convention.
            (
                6,
                6,
                None,
                "obverse",
                posix_path(POSIX_MEDIA_FILENAME),
                None,
                "image/jpeg",
                300,
                300,
                None,
                "2024-03-01 09:00:00",
            ),
        ],
    )

    cur.executemany(
        "INSERT INTO ucoin_catalog_sources (id, title, url, country, collection_group, "
        "last_scanned, last_inserted, last_updated, last_skipped, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                1,
                "Ukraine commemorative",
                "https://uk.ucoin.net/catalog/ua",
                "Ukraine",
                "commemorative",
                10,
                5,
                3,
                2,
                "2024-04-01 09:00:00",
                "2024-04-01 09:00:00",
            ),
        ],
    )

    cur.executemany(
        "INSERT INTO settings (key, value_json, updated_at) VALUES (?,?,?)",
        [
            ("display_currency", '"UAH"', "2024-05-01 09:00:00"),
            ("default_grade_circulation", '"XF"', "2024-05-01 09:00:00"),
        ],
    )
