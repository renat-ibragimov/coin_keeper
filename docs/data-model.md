# Data model

The PostgreSQL schema as it stands at Alembic head. Source of truth is
`backend/app/models/` plus `backend/alembic/versions/`; this document explains the
shape and the reasons. Behavior built on top of it: `business-rules.md`.

---

## Conventions

- Money is `numeric(14,2)`; exchange rates `numeric(14,6)`. Never `float`.
- Stored dates are `date` / `timestamptz`, never text. Flags are `boolean`.
- Closed value sets are native `ENUM` types (see "Enums"); open-ended vocabularies that
  grow from outside (`catalog_items.quality`, `job_runs.job`) stay `text`.
- `created_at` defaults to `now()`. `updated_at` is maintained by the `set_updated_at()`
  trigger (not by the app) on `users`, `countries`, `coin_series`, `catalog_items`,
  `collection_items`, `sales`, `ucoin_catalog_sources`, `user_settings`, `job_runs`.
- Extensions: `citext` (case-insensitive email), `pg_trgm` (installed; no trigram index
  yet).
- Constraint and index names follow the naming convention in `app/models/base.py`.
- Every schema change is an Alembic migration; migrations run on API container start.

## Layers and ownership

Data splits into three layers (`AGENTS.md`, "Three data layers"):

| Layer | Tables | Marker |
|---|---|---|
| Shared reference data | `countries`, `currencies`, `denominations`, `materials`, `edge_types`, `quality_types`, `coin_series`, `exchange_rates` | — |
| Catalog | `catalog_items`, `catalog_variants`, `market_price_snapshots`, `price_source_links`, catalog `media_files` | `catalog_items.created_by`: `NULL` = shared, user id = personal position |
| Personal | `collection_items`, `expenses`, `storage_locations` (non-preset), `user_settings`, own `media_files`, own price snapshots | `owner_id` / `created_by` / `user_id` |

The visibility filters — `created_by IS NULL OR created_by = :user_id` for catalog items
and price snapshots, `owner_id = :user_id` for personal rows — live in the repository
layer, never in routes (`auth.md`). Who may write what: `business-rules.md`, BR-2.

## Enums

```sql
collection_group    ('circulation', 'commemorative', 'collector', 'other')
metal_kind          ('precious', 'base', 'unknown')
media_role          ('obverse', 'reverse', 'edge', 'additional')
media_source        ('user_upload', 'ucoin', 'nbu', 'ua_coins', 'manual')
translation_source  ('official', 'llm', 'manual')
match_status        ('suggested', 'confirmed', 'rejected')
offer_status        ('considering', 'ordered', 'purchased', 'rejected', 'unavailable')
user_role           ('user', 'admin')
auth_token_kind     ('email_verify', 'password_reset', 'telegram_link')
expense_category    ('coin_purchase', 'delivery', 'album', 'holder', 'storage',
                     'grading', 'literature', 'photo_equipment', 'other')
```

`collection_group` has **four** values; queries that branch on it must handle all four.

## Three language slots

Every named entity — country, series, coin — carries:

```
<name>_original     the issuer's own wording; NEVER translated
original_lang       ISO 639-1 language of <name>_original
<name>_uk           Ukrainian translation
<name>_en           English translation
<name>_uk_source    official | llm | manual   (series and catalog items)
<name>_en_source    same
```

- There are no `*_ru` columns. For Soviet coins Russian *is* the original
  (`original_lang = 'ru'`); for US coins, English.
- A translation slot that merely repeats the original is not a translation and is left
  `NULL`.
