# External integrations

Where outside data comes from, who fetches it, and the rules it must pass before it
reaches the database.

## Who does what

Scheduled scraping does **not** run in this repository. It lives in the sibling
repository **`coin-parser`** (`collector/`), runs on the server's crontab
(`coin-parser/deploy/crontab`) in its own containers
(`deploy/docker-compose.collector.yml`), writes straight into this project's Postgres and
MinIO, and reports every run to this API (`admin.md`, "Job runs").

| Source | Gives | Job (`coin-parser`) | Schedule (UTC) | Writes |
|---|---|---|---|---|
| NBU rates API | USD/EUR → UAH rates | `update-rates` (`collector/rates/`) | every 5 h, `:25` | `exchange_rates` |
| NBU numismatic catalog | new Ukrainian issues, official names, photos, specs | `nbu-catalog-sync` (`collector/countries/ua/catalog_sync.py`) | daily 10:40 | `catalog_items` (drafts), `media_files`, MinIO |
| UA-Coins (ua-coins.info) | daily market prices of Ukrainian coins | `update-prices` (`collector/countries/ua/update_prices.py`) | daily 07:10 | `market_price_snapshots` |
| uCoin.net | user import of personal positions | — not implemented, deferred (`product.md`, "Out of scope") | — | — |

The server's cron has no timezone support, so the hours are written in UTC by hand;
the reasoning for each hour is in the crontab comments.

What this repository does with that data:

- reads `exchange_rates` through `RateRepository` (`app/repositories/rates.py`) —
  the "last rate on or before the date" rule is here, not in the parser
  (`business-rules.md`, BR-6);
- reads `market_price_snapshots` for prices and collection value
  (`business-rules.md`, BR-7);
- shows drafts from the NBU sync to admins for review (`admin.md`, "Draft review");
- records job runs and alerts in Telegram (`admin.md`).

The shared catalog and its prices are filled **only** by these jobs and by admins.
User actions never add shared records (`business-rules.md`, BR-2).

---

## NBU — exchange rates

```
GET https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?json&start=YYYYMMDD&end=YYYYMMDD&valcode=USD&sort=exchangedate&order=desc
```

- Only `USD` and `EUR`. One range request per currency per run, regardless of the
  window size.
- `rate` is parsed as `Decimal` straight from the JSON text
  (`json.loads(..., parse_float=Decimal)`), never through `float`.
  `exchangedate` (`DD.MM.YYYY`) is converted to ISO.
- Upsert: `INSERT ... ON CONFLICT (currency_code, effective_date, source) DO UPDATE` —
  the latest NBU answer always wins.
- Default window: the last 14 days, so a missed run heals on the next one. A backfill
  from any date is a manual run with `--start` / `--end`.

API docs: https://bank.gov.ua/ua/open-data/api-dev

---

## NBU — numismatic catalog

**The canonical source of the shared catalog for Ukraine.** Plain HTML, no JavaScript,
no Cloudflare — parsed with `httpx` + `selectolax`.

### The source

The search results come from one POST endpoint:

```
POST https://bank.gov.ua/ua/component/source/searchSouvenierCoinResult
     page=1&perPage=100&category[]=Coin
```

- `perPage` accepts 5/10/25/100. Filters: `serie[]`, `metal[]`, `nominal[]`,
  `quality[]`, `from`/`to` (`DD.MM.YYYY`, minimum `07.05.1995`), `search`.
  **Empty filter values break the request (404)** — send only filters in use.
- There are no per-coin pages: each listing card carries the title, series tag,
  denomination, issue date, material, mintage (`announced/actual`), artists, weight,
  diameter, quality, edge and description.
- The card id is in the preview path (`/media/coins/{id}/avers.jpg`); the letter code is
  in the full-size file path (`/files/coins_images/{code}a.png|{code}r.png`, 1600×1600
  PNG). Previews are ~200 px.
- Since 2022, base-metal coins are listed only as "… у сувенірному пакованні" — there's
  no separate card for the plain coin, so that card *is* the coin. Pairs of plain and
  packaged cards are linked by `packaging_of_id` (`business-rules.md`, BR-15).

