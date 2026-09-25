# Business rules

The rules the backend enforces. Each rule has a stable ID (`BR-N`); cite it from code as
`docs/business-rules.md, BR-N`. IDs are never renumbered — a retired rule keeps its
number unused.

Schema details: `data-model.md`. Endpoint contracts: `api.md`.

---

## BR-1. Catalog vs collection

- A **catalog item** describes a coin issue. It exists regardless of who owns it.
- A **collection item** is a specific purchase of a specific user, with a `quantity`.
- One catalog item → many collection items (different users, or one user buying twice).

Catalog items are **shared** (`created_by IS NULL`, visible to everyone) or **personal**
(`created_by = <user>`, visible only to the author). A collection item may point at
either kind.

## BR-2. Who creates catalog records

### Shared catalog — admins and system jobs only

Shared records are created, edited and archived only by admins and by the NBU catalog
sync in `coin-parser`. For everyone else the shared catalog is **read-only**; an attempt
to change it returns `403`. Shared records are archived, never deleted in normal work
(BR-10).

The shared catalog grows two ways:

1. **The initial seed** — the owner's migrated catalog (`data-model.md`, "Data origins").
2. **The NBU catalog sync** — enriches existing records and adds new issues as
   `status = 'draft'`. Drafts are invisible to non-admins (storefront, search,
   completeness) until an admin publishes them; rejecting a draft archives it with a
   reason (`admin.md`).

Price updates and user actions never add shared records.

**Series** belong to the shared catalog: there are no personal series and only admins
create them. A personal position can reference an existing series, or carry free text
in `series_text` (BR-14), which is shown but never counted.

### Personal positions — full CRUD for the author

When an issue isn't in the shared catalog, the user creates a **personal position**
(`created_by = <user>`). It is visible only to its author, fully editable and
deletable by them, has its own photos, and counts in the author's filters, search,
completeness and statistics exactly like a shared record.

A personal position is created **inside a purchase**, on the "Додати" page — there is
no standalone "create catalog item" screen. Technically it's one request,
`POST /collection` with a nested `newCatalogItem` (`api.md`): position, collection item
and expense are created in one transaction, so a rejected purchase never leaves an
orphan position.

Price updates never create positions in any layer: no match → `not-found`.

## BR-3. Import deduplication (not implemented — import is deferred)

Import (uCoin Excel export, uCoin page by URL) is post-MVP (`product.md`, "Out of scope"). When it's built,
it must follow this rule:

Import creates **personal positions only** and looks for an existing record in two
rounds:

1. **Shared catalog.** Match among `created_by IS NULL`. Found → create nothing; link the
   user's collection items to the shared record and take only data that doesn't touch
   the record itself (e.g. a price snapshot with `created_by = <user>`, BR-7).
2. **The user's personal positions.** Found → update it. Not found → create a new
   personal position.

Matching inside each round:

1. By `source_key`:
   ```
   uCoin Excel row:  ucoin:<country>|<denomination>|<year>|<variety>|<title>|<catalog no.>   (lower case)
   uCoin page:       ucoin:<hostname><pathname>[?tid=<tid>]   (hostname normalised)
   ```
2. Otherwise by natural key: country + denomination + year + lower(title), plus, when
   a catalog number is given, a match on the first non-empty of KM / UC / Numista. On
   several matches, prefer the one whose catalog number matched.

Updates never overwrite filled fields with empty ones (`COALESCE(new, old)` on
`series_id`, `subtype`, `catalog_km`, `material`, `source_key`). The whole import is
one transaction; the report is `scanned / inserted / updated / skipped + warnings[]`.

`source_key` uniqueness is per layer: global among shared records, per owner among
personal ones (two partial unique indexes, `data-model.md`).

## BR-4. Buying a coin

One transaction:

1. insert the `collection_items` row;
2. insert an `expenses` row, category `coin_purchase`, amount `unit price × quantity`,
   linked to both the catalog item and the new collection item.

**Currency.** The purchase keeps the price and currency the user entered
(`purchase_price`, `purchase_currency`) plus `purchase_rate_uah` — the NBU rate on the
purchase date (BR-6). The UAH amount is always computed: `purchase_price ×
purchase_rate_uah`. The original amount and currency are never lost.

**A coin that isn't in the catalog** adds a third step before the collection item:
insert the personal position (BR-2). Rates, currency and storage location are resolved
before the first insert, so a rejected purchase leaves nothing behind. Never split this
into two requests (`POST /catalog` then `POST /collection`) — a failure of the second
would leave junk in the user's catalog.