- `*_source` answers "can this translation be trusted": `official` — published by the
  issuer (NBU's Ukrainian and English sites); `llm` — machine translation; `manual` —
  set by a human (an admin `PATCH` sets it automatically). Loaders never overwrite a
  `manual` slot. `*_original` has no source.

Example (a Polish coin): `title_original` (`pl`) `W Polskę wierzę – Pieśń „Rota”`,
`title_uk` `Я вірю в Польщу — пісня „Рота“`, `title_en`
`I Believe in Poland — the Song ‘Rota’`.

### Display name and sorting

```
title_<locale> → title_original
```

Nothing beyond the original — it's `NOT NULL`, so the fallback is always meaningful.
The response locale is `?locale=`, else `Accept-Language`, else `uk`. Lists sort by the
same expression, with an explicit ICU collation (`uk-x-icu` / `en-x-icu`,
`app/repositories/localization.py`); without it Postgres sorts by code point and puts
Є, І, Ї, Ґ before А.

Dictionaries (`materials`, `edge_types`, `quality_types`) and storage locations use a
reduced form, described with those tables.

## Accounts

### users

```
id              bigserial PK
email           citext UNIQUE NOT NULL
password_hash   text              -- argon2id; NULL for a Google-only account
display_name    text
role            user_role NOT NULL DEFAULT 'user'
is_active       boolean NOT NULL DEFAULT true    -- registration creates it false until email verification
email_verified  boolean NOT NULL DEFAULT false
locale          text NOT NULL DEFAULT 'uk'       -- 'uk' | 'en'
avatar_key      text              -- storage key of the profile picture, not a URL
created_at, updated_at timestamptz
```

`avatar_key` is a plain column, not a `media_files` row: that table's checks tie every
file to a catalog or collection item. Auth flows: `auth.md`.

### auth_identities

```
id             bigserial PK
user_id        bigint NOT NULL FK users ON DELETE CASCADE
provider       text NOT NULL        -- 'google'
subject        text NOT NULL        -- the provider's stable user id
email_at_link  text NOT NULL
created_at     timestamptz
UNIQUE (provider, subject), UNIQUE (user_id, provider)
```

A provider subject identifies the account even if the email changes later.

### refresh_tokens, auth_tokens

Both store the sha256 of a token, never the token. A refresh token's family is one
sign-in; rotation, the grace window and family-scoped revocation are in `auth.md`,
"Sessions". Migration `0027` retired every token that existed before families
(`logout_all`).

```
refresh_tokens: id, user_id FK users CASCADE, token_hash UNIQUE, expires_at,
                revoked_at, revoke_reason CHECK (rotated | logout | reuse |
                password_change | password_reset | logout_all),
                family_id uuid, parent_id FK refresh_tokens SET NULL,
                session_started_at, persistent bool DEFAULT true,
                user_agent, ip inet, created_at;
                INDEX (user_id), INDEX (family_id),
                INDEX (user_id) WHERE revoked_at IS NULL
auth_tokens:    id, user_id FK users CASCADE, kind auth_token_kind, token_hash UNIQUE,
                expires_at, used_at, created_at; INDEX (user_id, kind)
```

An `auth_tokens` row is usable while `used_at IS NULL AND expires_at > now()`. Lifetimes
come from settings: 24 h for email verification, 1 h for password reset,
`telegram_link_ttl_minutes` for Telegram linking. Issuing a new token of a kind voids
the user's unused ones of that kind (`auth.md`).

### user_settings

One row per user, `user_id` is the PK (FK users `ON DELETE CASCADE`).

| Column | Default | Meaning |
|---|---|---|
| `locale` | `'uk'` | interface language |
| `display_currency` | `'UAH'` | unused — always `UAH`, no UI or API to change it |
| `default_grade` | `'UNC'` | pre-fills the purchase form (`business-rules.md`, BR-7) |
| `show_packaging_variants` | `true` | show souvenir-packaging cards in catalog lists (BR-15) |
| `theme` | `'system'` | `light` / `dark` / `system` |
| `catalog_view_mode`, `collection_view_mode` | `'cards'` | `cards` / `table` |
| `secondary_currency` | `'USD'` | `USD` / `EUR`, second amount next to UAH (BR-6) |
| `include_supporting_expenses` | `true` | count extras in "bought for" (BR-4) |
| `default_storage_location_id` | `NULL` | FK storage_locations `ON DELETE SET NULL` |

`theme` and the view modes are the cross-device copy of preferences; the client also
keeps a `localStorage` copy to paint before `GET /bootstrap` returns (and on sign-in
screens). New per-user preferences belong here, not in `localStorage`.

## Reference data

### countries

```
id                bigserial PK
code              text UNIQUE     -- ISO 3166-1 alpha-2; 3166-3 alpha-4 or X+3 for historical states
name_original     text NOT NULL UNIQUE   -- endonym: 'Україна', 'Polska', 'СССР'
original_lang     text NOT NULL
name_uk, name_en  text
collect_variants  boolean NOT NULL DEFAULT false
is_active         boolean NOT NULL DEFAULT true
catalog_confirmed boolean NOT NULL DEFAULT false
sort_order        int NOT NULL DEFAULT 100
created_at, updated_at timestamptz
```

Seeded with every issuer (`app/reference_data/countries.json`): the 249 ISO 3166-1
countries (endonym, Ukrainian and English names from CLDR) plus historical states CLDR
maps to a successor — USSR, RSFSR, Russian Empire, UNR, Austria-Hungary, German Empire,
GDR, Czechoslovakia, Yugoslavia, Serbia and Montenegro, Netherlands Antilles.

- `is_active` — the storefront switch (`business-rules.md`, BR-13). The seed activates
  Ukraine only; a country that existed before the seed keeps its state and `id`.
- `catalog_confirmed` — the hard catalog gate (BR-13a); `true` for Ukraine only.
- `sort_order` — Ukraine `0`, everyone else `100`, then name in the reader's locale.
- `collect_variants` — varieties mode (BR-5); not implemented.

### currencies

```
code            text PK          -- 'UAH', 'USD', 'EUR', 'UAK' (karbovanets 1992–1996), 'SUR' (Soviet ruble)
name            text NOT NULL
symbol          text
decimal_places  smallint NOT NULL DEFAULT 2
```

### denominations

A face value is structure, not a string — a string can't be shown in another language
or sorted.

```
id             bigserial PK
country_id     bigint NOT NULL FK countries
currency_code  text NOT NULL FK currencies
value          numeric(14,3) NOT NULL   -- the number in the named unit: 5 for "5 копійок"
unit           text NOT NULL            -- hryvnia | kopiika | karbovanets | ruble | kopeck |
                                        -- poltinnik | chervonets | dollar | dime | cent
sort_order     int NOT NULL DEFAULT 0   -- face value in the currency's smallest unit
is_active      boolean NOT NULL DEFAULT true
UNIQUE (country_id, currency_code, unit, value)
```

The label is rendered per request locale with CLDR plural rules ("5 копійок" /
"5 kopecks", "¼ долара"); units and rules are in `app/reference_data/denominations.py`.
`sort_order` puts 50 kopiiok before 1 hryvnia; `value` separates units of equal worth
(25 cents vs ¼ dollar).

### materials, edge_types, quality_types

Three dictionaries of the same shape — universal numismatic vocabulary, so no
`name_original` (`business-rules.md`, BR-14):

```
id       bigserial PK
code     text NOT NULL UNIQUE   -- 'silver', 'nickel_silver', 'reeded', 'proof'
name_uk  text NOT NULL
name_en  text NOT NULL
```

Seeded from `app/reference_data/`. Materials carry the metal only, no fineness.

### coin_series

```
id                bigserial PK
country_id        bigint NOT NULL FK countries ON DELETE CASCADE
name_original     text NOT NULL
original_lang     text NOT NULL
name_uk, name_en  text
name_uk_source, name_en_source  translation_source
description       text
start_year, end_year  int
is_official       boolean NOT NULL DEFAULT false
created_at, updated_at timestamptz
UNIQUE (country_id, name_original)
```

`is_official` is set by `coin-parser`'s series loader for series the issuer's own
catalog maintains (today: NBU). Curated series and other countries stay `false`; the
flag appears when the parser first visits a series.

### exchange_rates

```
id              bigserial PK
currency_code   text NOT NULL FK currencies
rate_uah        numeric(14,6) NOT NULL CHECK (rate_uah > 0)
effective_date  date NOT NULL
fetched_at      timestamptz NOT NULL
source          text NOT NULL DEFAULT 'NBU'
UNIQUE (currency_code, effective_date, source)
```

Shared; written by `coin-parser`. Only USD and EUR are loaded (`business-rules.md`,
BR-6).

## Catalog

### catalog_items

The central table. A row describes an **issue**, not a physical coin.

```
id                 bigserial PK
item_type          text NOT NULL DEFAULT 'coin'
country_id         bigint NOT NULL FK countries
series_id          bigint FK coin_series ON DELETE SET NULL
series_text        text             -- a personal position's own series name; display only
packaging_of_id    bigint FK catalog_items ON DELETE SET NULL   -- souvenir-packaging variant of
denomination_id    bigint FK denominations ON DELETE SET NULL
denomination_text  text             -- face value in words when there's no dictionary row
collection_group   collection_group NOT NULL
subtype            text
title_original     text NOT NULL
original_lang      text NOT NULL DEFAULT 'uk'
title_uk, title_en text
title_uk_source, title_en_source  translation_source
issue_year         int NOT NULL
issue_date         date
mintage_announced, mintage_actual  bigint
composition_id     bigint FK materials ON DELETE SET NULL
material           text             -- only what didn't resolve to composition_id
metal_kind         metal_kind NOT NULL DEFAULT 'unknown'
weight_grams       numeric(10,3)
diameter_mm, thickness_mm  numeric(8,2)
shape, orientation text
edge_type_id       bigint FK edge_types ON DELETE SET NULL
edge               text             -- only what didn't resolve to edge_type_id
quality_type_id    bigint FK quality_types ON DELETE SET NULL
quality            text             -- strike quality code; kept verbatim when not in the dictionary
catalog_km, catalog_uc, catalog_numista  text
catalog_number     text             -- a number with no named catalog (hand-entered coins)
notes              text
descriptions       jsonb            -- see below
artists            jsonb            -- see below
edited_fields      jsonb            -- names of hand-corrected fields
source_key         text             -- import/loader dedup key (business-rules.md, BR-3)
created_by         bigint FK users ON DELETE CASCADE   -- NULL = shared record
status             text NOT NULL DEFAULT 'active' CHECK (status IN ('draft','active','rejected'))
is_archived        boolean NOT NULL DEFAULT false
archived_at        timestamptz
archive_reason     text
created_at, updated_at timestamptz
```

**`created_by` is `ON DELETE CASCADE`, not `SET NULL`:** otherwise deleting a user
would silently turn their personal positions into shared records.

**Dictionary plus free text.** `composition_id`/`material`, `edge_type_id`/`edge`,
`quality_type_id`/`quality`, `denomination_id`/`denomination_text`,
`series_id`/`series_text` follow one pattern: the dictionary row where one fits, the
source's or user's own words where not (`business-rules.md`, BR-14).
`denomination_text` is shown in place of a denomination when `denomination_id` is empty;
sorting and filtering by denomination ignore it, as they ignore free-text `material`.
`series_text` is display only (via `series_display_name()` in
`app/repositories/localization.py`); completeness, the series filter and series screens
count `series_id` only.

**`quality`** has no `CHECK`: its vocabulary lives in `coin-parser` and grows.

**Catalog number shown on the card:** the first non-empty of `catalog_km`, `catalog_uc`,
`catalog_numista`, `catalog_number` — a named catalog always wins.

**`status`.** `draft` — created by the NBU catalog sync, waiting for an admin;
`active` — published; `rejected` — a rejected draft, which is also archived with the
reason. Non-admin reads require `status = 'active'` (`business-rules.md`, BR-2;
`admin.md`).

**`edited_fields`** — the contract that a catalog loader leaves hand-corrected fields
alone. Nothing writes it yet.

**Archiving** (`is_archived`, `archived_at`, `archive_reason`) replaces deletion for
shared records; the three are set together and cleared together. Semantics:
`business-rules.md`, BR-10.

#### descriptions and artists

Either column may be `NULL` as a whole — a row the parser hasn't touched and the user
didn't describe. **Once non-null, the inner shape is fixed** and code must not guard
against missing keys.

`descriptions`: both locale keys (`uk`, `en`) and all three parts are always present;
missing text is `null`, not a missing key.

```json
{
  "uk": {"general": "...", "obverse": "...", "reverse": "..."},
  "en": {"general": null, "obverse": null, "reverse": null}
}
```

The purchase form's three description fields write under the request locale and fill
the other locale with `null`s. If nothing was typed, the column stays `NULL` — a row of
nulls would claim "the parser came and found nothing".

`artists`: `designers` and `sculptors` are always arrays (possibly `[]`), each person an
object with the same locales:

```json
{
  "designers": [{"uk": "Таран Володимир", "en": "Volodymyr Taran"}],
  "sculptors": [{"uk": "Чайковський Роман", "en": "Roman Chaikovskyi"}]
}
```

The API collapses both to the reader's locale (`description.general/obverse/reverse`,
`designers`, `sculptors`), falling back to the other locale where the requested one has
no text.