### The daily sync (`nbu-catalog-sync`)

A shallow check, then deep work only when something is new:

1. Fetch the 25 most recent coin cards.
2. Compare their `nbu:<id>` source keys with `catalog_items.source_key`. Nothing new →
   done.
3. For each new id: find its official series, parse that whole series, match it to
   UA-Coins, fetch prices and photos, and process photos (background removal, sizes —
   `media.md`).
4. A card enters the catalog only if both obverse and reverse passed photo review;
   otherwise it becomes a warning in the run report.
5. Upload media to MinIO (`media_files.source = 'nbu'`, stored, not hotlinked) and insert
   the card as a **draft** (`status = 'draft'`, `created_by = NULL`), then load its
   prices. An admin publishes or rejects the draft (`admin.md`, "Draft review").

Report stats: `scanned`, `known`, `new`, `drafted`, `uploaded`, `warnings`.

### Loader rules (`load_cards.py`)

Shared by the daily sync and manual series loads:

- Matching is by `source_key` (`nbu:<id>`).
- On update, source-owned columns (titles and their `*_source`, denomination, dates,
  mintage, material, weight, diameter, edge, quality, descriptions, artists) are
  rewritten from the source — **except** fields listed in the record's
  `edited_fields`.
- **Known gap:** nothing in this app writes `edited_fields` yet. An admin edit through
  `PATCH /catalog/{id}` sets `*_source = 'manual'` on titles, but the loader doesn't
  check `*_source`, so re-loading that series overwrites the edit (`backlog.md`).
- Never written: catalog numbers, `notes`, `subtype`, `status` of an existing row, and
  the archive columns. `collection_group`, `country_id` and `created_by` are set only on
  insert.
- Official Ukrainian titles are stored with `*_source = 'official'`.

### The sync never deletes and never archives

The loader doesn't write archive columns at all. Discontinued issues stay as they are;
archiving is an admin action (`business-rules.md`, BR-10). Probable duplicates are not
detected automatically — admins close them by archiving with a "duplicate" reason.

### Scope

Ukraine only. US and USSR records in the shared catalog come from the initial seed
(`data-model.md`, "Data origins") and are maintained by admins by hand; those countries
are `catalog_confirmed = false` (`business-rules.md`, BR-13a).

Source: https://bank.gov.ua/ua/numismatic-products

---

## UA-Coins — market prices

**The price source of the shared catalog.** Plain HTML without Cloudflare, so it's fit
for scheduled scraping. The site doesn't answer from some networks outside Ukraine; for
local investigation use Wayback Machine copies (`web.archive.org`), which can lag the
live site by weeks.

### Useful pages

| Page | URL | Gives |
|---|---|---|
| whole catalog | `/ua/catalog/all/all` | ~1060 rows, all years, one request |
| catalog by year | `/ua/catalog/all/{year}` | same rows for one year |
| same in Russian | `/catalog/all/all`, `/catalog/all/{year}` | Russian names with the same ids |
| series | `/ua/categories/all`, `/en/categories/all` | 38 series with counts and total mintage |
| coin page | `/ua/list/{id}-{slug}` | specs table, series, today's price |
| NBU release plan | `/ua/nbu-plan-list` | by year |

A table row (`td[data-title]`): "Дата" (`dd.mm.yyyy`), "Номінал" (`5 грн.`,
`200000 крб.`), "Тираж тис." in thousands as `announced/actual`, "Назва" linking to
`/ua/list/{id}-{slug}`, "Вартість dd.mm.yyyy" (number with thin spaces, trend arrow, or
"немає даних" = no quote). Series and metal are only on coin and series pages. Sets and
souvenir-packaged coins appear as separate rows.

### The daily job (`update-prices`)

1. **Scope comes from the database:** active shared `catalog_items` with
   `source_key LIKE 'nbu:%'` whose series is in `coin-parser`'s finished list
   (`db_map.json`, `completed`). A series joins that list by hand, after it's loaded
   and verified — quoting a coin through an unverified link is how a price lands on the
   wrong coin.