**Commit before background work.** The request session is a function-scoped
dependency (`DbSession` in `app/api/deps.py`): it commits when the route returns,
before the response is sent and before any `BackgroundTasks` run. The background title
translation opens its own session and always finds the committed rows, and a failing
background task can't roll the purchase back.

### Supporting expenses

A purchase can carry supporting expenses — shipping, holder, grading — each with its
own amount and currency, sharing the purchase's date and seller. Rates for **every**
currency in the request are resolved before the first insert: an expense in a currency
without a rate rejects the whole purchase.

- **The amount is per purchase, not per unit** — never multiplied by `quantity`. Cost
  per unit including extras is `(unit price × quantity + Σ supporting) / quantity`.
- **Linked like the purchase:** both `catalog_item_id` and `collection_item_id` are
  set. `collection_item_id` is what tells which purchase a shipping cost belongs to when
  the same catalog item was bought several times.
- **Deleting the collection item keeps them.** The service doesn't delete supporting
  expenses; `expenses.collection_item_id ON DELETE SET NULL` clears the link and the
  expense stays in "Гроші" with its `catalog_item_id` — the money was spent regardless.
- **Older rows** created before the link existed have `collection_item_id` backfilled
  (migration `0025`) only where `(owner_id, catalog_item_id)` has exactly one collection
  item; ambiguous ones stay `NULL` until the user fixes them.

**Counting them in "bought for".** `user_settings.include_supporting_expenses`
(default `true`): when on, the headline cost on the coin card and the base for value
change is `purchaseTotalUah + supportingExpensesUah`, with a note of how much of it is
extras; when off, the headline is `purchaseTotalUah` and extras are shown separately.
The same goes for the "Мої монети" positions and KPI tiles (spent and difference); the
overview's tiles ignore the setting — they are everything spent on the hobby.
The API always returns both sums unchanged — the setting only affects how the frontend
combines and labels them.

## BR-5. Completeness

A catalog item counts as **collected** when the user has at least one collection item
for it; quantity doesn't matter.

```
total     = COUNT(active catalog items in scope)
collected = COUNT(DISTINCT collection_items.catalog_item_id) for the user,
            intersected with the same active items in scope
missing   = MAX(0, total − collected)
percent   = ROUND(collected / total × 100, 1)      -- 0 when total = 0
```

- **Scope** = catalog items visible to the user (shared + own personal, BR-2),
  narrowed by the active filter or grouping (country, series, year, denomination,
  material, metal kind, edge, quality…; `api.md`, `/completeness/*`). Personal
  positions count like shared ones.
- **Numerator and denominator use the same set — active items** (`NOT is_archived`,
  published). Counting all of the user's instances against active items only would give
  "21 of 20". An instance of an archived item stays in the collection, spend and value,
  but not in completeness (BR-10).
- **Varieties.** `countries.collect_variants` would make each variety its own required
  item. The flag exists; the mode is not implemented (`product.md`, "Out of scope").

## BR-6. Exchange rates

Source: the NBU API, loaded by `coin-parser` into `exchange_rates` (`integrations.md`).
Only USD and EUR against UAH are stored; there is no direct USD↔EUR rate.

- A historical amount converts at the rate **on the purchase date**; on a non-banking
  day, the last rate published before it (`RateRepository.rate_on`).
- If NBU has no rate on or before that date, the converted amount is `null` — it is
  **never** filled in from a later rate.
- Current value uses the latest rate.
- The original amount and currency are always kept.

### Secondary display currency

UAH is the only currency sums are computed in (SQL aggregates for the dashboard,
catalog, "Гроші"); everything else is a conversion of the finished UAH number.
`user_settings.secondary_currency` (`USD` | `EUR`) picks which of the two
already-computed numbers the UI shows next to UAH — the API always returns both:

- at the purchase-date rate: `purchaseTotalUsd/Eur` (catalog item), `totalUsd/Eur`
  (collection item), `amountUsd/Eur` (expense row);
- at the latest rate: only current market value on the coin card.

## BR-7. Market prices

### Who updates prices

| Records | Updated by | How often |
|---|---|---|
| Shared catalog | the central job in `coin-parser`, source UA-Coins | daily |
| Personal positions | nobody yet — manual entry and per-position refresh are deferred (`product.md`, "Out of scope") | — |

The daily job visits **active** records only; an archived record's price history
freezes at archiving. There is no "update price" button for shared records, and no
server-side crawl of uCoin (`integrations.md`).

### Snapshot visibility