#### Indexes

```sql
-- catalog reads work on active rows, so most indexes are partial
(country_id, issue_year)   WHERE NOT is_archived
(series_id)                WHERE NOT is_archived
(packaging_of_id)          WHERE NOT is_archived
(created_by)
(catalog_km)               WHERE NOT is_archived   -- three single-column indexes: search
(catalog_uc)               WHERE NOT is_archived   -- matches any one number, a composite
(catalog_numista)          WHERE NOT is_archived   -- would only serve the first column
(archived_at)              WHERE is_archived       -- admin archive views

-- source_key: unique globally among shared rows, per owner among personal rows
UNIQUE catalog_items_source_key_shared_idx (source_key)
  WHERE source_key IS NOT NULL AND created_by IS NULL
UNIQUE catalog_items_source_key_own_idx (created_by, source_key)
  WHERE source_key IS NOT NULL AND created_by IS NOT NULL

-- full-text search over all three title slots
catalog_items_search_idx USING gin (to_tsvector('simple',
  coalesce(title_original,'') || ' ' || coalesce(title_uk,'') || ' ' || coalesce(title_en,'')))
  WHERE NOT is_archived
```

- **Write `NOT is_archived` verbatim** in queries. A partial index applies only when the
  query predicate matches it; `is_archived = false` or `IS NOT TRUE` won't use it.