2. Download the yearly tables for the years those coins were issued (±1) — one request
   per year, up to 3 attempts.
3. Each coin finds its row **by the UA-Coins id** stored in `price_source_links`. Nothing
   is re-matched by title at night: matching is a one-time, reviewed decision.
4. Quotes go into `market_price_snapshots` with `created_by = NULL` (visible to
   everyone), through the same batch insert as manual price loads, so reruns collapse
   instead of duplicating.

Archived records are out of scope, so their price history freezes; an unarchived
record re-enters on its own. The downloaded HTML is kept on the server for a few days
for investigation. Exit codes: `0` ok, `1` partial, `2` nothing done.

---

## Price validation

A price is validated **before** it's written. A price that fails is not written to
`market_price_snapshots`; it's reported with the source's raw text instead.

What `coin-parser` enforces today:

| Check | Where | On failure |
|---|---|---|
| The cell parses as a number | `ua_coins.parse_price_cell` | "немає даних" or junk → no quote |
| `price > 0` | same, and `prices._coerce_price` | no quote / series anomaly |
| `price < 10^12` (fits `numeric(14,2)`) | `update_prices.build_rows`, `prices._coerce_price` | `no_quote:unusable` |
| The quote belongs to this coin | matched by stored UA-Coins id, never by title | `no_link` / `no_quote:not_listed` |

Every row keeps a `raw_payload` (date, price, source table year) and `source_url`.

`coin-parser` never sets `is_suspect`: the market is thin and spikes are real trades.
`is_suspect` exists only for the seeded history (`data-model.md`, "Data origins").

**When adding any new price source or write path** (manual entry, import — both
deferred), validate on every path the same way and additionally reject:

- a number that looks like a year (1900–2100) or has more than 7 digits without
  separators — typical glued-number parser bugs;
- a value with no explicit currency marker (`₴`, `грн`, `UAH`);
- a value more than ~10× away from the median of the item's recent snapshots — return
  `rejected` for manual review instead of writing it.

---

## uCoin.net (deferred)

uCoin import of **personal positions** is post-MVP (`product.md`, "Out of scope"). Constraints any
implementation must keep:

- **Never a scheduled server-side crawl**: uCoin is behind Cloudflare and the data and
  images aren't ours. Only a user-initiated import, filling only that user's personal
  positions, with deduplication against the shared catalog (`business-rules.md`, BR-3).
- Images keep `source = 'ucoin'` and are visible only to the importer (`media.md`).
- **Excel export is the reliable path.** Sheet `Collection`; columns: 1 country,
  2 series, 4 denomination, 5 year, 6 variety, 7 title, 10 market price, 11 catalog
  number. Skip rows with no country, denomination or year.
- **Page scraping needs a headless browser** (JavaScript + Cloudflare). Retry while the
  page says "just a moment" / "enable javascript" for up to ~45 s, then fail with a
  suggestion to use the Excel path. Keep at least 450 ms between requests.
- Normalise URLs: language subdomains are the same coin
  (`source_key = ucoin:<normalised host><path>[?tid=<tid>]`).

## Numista (not used)

Requires a personal API key per user; a service-wide key would break their terms. Not
integrated. Docs: https://en.numista.com/api/doc/index.php

---

## Rules for every external source

- External sites are called only from background jobs, never inside an HTTP request
  handler of this API.
- Timeouts, bounded retries, a pause between requests to the same host, an honest
  User-Agent (`coin-parser` sends `coin-collector/0.1 (personal project)`).
- Scheduled scraping only for sources without Cloudflare and with acceptable terms: NBU
  and UA-Coins.
- No external source creates **shared** catalog records except the NBU catalog sync, and
  that one creates drafts.
- Keep the raw response next to what was parsed from it — without it, a bad value can't
  be investigated.

## Other outbound services

Not data sources, listed for completeness: Google OAuth (`auth.md`), Telegram Bot API
(`admin.md`, `telegram-support.md`), the Anthropic API for background name translation
(`claude-haiku-4-5`, `app/services/translation.py`; `business-rules.md`, BR-16), SMTP
(`infra.md`).