| `market_price_snapshots.created_by` | Source | Visible to |
|---|---|---|
| `NULL` | the central daily job | everyone |
| `<user>` | the user's own entry (manual, personal refresh, import) | the author only |

A user's collection is valued from shared snapshots **plus their own**; the current
price is the latest by `observed_at` among snapshots visible to them, so a fresher own
snapshot overrides a shared one. Snapshots with `is_suspect = true` are excluded
(`data-model.md`, "Data origins").

### History is append-only

Every check inserts a new snapshot row; nothing is overwritten.

### Conversion to UAH

```
currency_code = 'UAH' → price
otherwise             → price × latest rate for that currency
```

### Validation before writing

A price is validated **before** it's written, identically on every write path. A price
that fails is not written to `market_price_snapshots`: it's returned as `rejected` and
logged with the source's raw response. Checks and known parser pitfalls:
`integrations.md`, "Price validation".

### Default grade

One configurable default for all coins, `UNC` until the user changes it
(`user_settings.default_grade`). It pre-fills the purchase form and can be overridden
per purchase.

## BR-8. Finances

```
coin spend       = SUM(amount × COALESCE(rate_uah, 1)) where category = 'coin_purchase'
related spend    = SUM(amount × COALESCE(rate_uah, 1)) where category <> 'coin_purchase'
total spend      = coin spend + related spend

collection value = SUM(quantity × latest UAH price) over the user's collection items
missing budget   = SUM(latest UAH price) over visible catalog items the user doesn't own
unpriced missing = COUNT of visible catalog items the user doesn't own that have no price
```

"Latest price" = latest among snapshots visible to the user (BR-7). "Visible catalog
items" = shared + own personal, under the storefront rule (BR-13). "Unpriced missing"
tells the user how far the budget can be trusted. Every sum is scoped by `owner_id`.

## BR-9. Breakdowns

- **By country:** items per country, collected (`DISTINCT catalog_item_id`), top 6 by
  item count.
- **By series:** every series the user has started — no limit. The frontend sorts
  (least complete first, finished last, alphabetical among ties); trimming on the server
  would silently drop series from a personal collection.

## BR-10. Deletion and archiving

### Shared catalog: archive, don't delete

Shared records are **not deleted**. A record that no longer belongs in the storefront —
discontinued, duplicate, created by mistake — is **archived**: `is_archived = true`,
`archived_at`, and a required `archive_reason`. Other people's collection items,
purchases, expenses, photos and price history hang off it.

| | Archived shared record |
|---|---|
| Storefront, search, filters | hidden unless `archived=true` is requested |
| Completeness numerator and denominator | excluded (BR-5) |
| Daily price job, NBU catalog sync matching | skipped |
| Owners' collection items, purchases, expenses | kept and still counted |
| Collection value and spend | unchanged |
| Photos and price history | kept |
| Coin card for an owner | opens, with a banner "archived: <reason>" |

Archiving is reversible: `unarchive` clears the flag, `archived_at` and
`archive_reason`. Only admins archive and unarchive shared records (`auth.md`); both
actions go to `audit_log`. Duplicates are archived with a "duplicate" reason — merging
with re-pointing of instances is deferred (`product.md`, "Out of scope").

### Physical deletion of a shared record

A clean-up tool, not a workflow. All conditions at once, else `409`:

1. done by an admin;
2. the record is shared and **already archived**;
3. no `collection_items` or `expenses` reference it;
4. its `media_files` and `market_price_snapshots` go by cascade — they belong to the
   record, not to users.

### Personal positions and the rest

- **A personal position** is deleted physically by its author; archiving doesn't apply.
  In the same transaction the service deletes the author's collection items on it and
  their `coin_purchase` expenses — safe, since a personal position can't carry anyone
  else's data.
- The "can't delete an item with instances" guard lives **in the service layer**:
  `collection_items.catalog_item_id` is `ON DELETE NO ACTION` because of the cascade
  diamond on user deletion (`data-model.md`).
- **Deleting a collection item deletes its `coin_purchase` expense** with an explicit
  `DELETE` in the same transaction. `expenses.collection_item_id ON DELETE SET NULL` is
  only a safety net for that category — on its own it would keep the expense and
  inflate spend.
- **Supporting expenses are left alone** — `ON DELETE SET NULL` is exactly the intended
  behavior for them (BR-4).
- Deleting a user deletes their collection, expenses, photos and personal positions and
  never touches the shared catalog.
- Deleting a photo takes effect immediately and is not audited (`media.md`).