- **The search expression in code must match the index expression exactly**
  (`_search_vector()` in `app/repositories/catalog.py`). The `simple` configuration is
  deliberate: titles mix Ukrainian, Russian and English, and stemming for one language
  would break the others.
- **Archived rows stay in `source_key` uniqueness.** Excluding them would let a loader
  create a fresh record with the same key while other people's coins stay attached to the
  archived one — a silent duplicate. To "reopen" a record, unarchive it.

### catalog_variants

```
id, catalog_item_id FK catalog_items CASCADE, name NOT NULL,
mint_name, mint_mark, variety_code, notes
UNIQUE (catalog_item_id, name, mint_mark)
```

Exists; unused (varieties are deferred, `product.md`, "Out of scope").

### market_price_snapshots

Append-only price history — every check inserts a row.

```
id               bigserial PK
catalog_item_id  bigint NOT NULL FK catalog_items ON DELETE CASCADE
source           text NOT NULL        -- 'UA-Coins', 'uCoin', 'Manual'
grade            text
price            numeric(14,2) NOT NULL CHECK (price >= 0)
currency_code    text NOT NULL FK currencies
observed_at      timestamptz NOT NULL
source_url       text
raw_payload      jsonb                -- the source's raw response, for debugging parsers
created_by       bigint FK users ON DELETE SET NULL   -- NULL = central job
is_suspect       boolean NOT NULL DEFAULT false
UNIQUE NULLS NOT DISTINCT (catalog_item_id, source, grade, observed_at)
INDEX (catalog_item_id, observed_at DESC), INDEX (created_by),
INDEX (catalog_item_id) WHERE is_suspect
```

- `created_by` decides visibility (`business-rules.md`, BR-7).
- `NULLS NOT DISTINCT`: most snapshots have no grade, and by default two rows differing
  only in a `NULL` grade wouldn't collide.
- `is_suspect` exists only for imported history (see "Data origins"); normal writes
  reject a bad price instead of flagging it. Suspect rows show in history and are
  excluded from value.

### price_source_links

A confirmed mapping of a catalog item to an external source record.

```
id, catalog_item_id FK catalog_items CASCADE, source NOT NULL,
external_id NOT NULL    -- URL or id on the source side
match_status match_status NOT NULL DEFAULT 'confirmed', matched_at
UNIQUE (catalog_item_id, source)
```

### media_files

```
id                  bigserial PK
catalog_item_id     bigint FK catalog_items ON DELETE CASCADE
collection_item_id  bigint FK collection_items ON DELETE CASCADE
owner_id            bigint FK users ON DELETE CASCADE   -- NULL for catalog photos
role                media_role NOT NULL
source              media_source NOT NULL DEFAULT 'user_upload'
license, attribution  text
storage_key         text      -- key of the largest stored size
external_url        text      -- hotlink; the frontend never shows foreign URLs
thumbnail_key       text      -- 300 px preview
variants            jsonb     -- {"300": key, "600": key, "1200": key}
mime_type           text
width, height       int
size_bytes          bigint
sha256              text
created_at          timestamptz
CHECK (catalog_item_id IS NOT NULL OR collection_item_id IS NOT NULL)
CHECK (storage_key IS NOT NULL OR external_url IS NOT NULL)
INDEX (catalog_item_id), INDEX (collection_item_id), INDEX (owner_id)
```