## BR-11. (retired)

Coin-group heuristics of the previous app. The resulting data was corrected once; no
code applies them now.

## BR-12. Language and Unicode

- Interface: `'uk' | 'en'`, default `'uk'`.
- Coin names: any language and script.
- **Three slots on every named entity** (countries, series, coins): `*_original` in the
  issuer's language (plus `original_lang`) and two translations, `*_uk` and `*_en`, each
  with a `*_source` (`official | llm | manual`). The original is never translated — it's
  what the issuer called the coin.
- **Russian is not a separate language.** There are no `*_ru` columns. For Soviet
  coins Russian *is* the original (`original_lang = 'ru'`).
- **Display name** = `title_<locale>` → `title_original`, nothing beyond that. Response
  locale: `?locale=`, else `Accept-Language`, else `uk` (`data-model.md`).
- When the displayed name is a translation, the card also shows the original and its
  language, so the reader knows it's a translation.
- Search covers the original, both translations and catalog numbers at once
  (full-text config `simple`, `data-model.md`).

## BR-13. Country visibility and the storefront rule

`countries.is_active` is the **storefront switch**: the country chips in catalog filters
and what the catalog shows by default. Only Ukraine is active; a country that existed
before the seed keeps its state and `id`. Countries are ordered by `sort_order`
(Ukraine = 0), then by name in the reader's locale.

The purchase form offers **all** issuers (about 260, ISO 3166-1 plus historical ones),
searchable by any of the three names and by code: a personal position may be any
issuer's coin.

### The storefront rule

A catalog record is visible in listings and aggregates if **any** holds:

1. its country is active;
2. it's the current user's personal position;
3. the current user owns at least one collection item of it.

A series is visible if its country is active **or** the user owns an item in it (no
personal layer for series, so point 2 doesn't apply).

**Completeness adds a fourth point:** a record also counts when the user owns at least
one collection item of **the same series**. A series the user collects is counted and
shown whole — its missing coins included — even from an inactive country; that's what
completeness is for. Drafts, other users' personal positions and records outside any
collected series stay out. `storefront_visible(..., collected_series=True)` applies it
to the counts (`/completeness/*`, `/series/summary`) and the tiles alike, so they always
match.

One predicate implements it — `storefront_visible()` in `app/repositories/catalog.py`,
`series_storefront_visible()` in `app/repositories/series.py` — used by `GET /catalog`
(list and `total`), the "missing" listing and the missing budget, `GET /series*`,
`GET /completeness/*`, and the dashboard aggregates in `GET /bootstrap`, so KPIs match
the lists.

**Direct card exception.** `GET /catalog/{id}` and its sub-resources (`/prices`,
`/collection-items`) ignore the rule: a record of an inactive country opens by direct
link. An explicit `?countryId=` of an inactive country isn't an error — it just returns
what the rule allows.

**Open question:** point 3 (owned records of an inactive country appear in shared
listings) is provisional; the owner may replace it with a separate marker or a
different scope.

## BR-13a. Hard gate: confirmed-catalog countries

`countries.catalog_confirmed` marks a country whose catalog has actually been built and
verified against an official source. Only Ukraine is `true`; everything else, including
the US and USSR records from the seed, is `false` until someone does the same
verification and confirms it by hand.

Without this gate, points 2–3 of BR-13 would turn a whole country into "catalog" for a
user as soon as they bought one coin from it.

- **The gate applies to `GET /catalog` only** (list, search, year bounds for the year
  filter) — the one screen that presents "the catalog". A record appears there only if
  its country is `catalog_confirmed`, and **only then** are BR-13 points 1–3 checked.
- **"Моя колекція", the overview and "Комплектність" ignore the gate.** They're about
  the user's own collection and must show everything the user has. The predicates take
  `require_confirmed` (default on); `/series*`, `/completeness/*` and the `/bootstrap`
  aggregates pass `require_confirmed=False`. Dashboard KPIs and `GET /catalog` totals
  therefore differ for an unconfirmed country the user has coins in — by design.
- **Completeness tiles** come from `GET /completeness/items` with the same
  `require_confirmed=False`, never from `GET /catalog`, which would show an empty grid
  under "56 of 56". The frontend offers "open in catalog" only for `groupBy=series`
  when `CountryOut.catalogConfirmed` is true.
- **Exceptions:** the direct card and `GET /collection` are never gated.
  `GET /catalog/lookup` (suggestions in the purchase form) ignores both the gate and the
  storefront rule — the user picked the country explicitly, and hiding a shared record
  there would push them to create a personal duplicate. Layer visibility and archiving
  still apply. Implemented as `apply_storefront=False` on `CatalogRepository.list_items`,
  its only use.

## BR-14. Material, edge, strike quality

Three coin attributes share one design: a dictionary (`materials`, `edge_types`,
`quality_types` — code + `name_uk` + `name_en`, no `name_original`: this is universal
numismatic vocabulary) plus a free-text fallback on the catalog record (`material`,
`edge`, `quality`) for what the dictionary doesn't cover. The FK (`composition_id`,
`edge_type_id`, `quality_type_id`) and the text coexist: dictionary name where known,
source text where not (`data-model.md`).

- **No fineness in materials.** The NBU "Матеріал" filter has nine values and never
  states silver or gold fineness, so the dictionary has only the metal ("Срібло",
  "Золото", "Срібло із золотим покриттям"). Fineness, when known, lives in `notes`.
- **Technical tokens** (`nickel_silver`, bare `silver`/`gold`, `bimetallic`,
  `cupronickel`…) left in `material`/`edge` by the seed are resolved to dictionary rows by
  migrations `0007` and `0010`; the known aliases are in
  `app/reference_data/materials.py` (`LEGACY_RAW_ALIASES`).

**The purchase form splits these fields deliberately:**

- *Dictionary plus free text* (`Combobox`): **material**, **denomination**, **series**.
  The dictionaries are seeded from what the catalog holds (Ukraine, USSR, US), so they
  know nothing about, say, Austria. On submit, a case-insensitive match sends the id;
  otherwise the text (`material`, `denomination_text`, `series_text`). `series_text` is
  display-only — completeness counts `series_id` (BR-2).
- *Dictionary only* (`Select`): **edge** and **quality**. Both are optional, and
  hand-typed values would never match parser output.
- **Year** — a list plus free input (a 1780 coin won't be in any country's list),
  newest first.

Full dictionaries for the form: `GET /materials`, `GET /edge-types`,
`GET /quality-types`. Don't confuse them with `GET /catalog/materials`, which narrows the
filter to values actually present.

## BR-15. Coins in souvenir packaging

NBU often sells the same coin as two cards: plain and "у сувенірній упаковці". For a
collector that's a presentation variant, not a second coin.
`catalog_items.packaging_of_id` (self-referencing FK) links the packaged card to the
plain one.

- **Pairing criterion:** exact equality of `weight_grams` and `diameter_mm` within
  (series, title without the packaging suffix, issue year). Not title alone — a theme
  re-issued decades later or a heavier silver variant is not a pair. `mintage` is
  excluded: NBU counts loose and packaged as separate batches. Pairs are found by
  `coin-parser` on every parse run.
- **Visibility is a user setting:** `user_settings.show_packaging_variants`, default
  `true`. `GET /catalog` hides records with a `packaging_of_id` when it's off; the direct
  card never checks it (lists filter, a single card doesn't — as with BR-10 and BR-13).
- Not built: `catalog_variants` and a "has a packaged variant" badge on the plain card
  (`backlog.md`).

## BR-16. Storage location

A dictionary (`storage_locations`, `data-model.md`), not free text on
`collection_items`.

- **One system preset, "Вдома"** (`owner_id IS NULL`). Anything more specific the user
  creates themselves.
- **Get-or-create by name; the client never sees ids.** The purchase form and settings
  send only the name (`GET /collection/storage-locations` → `{name, custom}`);
  `StorageLocationService.resolve` finds or creates the row. Matching is
  case-insensitive, trimmed, and checks all three name slots, so "вдома" / " Вдома "
  never create a duplicate or shadow the preset.
- **Translation in the background.** A new personal location stores the typed text in
  both language slots (`manual`); `POST /collection` and `PATCH /bootstrap/settings`
  schedule a `BackgroundTasks` job that detects the language via the Anthropic API and
  fills the other slot (`llm`). Every early exit of that job is logged (no API key, row
  vanished, no tool-use in the reply, API error).
- **Commit before the background job.** A new location is committed together with the
  rest of the request, before the translation job starts (BR-4); a purchase that fails
  after the location was resolved leaves no location behind.
- **Delete own, not the preset.** `DELETE /collection/storage-locations?name=` returns
  `403` for the preset and `404` for a name this owner can't see — including someone
  else's, so their existence isn't revealed. Purchases that used a deleted location keep
  working: both FKs (`collection_items.storage_location_id`,
  `user_settings.default_storage_location_id`) are `ON DELETE SET NULL`.