`variants` lists sizes actually stored — nothing is upscaled, so a 600 px source has no
`1200`. Rows with empty `variants` fall back to `storage_key` / `thumbnail_key`.
`source` drives visibility; rules, sizes and rights: `media.md`.

## Collection and money

### collection_items

One purchase of a catalog item by a user, with a `quantity`.

```
id                   bigserial PK
owner_id             bigint NOT NULL FK users ON DELETE CASCADE
catalog_item_id      bigint NOT NULL FK catalog_items ON DELETE NO ACTION
variant_id           bigint FK catalog_variants ON DELETE SET NULL
quantity             int NOT NULL DEFAULT 1 CHECK (quantity > 0)
grade, condition_notes  text
acquisition_date     date
acquisition_place, seller  text
purchase_price       numeric(14,2)
purchase_currency    text FK currencies
purchase_rate_uah    numeric(14,6)      -- NBU rate on the purchase date
storage_location_id  bigint FK storage_locations ON DELETE SET NULL
grading_company, grading_number, grading_grade  text
is_for_swap, is_for_sale, needs_replacement  boolean NOT NULL DEFAULT false
notes                text
created_at, updated_at timestamptz
INDEX (owner_id, catalog_item_id), INDEX (owner_id, acquisition_date DESC)
```

The UAH amount is never stored: `purchase_price × purchase_rate_uah`
(`business-rules.md`, BR-4).

#### Why `NO ACTION`, not `RESTRICT`

"Don't delete a catalog item that has collection items" is enforced in the **service
layer** (`business-rules.md`, BR-10); the FK is only a backstop against orphans, so it
uses the least restrictive option that still guarantees integrity.

Deleting a user fires two cascades that meet at personal catalog items
(`users → collection_items` and `users → catalog_items.created_by`). On PostgreSQL 16
both `RESTRICT` and `NO ACTION` handle that correctly: all referential actions of one
statement are queued together, so the collection items are gone before the check
runs (`tests/test_cascade_diamond.py`).

The real difference is deferral: `RESTRICT` is checked immediately even when declared
`DEFERRABLE INITIALLY DEFERRED`; `NO ACTION` can wait until commit. That matters for
re-pointing collection items from one catalog item to another inside a transaction —
exactly what merging duplicates will need (deferred, `product.md`, "Out of scope"). Keeping the option
costs nothing; lacking it later would cost a migration.

### expenses

```
id                  bigserial PK
owner_id            bigint NOT NULL FK users ON DELETE CASCADE
category            expense_category NOT NULL
amount              numeric(14,2) NOT NULL CHECK (amount >= 0)
currency_code       text NOT NULL FK currencies
rate_uah            numeric(14,6)
expense_date        date NOT NULL
catalog_item_id     bigint FK catalog_items ON DELETE SET NULL
collection_item_id  bigint FK collection_items ON DELETE SET NULL
series_id           bigint FK coin_series ON DELETE SET NULL
vendor, description text
created_at          timestamptz
INDEX (owner_id, expense_date)
```

- Every purchase creates a `coin_purchase` expense in the same transaction.
- `collection_item_id ON DELETE SET NULL` means different things per category: for
  `coin_purchase` it's only a backstop — the service deletes that expense explicitly, and
  relying on the FK would keep it and inflate spend; for supporting expenses it's the
  intended behavior. Both: `business-rules.md`, BR-4 and BR-10.

### storage_locations

```
id              bigserial PK
owner_id        bigint FK users ON DELETE CASCADE   -- NULL = system preset, visible to all
name_original   text NOT NULL                       -- what the owner typed
name_uk         text NOT NULL
name_uk_source  translation_source NOT NULL
name_en         text NOT NULL
name_en_source  translation_source NOT NULL
created_at      timestamptz
```

Never exposed as a CRUD resource by id — the client addresses locations by name and the
server resolves them. One preset, "Вдома" / "At home". Get-or-create, translation and
deletion rules: `business-rules.md`, BR-16.

## Operations

### audit_log

```
id, user_id FK users ON DELETE SET NULL, action NOT NULL, entity_type NOT NULL,
entity_id text, details jsonb, created_at
```

Written for catalog item archive / unarchive / delete / draft publish / reject
(`catalog_item.*`) and admin role changes (`role.promote`, `role.demote`). Image
deletion is not audited.

### job_runs

One row per run of a background job, as the job reported it (`admin.md`).

```
id           bigserial PK
job          text NOT NULL     -- 'update-prices', ...; open-ended on purpose
status       text NOT NULL CHECK (status IN ('running','ok','partial','failed'))
started_at   timestamptz NOT NULL
finished_at  timestamptz       -- CHECK: NULL exactly when status = 'running'
run_date     date              -- the day the run is about, not the day it ran
summary      text              -- the job's one-line self-report
stats        jsonb             -- the job's own counters, verbatim
details      text              -- only when not ok
exit_code    smallint
created_at, updated_at timestamptz
INDEX (job, started_at DESC)
```

A run opens as `running` before work starts, so a killed run leaves a `running` row
rather than nothing. No foreign keys: a job reports on itself, not on records.
`run_date` differs from `started_at` because the nightly price run is dated by the
UA-Coins table header, which may still show yesterday.

### telegram_recipients

```
id, user_id FK users CASCADE, chat_id bigint NOT NULL UNIQUE, linked_at
INDEX (user_id)
```

Chats that receive admin notifications. A row appears only through a one-time link code
issued to a signed-in admin (`admin.md`).

### Support bot tables

`support_telegram_settings` (singleton row, `CHECK (id = 1)`: the forum group chat id),
`support_link_tokens` (hashed one-time tokens linking a Telegram chat to an account),
`support_tickets` (`status IN ('open','closed')`, one forum topic per ticket),
`support_messages` (`direction IN ('user_to_admin','admin_to_user')`). Behavior:
`telegram-support.md`.

## Unused tables

Created by the initial schema for deferred features (`product.md`, "Out of scope"); nothing reads or
writes them:

- `sales` — sold collection items (FKs `NO ACTION`, `quantity > 0`, `sale_price >= 0`).
- `purchase_offers` — offers being considered (`offer_status`).
- `collection_goals` — collecting targets by country / series / group / years.
- `ucoin_catalog_sources` — saved uCoin sections for repeat import, unique per
  `(owner_id, url)`.

## Relationships

```
users ──< collection_items >── catalog_items ──< market_price_snapshots
  │            │                     │       ├─< price_source_links
  │            │                     │       ├─< catalog_variants
  │            │                     │       └─< media_files (catalog photos)
  │            ├─< media_files (own photos)
  │            └─< expenses
  ├──< catalog_items (personal positions, created_by)
  ├──< market_price_snapshots (own snapshots, created_by)
  ├──< storage_locations (own; the preset has owner_id NULL)
  ├── user_settings
  ├──< auth_identities, refresh_tokens, auth_tokens
  └──< telegram_recipients, support_link_tokens, support_tickets

storage_locations ──< collection_items, user_settings.default_storage_location_id
countries ──< coin_series ──< catalog_items
    └─────< denominations ──< catalog_items
materials / edge_types / quality_types ──< catalog_items
currencies ──< exchange_rates, denominations
```

## Data origins

The database was seeded once, at first deploy, from a snapshot of the owner's previous
desktop app (SQLite, 2026-08-06). The import code has been deleted; what it left in the
data is described here so that odd-looking rows have an explanation.

- **Catalog.** Its 3063 items became shared-catalog records (`created_by IS NULL`),
  including the US and USSR ones — those countries stay `catalog_confirmed = false`.
- **Collection.** 620 collection items and their purchase history belong to the owner's
  account.
- **Price snapshots.** The 3938 imported snapshots were run through the price checks in
  `integrations.md`; failures were kept with `is_suspect = true`, visible in history but
  excluded from value. New prices never get this flag — they're rejected before writing.
- **Free text.** `catalog_items.material` keeps, verbatim, whatever could not be mapped
  to a `materials` code instead of guessing. The alias tables in
  `backend/app/reference_data/` (`LEGACY_RAW_ALIASES` in `materials.py`,
  `LEGACY_ALIASES` in `edge_types.py`) map raw imported values to dictionary codes;
  migrations `0007` and `0010` resolved the known technical tokens.
- **Denominations.** Migration `0003` parsed the imported free-text labels into
  structured rows and merged duplicates; an unparseable label would have stopped it.
- **Photos.** About 320 US images use the old `legacy-N.webp` key scheme without size
  variants; tools that expect all three sizes report them as missing originals.
