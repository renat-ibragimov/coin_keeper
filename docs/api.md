# API

REST + JSON under `/api/v1`. OpenAPI at `/api/v1/openapi.json`, Swagger UI at
`/api/v1/docs`. Routes live in `backend/app/api/v1/`, bodies in `backend/app/schemas/`.
The frontend's types are generated from the deployed OpenAPI (`npm run gen:api`).

This document is the contract: what each endpoint accepts, returns and refuses. The
rules behind the numbers are in `business-rules.md` (cited as BR-N); access rules in
`auth.md`.

---

## Conventions

- **Casing.** JSON is camelCase (`CamelModel`, `alias_generator = to_camel`); query
  parameters are camelCase too (`countryId`, `pageSize`).
- **Auth.** `Authorization: Bearer <access token>`. The refresh token lives only in an
  httpOnly cookie (see "Authentication"). An endpoint marked *guest* also answers without
  a token; everything else returns `401 not-authenticated` without one.
- **Pagination.** Every list is paged: `?page=1&pageSize=50` (`pageSize` 1–200), response
  `{items, total, page, pageSize}` (`Page[T]`). Exceptions: small dictionaries and
  `/catalog/lookup`.
- **Errors.** RFC 7807, `application/problem+json`:
  `{type, title, status, detail}`, where `type` is
  `https://coinkeeper.app/problems/<slug>` and the slug is stable (`catalog-item-not-found`,
  `shared-catalog-read-only`…). Validation errors are `422 validation-error` with an
  `errors` array. Handlers: `backend/app/api/errors.py`.
- **Money** is a string with two decimals (`"1923.00"`, `Money`); rates are decimal strings
  (`Rate`). Never floats.
- **Dates.** ISO 8601: `YYYY-MM-DD` for dates, timezone-aware timestamps for moments.
- **Locale.** Localized fields follow `?locale=uk|en`, else `Accept-Language`, else `uk`
  (BR-12).
- **Route order.** Literal sub-paths (`/catalog/summary`, `/collection/countries`…) are
  registered before `/{id}` routes; otherwise FastAPI tries to parse them as ids.

### Multi-value filters

Filters that select from a list repeat the key: `?countryId=1&countryId=2`. The backend
reads them as `list[int]` (or a list of enum values); the frontend's `client.ts` and
filter hooks produce the same shape. Applies to `countryId`, `seriesId`,
`denominationId`, `group`, `materialId`, `metalKind` on `/catalog`, `/catalog/summary`,
`/collection` and `/collection/summary`.

### Guest access and rate limits

Anonymous visitors can browse the public catalog:

| Endpoint | Guest behavior |
|---|---|
| `GET /catalog` | shared, active, published records of active **and** confirmed countries only; no prices, ownership or personal fields (`PublicCatalogListItem`). `owned`, `scope=own`, `archived=true` and sorts `owned`/`purchase`/`price` → `422 private-catalog-filter` |
| `GET /catalog/{id}` | `PublicCatalogCard` — the same allowlist, no prices |
| `GET /catalog/materials`, `GET /countries`, `GET /denominations` | as for users |
| `GET /series` | only `scope=catalog`; `scope=mine` → `422 private-series-filter` |
| `GET /support/telegram`, `GET /health`, the auth endpoints | public by nature |

Guests are rate-limited per IP (`app/core/rate_limit.py`): catalog and card 300/min,
catalog search (`q` set) 90/min, reference lists 300/min. Over the limit →
`429 rate-limit-exceeded` with `Retry-After`. Signed-in users are not limited here.

---

## Authentication

```
POST   /auth/register            {email, displayName?, website?}      → 202 {status: "accepted"}
POST   /auth/resend-verification {email}                              → 202
POST   /auth/verify-email        {token, newPassword?}                → {user, tokens}
POST   /auth/login               {email, password}                    → {user, tokens}
POST   /auth/refresh             — (cookie)                           → {user, tokens}
POST   /auth/logout              — (cookie)                           → 204
POST   /auth/forgot-password     {email}                              → 202
POST   /auth/reset-password      {token, newPassword}                 → 204
GET    /auth/me                                                       → user
PATCH  /auth/me                  {displayName?, locale?}              → user
PUT    /auth/me/avatar           <raw image bytes>                    → user
DELETE /auth/me/avatar                                                → user
POST   /auth/change-password     {currentPassword, newPassword}       → 204
POST   /auth/set-password        {newPassword}                        → 204
GET    /auth/google/status                                            → {enabled}
GET    /auth/google/start                                             → 302 to Google
POST   /auth/google/link/start   (signed in)                          → {url}
GET    /auth/google/callback     ?state&code&error                    → 303 to the app
```

- **Tokens.** `tokens = {accessToken, expiresIn}`. The refresh token is **never** in a
  body: login, verify, refresh and the Google callback set it as an httpOnly, Secure,
  SameSite=Lax cookie scoped to `/api/v1/auth`; `/auth/refresh` and `/auth/logout` read
  it from there and take no body. Refresh rotates the cookie; an invalid one is cleared
  (`401 invalid-refresh-token`).
- **`user`** (`UserOut`): `id, email, displayName, role, locale, emailVerified,
  hasPassword, googleLinked, avatarUrl`. `avatarUrl` is a signed short-lived URL or
  `null`, never a storage key (`media.md`), built in one place so it's identical here and
  in `/bootstrap`.
- **Registration** answers `202` whether or not the address is taken, and creates no
  tokens: the account is inactive until the email is confirmed. The password is chosen at
  `/auth/verify-email` (`422 password-required` if missing, except for Google-created
  accounts). A legacy `password` field in `/auth/register` is accepted and ignored.
  `website` is a honeypot: filled → the same `202`, nothing created.
  `ALLOW_REGISTRATION=false` → `403 registration-closed`.
- **Always 202:** `/auth/resend-verification` and `/auth/forgot-password`, so they can't
  be used to probe addresses.
- **Errors.** Login: `401 invalid-credentials`, `403 email-not-verified`,
  `403 account-disabled`. Tokens in links: `400 invalid-verification-token`,
  `400 invalid-reset-token`. Passwords: `422 weak-password`.
  `/auth/change-password` with a wrong current password → `400 invalid-credentials`; on
  success every session is revoked and the cookie cleared. `/auth/set-password` when a
  password already exists → `409 password-already-set` (it's for Google-only accounts).
- **Rate limits** (per IP and per email where there is one): login 5 / 15 min (reset on
  success), register 3/h, forgot-password 3/h, resend 3/h, reset 5/h, refresh 30/h,
  Google start 10/h → `429 rate-limit-exceeded` with `Retry-After`. Rationale: `auth.md`.
- **Avatar.** `PUT /auth/me/avatar` takes the image as the whole body, no multipart:
  JPEG, PNG or WebP, ≤ 12 MB, ≤ 4000 px wide, else `422 invalid-image` (an oversized
  `Content-Length` is refused before reading the body). Same bytes → same key, so a
  repeat is a no-op. `DELETE` returns `200` with the profile (the caller needs the empty
  `avatarUrl`); deleting a missing avatar isn't an error.
- **Google.** `/status` tells the frontend whether to show the button. `/start` redirects
  to Google (`503 google-disabled` when not configured). `/link/start` (signed in) returns
  the URL to link Google to the current account; already linked → `409
  google-already-linked`. The callback redirects back to the app:
  `/google-complete` after a successful sign-in (the frontend then calls `/auth/refresh`),
  `/google-complete?mode=link&google=linked|conflict|error` for linking,
  `/login?google=error|link-required|registration-closed` and
  `/check-email?google=verify` otherwise. A Google sign-in for an email that already has
  an account doesn't merge silently — the user signs in the existing way and links from
  settings. Flow and conflict rules: `auth.md`.

---

## Bootstrap

One request feeds the app shell and the overview.

```
GET /bootstrap
→ {
    user: UserOut,
    settings: SettingsOut,
    dashboard: {
      catalogItems, collectionItems, countries,
      completedItems, missingItems, completionPercent,
      coinSpendUah, relatedSpendUah, totalSpendUah,
      marketValueUah, missingBudgetUah, unpricedMissingItems,
      countryBreakdown: [{name, count, owned}],
      seriesBreakdown:  [{id, name, country, count, owned}],
      isEmpty
    },
    exchangeRates: [{code, rate, effectiveDate}],     // latest USD and EUR
    finance: {
      coinSpendUah, coinSpendUsdAtPurchase, coinSpendEurAtPurchase,
      purchasesWithoutHistoricalUsdRate, purchasesWithoutHistoricalEurRate
    }
  }
```

- Calculations: BR-8 (finances), BR-9 (breakdowns), BR-13/BR-13a (the aggregates use the
  storefront rule with `require_confirmed=False`).
- `seriesBreakdown[].id` lets the overview link a series row to its completeness page.
- `isEmpty` means the user has nothing yet — no collection items and no personal
  positions. The shared catalog alone doesn't make the dashboard "full".

### Settings

```
PATCH /bootstrap/settings   {any subset of the fields below}   → SettingsOut
```

Partial update: only the fields sent are changed. `locale` is changed through
`PATCH /auth/me`, not here.

| Field | Values, default | Meaning |
|---|---|---|
| `showPackagingVariants` | bool, `true` | show souvenir-packaging cards in `GET /catalog` (BR-15) |
| `defaultGrade` | string ≤ 50, `UNC` | pre-fills the purchase form; free text, not validated against a list (BR-7) |
| `theme` | `light \| dark \| system`, `system` | |
| `catalogViewMode`, `collectionViewMode` | `cards \| table`, `cards` | the frontend keeps a localStorage copy only as a cache |
| `secondaryCurrency` | `USD \| EUR`, `USD` | which already-computed conversion to show next to UAH (BR-6) |
| `defaultStorageLocation` | name or `null` | resolved by name through get-or-create (BR-16); `""`/`null` clears it |
| `includeSupportingExpenses` | bool, `true` | whether the coin card adds supporting expenses to "bought for" (BR-4) |

`SettingsOut` also carries `locale` and `displayCurrency`.

---

## Catalog

```
GET    /catalog                          guest   list (filters below)
GET    /catalog/summary                          KPI tiles for the same filters
GET    /catalog/lookup                           typeahead for the purchase form
GET    /catalog/materials                guest   materials the catalog filter offers
GET    /catalog/{id}                     guest   card
GET    /catalog/{id}/prices                      price history visible to the user
GET    /catalog/{id}/collection-items            the user's own purchases of this item
POST   /catalog                                  create a record
PATCH  /catalog/{id}                             edit
DELETE /catalog/{id}                             delete
POST   /catalog/{id}/archive     {reason}        archive a shared record (admin)
POST   /catalog/{id}/unarchive                   unarchive (admin)
```

Every read is limited to records the user may see — shared plus their own personal ones
(`created_by IS NULL OR created_by = :user`) — by the repository, not the route. Drafts
(`status = 'draft'`) are invisible to everyone but admins (BR-2).

### Catalog filters

```
GET /catalog
  ?page, pageSize
  &q               ≤ 200 chars: original and translated titles, catalog numbers (BR-12)
  &countryId*  &seriesId*  &denominationId*  &materialId*
  &group*          circulation | commemorative | collector | other
  &metalKind*      precious | base | unknown
  &year | yearFrom, yearTo
  &dateFrom, dateTo  ISO dates on issue_date; a coin with no issue_date matches by
                     issue_year within the same years
  &owned           true (have) | false (missing)
  &scope           all (default) | shared | own
  &archived        false (default) | true
  &sort            title | country | series | year (default) | denomination | material
                   | owned | purchase | price
  &order           asc | desc (default)
  * repeatable, see "Multi-value filters"
```

- The storefront rule (BR-13) and the confirmed-country gate (BR-13a) apply;
  souvenir-packaging cards are hidden when the user's setting is off (BR-15).
- `archived=true`: admins see every archived record; a user sees only archived records
  they own an instance of — so they can still find their coin (BR-10).
- `sort=material` sorts by what the column shows: the dictionary name in the request
  locale, else the free-text `material`.
- `sort=owned|purchase|price` sort by per-user aggregates (quantity owned, purchase
  total, latest visible price) computed in SQL over the whole result, not per page.

`GET /catalog/summary` takes the same filters without paging/sorting and returns
`{total, owned, missing, purchaseTotalUah, missingBudgetUah, unpricedMissing}` — the
"Каталог" KPI tiles, always consistent with the list below them. `owned` is accepted for
symmetry but ignored: choosing "missing" must not zero the tile that shows both sides.

`GET /catalog/lookup?q&countryId&limit` (`q` 1–200 chars, `limit` 1–20, default 8)
returns up to `limit` `CatalogListItem`s, unpaged. Same layer visibility and archive rule
as `/catalog`, but **no** storefront rule or confirmed gate: the user has explicitly
chosen the country, and hiding a shared record would push them into a personal
duplicate (BR-13a).

`GET /catalog/materials?countryId` returns only materials actually used by confirmed-
country records — the catalog's material filter. The full dictionary for forms is
`GET /materials` ("Reference data").

### Catalog list item

`CatalogListItem` (list, lookup, completeness tiles):

```json
{
  "id": 1,
  "country": "Україна",
  "seriesName": "Флора і фауна України",
  "denomination": {"id": 4, "value": "2.000", "unit": "hryvnia", "currencyCode": "UAH", "label": "2 гривні"},
  "denominationText": null,
  "year": 2018,
  "issueDate": null,
  "title": "Дельфін",
  "titleOriginal": "Дельфін", "originalLang": "uk",
  "titleUk": "Дельфін", "titleUkSource": "official",
  "titleEn": "Dolphin", "titleEnSource": "official",
  "variety": null,
  "catalogNumber": "KM# 123",
  "collectionGroup": "commemorative",
  "metalKind": "base",
  "composition": {"id": 13, "code": "nickel_silver", "name": "Нейзильбер"},
  "material": null,
  "marketPriceUah": "666.00", "priceSource": "UA-Coins", "priceObservedAt": "2026-08-06T12:20:27Z",
  "quantityOwned": 1,
  "purchaseTotalUah": "666.00", "purchaseTotalUsd": "16.20", "purchaseTotalEur": "15.10",
  "supportingExpensesUah": "60.00",
  "obverseImage": {"preview": "…_300.webp", "medium": "…_600.webp", "large": "…_1200.webp", "attribution": "Національний банк України"},
  "reverseImage": {"…": "same shape"},
  "thumbnailUrl": "…_300.webp",
  "isOwn": false,
  "isArchived": false,
  "archiveReason": null,
  "sourceUrl": "https://www.ua-coins.info/ua/list/512-delfin"
}
```

- `title` is the display name (`title_<locale>` → `title_original`); `country`,
  `seriesName`, `denomination.label` and `composition.name` follow the same locale. The
  raw slots are included for edit forms and the "original: …" line (BR-12).
- `denomination` is structure plus a ready label; `denominationText` is the typed-in value
  for countries without a dictionary, shown when `denomination` is `null`. `seriesName`
  already falls back to `series_text`. `composition` is the dictionary row; `material`
  holds text only where no row fits (BR-14).
- Images: three stored sizes plus the credit line; the page uses `preview` in lists,
  `medium` on the card, `large` in the lightbox. A missing larger size repeats the
  largest one available (`media.md`).
- Per-user fields: `quantityOwned`, `purchaseTotalUah/Usd/Eur` (USD/EUR at each
  purchase's date rate, `null` without a rate — BR-6), `marketPriceUah` (latest visible,
  non-suspect snapshot — BR-7), `supportingExpensesUah` (all non-`coin_purchase` expenses
  on this item, by `catalog_item_id`, `null` if none; never folded into
  `purchaseTotalUah` — BR-4).
- `isOwn` — a personal position of the current user; the frontend shows edit actions by
  it. `isArchived`/`archiveReason` drive the archived banner.
- `sourceUrl` — the "source" link: from `price_source_links`, preferring UA-Coins (its
  `external_id` is the page URL). An NBU row yields `null` on purpose — it ranks second
  only to outvote leftover uCoin rows. No suitable link → `null`, and the block is hidden.

### Catalog card

`GET /catalog/{id}` → `CatalogCard` = the list item plus: `countryId, seriesId,
denominationId, itemType, subtype, mintageAnnounced, mintageActual, weightGrams,
diameterMm, thicknessMm, shape, edgeType, edge, orientation, qualityType, quality,
catalogKm, catalogUc, catalogNumista, notes, description {general, obverse, reverse},
designers[], sculptors[], archivedAt, createdAt, updatedAt`.

The card ignores the storefront rule and the confirmed gate: a record of an inactive or
unconfirmed country opens by direct link (BR-13).

`GET /catalog/{id}/prices` → `[{id, source, grade, price, currencyCode, priceUah,
observedAt, sourceUrl, isOwn, isSuspect}]` — snapshots visible to the user (BR-7);
`isOwn` marks the user's own points on the chart.

`GET /catalog/{id}/collection-items` → the user's own purchases of this item
(`CatalogCollectionItemOut`: `id, catalogItemId, quantity, grade, acquisitionDate,
seller, purchasePrice, purchaseCurrency, purchaseRateUah, totalUah, totalUsd, totalEur,
supportingExpensesUah, storageLocation, notes`). Here `supportingExpensesUah` counts
only expenses linked to that exact purchase by `collection_item_id`; an old purchase
not covered by the backfill shows `null` even if the item has extras overall (BR-4).

### Creating and editing catalog records

| Request | Shared record | Own personal | Someone else's personal |
|---|---|---|---|
| `GET` | 200 | 200 | 404 |
| `PATCH` | 403 `shared-catalog-read-only` (admin: 200) | 200 | 404 |
| `POST …/archive`, `…/unarchive` | 403 (admin: 200) | 400 `archive-not-applicable` | 404 |
| `DELETE` | 403 (admin: see "Deleting catalog records") | 204 | 404 |

`POST /catalog` (`CatalogItemCreate`) creates a **personal** record
(`created_by` = current user). An admin creates a shared record only by sending
`shared: true` — admins collect too, so without the flag their records are personal.
`shared: true` from a regular user → `403 admin-required`. Unknown `countryId`,
`seriesId` (or one from another country), `denominationId`, `compositionId`,
`edgeTypeId`, `qualityTypeId` → `422 invalid-reference`. In the UI personal positions
are created through `POST /collection` instead ("Buying a coin not in the catalog").

`PATCH /catalog/{id}` (`CatalogItemUpdate`) accepts any subset of the create fields plus
`description`, `descriptionObverse`, `descriptionReverse`.

### Editing names

There is no separate endpoint: titles are edited with `PATCH /catalog/{id}` under the
same permissions.

- `titleUk` / `titleEn` must be non-empty (`""` → `422`); omit the field to leave the
  slot alone.
- Any value sent stamps `titleUkSource` / `titleEnSource` as `manual`, overriding
  `official` and `llm`.
- `titleOriginal` is edited the same way; it has no source marker.

```
PATCH /catalog/{id}  {"titleUk": "Різдво Христове"}  → 200, titleUkSource = "manual"
PATCH /catalog/{id}  {"titleUk": ""}                 → 422
```

There is no admin screen for this yet (`backlog.md`).

### Archiving

```
POST /catalog/{id}/archive  {reason}  → 200 {isArchived: true, archivedAt, archiveReason}
POST /catalog/{id}/unarchive          → 200 {isArchived: false, archivedAt: null, archiveReason: null}
```

- Admin only (`403 shared-catalog-read-only`); personal records → `400
  archive-not-applicable`.
- `reason` is required and non-empty after trimming (≤ 1000 chars) → else `400
  archive-reason-required`.
- Already archived / not archived → `409 archive-state`.
- Both actions are written to `audit_log`. Instances, purchases, expenses, photos and
  price history are untouched — semantics in BR-10.

### Deleting catalog records

`DELETE /catalog/{id}` → `204`.

- **Personal record:** deleted by its author together with the author's collection
  items on it and their `coin_purchase` expenses, in one transaction (BR-10).
- **Shared record:** admin only, and only as a clean-up. `409
  catalog-item-delete-conflict` if it isn't archived yet or any `collection_items` /
  `expenses` reference it. Its media and price snapshots go by cascade. The normal way to
  remove a record from the catalog is archiving.

---

## Collection

```
GET    /collection                     positions (filters below)
GET    /collection/summary             KPI tiles for the same filters
POST   /collection                     buy a coin
GET    /collection/{id}                one purchase
PATCH  /collection/{id}                edit a purchase
DELETE /collection/{id}                delete a purchase
PUT    /collection/{id}/photos/{role}  upload the owner's photo
DELETE /collection/{id}/photos/{role}  remove it
GET    /collection/countries | /series | /denominations | /materials   filter lists
GET    /collection/storage-locations   storage locations
POST   /collection/storage-locations
DELETE /collection/storage-locations?name=
```

Everything is scoped by `owner_id`; another user's purchase → `404`.

### Positions

`GET /collection` returns **positions**: one row per catalog item, all of the user's
purchases of it folded together. Paging is by position. Individual purchases are
`GET/PATCH/DELETE /collection/{id}` (a `CollectionItem` id) and
`GET /catalog/{id}/collection-items`.

Filters mirror `/catalog` on the coin's attributes — `q`, `countryId*`, `seriesId*`,
`denominationId*`, `materialId*`, `group*`, `metalKind*`, `year`, `yearFrom`, `yearTo`,
`dateFrom`, `dateTo` (on `issue_date`, not the purchase date, with the same year
fallback) — plus `grade`: a position matches if **any** of its purchases has that grade,
and its aggregates still cover **all** its purchases (grade filtering shows the whole
position).

`sort`: `release` (default; issue year, then issue date) | `date` (last purchase) |
`title` | `country` | `series` | `quantity` | `total` | `valuation` (latest price ×
quantity, the number shown) | `grade`; `order` `asc | desc` (default `desc`).

`CollectionPositionOut`: `catalogItemId, title, country, seriesName, collectionGroup,
denomination` (ready label), `year, issueDate, isArchived, archiveReason,
totalQuantity, totalSpendUah` (coin prices only, at each purchase's rate — never
extras), `supportingExpensesUah` (by catalog item, `null` if none; the frontend adds it
per `includeSupportingExpenses`), `marketValueUah` (latest visible non-suspect price ×
quantity, `null` without a price), `lastAcquisitionDate, grades[]` (distinct, sorted,
no nulls), `thumbnailUrl`.

`GET /collection/summary` (same filters, no paging) → `{collectionItems,
completedItems, coinSpendUah, relatedSpendUah, totalSpendUah, marketValueUah}` — the
"Мої монети" tiles; without filters the numbers match `/bootstrap`.

### Buying a coin

```
POST /collection
{
  "catalogItemId": 812,            // or "newCatalogItem": {...} — exactly one
  "quantity": 1,                   // ≥ 1
  "price": "250.00",               // ≥ 0: a gift or unknown price is legitimate
  "currency": "UAH",
  "purchaseDate": "2026-09-14",
  "seller": "Violity", "notes": null, "grade": "UNC",
  "storageLocation": "Вдома",      // a name, resolved by get-or-create (BR-16)
  "extraExpenses": []              // see "Supporting expenses in a purchase"
}
→ 201 CollectionItemOut
```

- Neither or both of `catalogItemId` / `newCatalogItem` → `422`. Unknown or invisible
  `catalogItemId` → `404 catalog-item-not-found`.
- The server takes the NBU rate for `purchaseDate` (BR-6), stores `purchase_rate_uah` and
  writes the `coin_purchase` expense in the same transaction (BR-4). No rate on or before
  the date → `422 exchange-rate-missing`; unknown currency → `422 unknown-currency`.
- `CollectionItemOut` (also returned by `GET/PATCH /collection/{id}`) is one purchase:
  `id, catalogItemId, title, country, seriesName, denomination, year, isArchived,
  archiveReason, quantity, grade, purchaseDate, seller, price, currency, rateUah,
  totalUah, storageLocation, notes, thumbnailUrl, marketPriceUah, obverseImage,
  reverseImage, obversePhotoIsOwn, reversePhotoIsOwn`. The images are this purchase's own
  photo where uploaded, the catalog's otherwise (`media.md`).

`PATCH /collection/{id}` accepts `quantity, price, currency, purchaseDate, seller,
notes, grade, storageLocation`; same rate errors. `DELETE /collection/{id}` → `204`,
also deletes its `coin_purchase` expense; supporting expenses stay (BR-10).

### Buying a coin not in the catalog

Instead of `catalogItemId` the body carries `newCatalogItem` — the coin the user
describes. The personal position, the purchase and the `coin_purchase` expense are
created in **one transaction** (BR-2, BR-4).

```json
"newCatalogItem": {
  "countryId": 230, "titleOriginal": "Львівський оперний театр", "issueYear": 2021,
  "collectionGroup": "commemorative",
  "compositionId": null, "material": "Нейзильбер",
  "seriesId": null, "seriesText": null, "denominationId": null, "denominationText": null,
  "metalKind": "unknown", "issueDate": null, "mintageAnnounced": null,
  "weightGrams": null, "diameterMm": null, "thicknessMm": null, "shape": null,
  "edgeTypeId": null, "edge": null, "qualityTypeId": null, "quality": null,
  "catalogNumber": null,
  "description": null, "descriptionObverse": null, "descriptionReverse": null
}
```

`NewCatalogItemIn` differs from `CatalogItemCreate` on purpose:

- **No `shared`.** The record is always personal; the purchase form is not a door into
  the shared catalog.
- **No `originalLang`, `titleUk`, `titleEn`.** Both translated slots start as the typed
  text marked `manual`; a background task detects the language and replaces the slot
  that is a translation, marked `llm` (`app/services/translation.py`). On any error, or
  without `ANTHROPIC_API_KEY`, the typed text stays. A client can't claim `official`.
- **Material is required** as `compositionId` or free `material` text — else `422`.
  Denomination and series are optional in the same two shapes (`denominationId` /
  `denominationText`, `seriesId` / `seriesText`) (BR-14).
- **One `catalogNumber`** instead of KM / UC / Numista: a collector has a number, not
  its catalogue's name.
- **`description*`** fields instead of `notes`: stored in `descriptions` under the
  request locale (`data-model.md`).
- **Required:** `countryId`, `titleOriginal`, `issueYear` (the column is `NOT NULL` and
  completeness and year filters depend on it), `collectionGroup`, and the material.

Rates, currency and storage location are resolved **before** the first insert, and bad
references (`countryId`, `seriesId`, `denominationId`, `compositionId`, `edgeTypeId`,
`qualityTypeId`) → `422 invalid-reference` before anything is written, so a rejected
purchase never leaves an orphan position. The transaction commits before the response
is sent and before the translation task runs (BR-4).

### Supporting expenses in a purchase

`extraExpenses` records shipping, holders, grading together with the purchase — with
either body shape.

```json
"extraExpenses": [
  {"category": "delivery", "amount": "60.00", "currency": "UAH"},
  {"category": "holder",   "amount": "25.00", "currency": "UAH"}
]
```

- Exactly three fields. Date and vendor come from the purchase (`purchaseDate`,
  `seller`).
- `amount > 0`; `category` is any manual category except `coin_purchase` (`422`); at most
  10 items; absent and `[]` are the same.
- Each row is stored with the new purchase's `catalog_item_id` **and**
  `collection_item_id`, with `amount` as sent — per purchase, never multiplied by
  `quantity` (BR-4).
- Rates for every currency in the request are resolved before the first insert: an
  extra without a rate rejects the whole purchase.
- The result is an ordinary expense, edited and deleted in "Гроші". Deleting it leaves
  the coin alone; deleting the coin keeps it (BR-10).

### Collection filter lists

```
GET /collection/countries
GET /collection/series?countryId
GET /collection/denominations?countryId
GET /collection/materials?countryId
```

The same shapes as `GET /countries`, `/series`, `/denominations`, `/materials`
(`CountryOut`, `SeriesOut`, `DenominationOut`, `CoinMaterial`), narrowed to values the
user has at least one purchase of — the "Мої монети" filter panel doesn't offer a
country with no coins. `CountryOut.minYear/maxYear` here are the bounds of the user's
own positions in that country.

### Storage locations

```
GET    /collection/storage-locations          → [{name, custom}]
POST   /collection/storage-locations  {name}  → 201 {name, custom}
DELETE /collection/storage-locations?name=    → 204
```

Addressed by name; ids never leave the server (BR-16). `custom = true` for the user's
own entries (deletable), `false` for the preset. `POST` is the same get-or-create a
purchase's `storageLocation` uses — an existing name is confirmed, not duplicated.
`DELETE`: the preset → `403 storage-location-shared`; a name this user can't see,
including someone else's → `404 storage-location-not-found`.

### Collection photos

```
PUT    /collection/{id}/photos/{role}   <raw image bytes>   → {obverse, reverse}
DELETE /collection/{id}/photos/{role}                       → {obverse, reverse}
```

`role` is `obverse` or `reverse` (else `422`). Same upload rules as the avatar: whole
body, JPEG/PNG/WebP ≤ 12 MB, ≤ 4000 px, oversized `Content-Length` refused before
reading → `422 invalid-image`. Always writes a new `media_files` row bound to the
**collection item** with `source = 'user_upload'`, never to the catalog record. The
answer is both sides already resolved (own photo or catalog default), so the page
repaints without a second request. Someone else's purchase → `404`. Selection and
visibility: `media.md`.

---

## Series

```
GET  /series?countryId&scope=mine|catalog      guest (scope=catalog only)
POST /series   {countryId, name, description?, startYear?, endYear?}
GET  /series/summary?countryId                → [{series: SeriesOut, summary}]
```

- Series are shared reference data; there are no personal series (BR-2).
- `scope=mine` (default): series of the user's own collection, not gated by confirmed
  countries. `scope=catalog`: the catalog's series filter — confirmed countries only
  (BR-13a).
- `SeriesOut`: `id, countryId, name` (locale), `nameOriginal, originalLang, nameUk,
  nameUkSource, nameEn, nameEnSource, description, startYear, endYear`.
- `POST /series`: admin only (`403 admin-required`); unknown country → `422
  invalid-reference`; duplicate name in the country → `409 series-exists`.
- `summary` = `{total, owned, missing, completionPercent, purchaseTotalUah,
  currentValueUah, unpricedMissing}` (BR-5). Used for the started/finished series KPI;
  the completeness screen uses `/completeness/*`.

---

## Completeness

```
GET /completeness/summary?groupBy&countryId&metalKind                       → [CompletenessGroupOut]
GET /completeness/group?groupBy&(value|unassigned)&countryId&metalKind      → CompletenessGroupOut
GET /completeness/items?groupBy&(value|unassigned)&countryId&metalKind&owned&page&pageSize
                                                                            → Page<CatalogListItem>

groupBy = series | year | denomination | material | edge | quality
CompletenessGroupOut = {groupBy, value, unassigned, label, countryId, description,
                        startYear, endYear, sortOrder,
                        summary: {total, owned, missing, completionPercent,
                                  purchaseTotalUah, currentValueUah, unpricedMissing}}
```

- Completeness by any catalog dimension (BR-5). Numerator and denominator count active
  items visible to the user; money counts all the user's instances, including those of
  archived items (BR-5, BR-10).
- A group is addressed by exactly one of `value=<id>` (for `year`, the year itself) or
  `unassigned=true` (the "no value" bucket: the column `IS NULL`). Both →
  `422 completeness-ambiguous-group`; neither → `422 completeness-missing-group`.
  `groupBy=year` has no unassigned bucket (`issue_year` is `NOT NULL`) → `422
  completeness-invalid-request`. An empty group → `404 completeness-group-not-found`.
- `label`, `countryId`, `description`, `startYear`, `endYear`, `sortOrder` come from
  the dimension's dictionary where it has one; `null` for `year` and `unassigned`.
- `metalKind` (`precious | base`) filters every dimension and every endpoint, so the
  filter carries from the list into the detail screen. `owned` (items only) narrows the
  tiles to have / missing.
- `/completeness/items` is the tile grid of a group — **not** `GET /catalog`. It uses
  `require_confirmed=False`, so a user's coins of an unconfirmed country appear (BR-13a).
  The frontend shows "open in catalog" only for `groupBy=series` with
  `CountryOut.catalogConfirmed = true`.

---

## Expenses

```
GET    /expenses?category&dateFrom&dateTo&page&pageSize&sort&order   → Page<ExpenseOut>
POST   /expenses                                                     → 201 ExpenseOut
PATCH  /expenses/{id}                                                → ExpenseOut
DELETE /expenses/{id}                                                → 204
GET    /expenses/summary                                             → ExpensesSummaryOut
GET    /expenses/chart-summary?dateFrom&dateTo                       → ExpensesChartOut
```

- `sort`: `date` (default) | `category` (taxonomy order, to group the journal) |
  `description` (what the column shows: coin title for purchases, own text otherwise) |
  `vendor` | `amount` (in UAH); `order` default `desc`.
- Body (`ExpenseCreate` / `ExpenseUpdate`): `category, amount, currency, expenseDate,
  catalogItemId?, seriesId?, vendor?, description?`. `amount > 0` → else `422` (a free
  shipping is a typo; a free coin is not — hence the purchase price allows `0`).
  `catalogItemId` optionally links the expense to an existing visible item; unknown →
  `422 invalid-reference`. Rate errors as in "Buying a coin".
- `coin_purchase` rows are managed by the purchase: creating, editing or deleting one
  here → `409 coin-purchase-managed`.
- `ExpenseOut`: `id, category, amount, currencyCode, rateUah, amountUah, amountUsd,
  amountEur` (USD/EUR at the expense date's rate, BR-6), `expenseDate, catalogItemId,
  collectionItemId, seriesId, vendor, description, coinTitle` (localized title of the
  linked coin for any expense that has one, else `null`).
- `ExpensesSummaryOut`: `categories` / `byCategory` (same list: `{category, count,
  totalUah}` for categories with spending), `totalUah, coinSpendUah, relatedSpendUah`,
  `byMonth` — the last 12 calendar months, oldest first, zero-filled
  (`{month: "YYYY-MM", coinsUah, supportingUah}`), `thisMonthUah, prevMonthUah`.
- `ExpensesChartOut` for a user-picked range (both params required; `dateFrom >
  dateTo` → `422 invalid-date-range`): `granularity` (`day` up to 31 days, else
  `month`), `byPeriod` (`{period, coinsUah, supportingUah}`, zero-filled, oldest first),
  `byCategory` for that range only.

---

## Reference data

```
GET /countries?scope=active|all|confirmed      guest
GET /denominations?countryId&scope=all|confirmed  guest
GET /materials
GET /edge-types
GET /quality-types
GET /currencies
```

- `GET /countries`: `active` (default) — the storefront; `all` — every issuer, for the
  purchase form; `confirmed` — the catalog's filter panel (BR-13a). `CountryOut`: `id,
  code, name` (locale), `nameOriginal, originalLang, nameUk, nameEn, collectVariants,
  isActive, catalogConfirmed, sortOrder, minYear, maxYear`. `minYear/maxYear` are the
  issue-year bounds of catalog items visible to this user in that country (`null` when
  none) — the year dropdowns' range.
- `GET /denominations`: `DenominationOut` = `id, countryId, currencyCode, value, unit,
  label, sortOrder`. `scope=confirmed` narrows to confirmed countries' denominations
  still used by a visible item.
- `GET /materials`, `/edge-types`, `/quality-types`: the **full** dictionaries
  (`{id, code, name}`) for the purchase form. Not to be confused with
  `GET /catalog/materials`, which narrows the filter to values present.
- `GET /currencies`: `{code, name, symbol, decimalPlaces}`.

---

## Admin

All `/admin/*` endpoints require the admin role → else `403 admin-required`.
Background and decisions: `admin.md`.

### Users

```
GET   /admin/users?page&pageSize
  → {items: [{id, email, displayName, role, isActive, emailVerified, createdAt, coinCount}],
     total, page, pageSize, summary: {totalUsers, collectors}}
PATCH /admin/users/{id}/role  {role: "user" | "admin"}  → AdminUserOut
```

`collectors` = users with at least one coin. `PATCH` returns the single row with
`coinCount: 0` (not recomputed). Refusals: `404 admin-user-not-found`,
`409 cannot-demote-self`, `409 last-admin`, `409 admin-user-ineligible` (only an active
user with a verified email can be promoted).

### Draft review

```
GET    /admin/proposals?page&pageSize            → {items: [{status, card: CatalogCard}], total, page, pageSize}
GET    /admin/proposals/{id}                     → {status, card}
PUT    /admin/proposals/{id}/photos/{role}       <raw image ≤ 12 MB> → CatalogCard
DELETE /admin/proposals/{id}/photos/{role}       → CatalogCard
POST   /admin/proposals/{id}/approve             → CatalogCard       // draft → active
POST   /admin/proposals/{id}/reject  {reason}    → ArchiveStateOut   // draft → archived
```

- Only records with `status = 'draft'`; anything else → `404 proposal-not-found`.
  Drafts come from the daily NBU catalog sync in `coin-parser` (BR-2).
- Photo upload writes a catalog photo (`source = 'manual'`); `role` is
  `obverse | reverse`; bad image → `422 invalid-image`.
- `approve` / `reject` on a record that's no longer a draft (double click, another
  admin) → `409 proposal-not-draft`. `reject` without a non-empty reason → `400
  archive-reason-required`. Both are audited.

### Job runs

```
GET /admin/jobs?job&page&pageSize
  → {items: [{id, job, status, startedAt, finishedAt, runDate, summary, stats, details, exitCode}],
     total, page, pageSize, jobs: ["update-prices", …]}
GET /admin/jobs/{id}   → one run, 404 job-run-not-found
```

Newest first. `jobs` lists job names seen so far, so the screen can filter without a
second request.

### Admin Telegram bot

```
GET    /admin/telegram        → {connected, chats}
POST   /admin/telegram/link   → {url, expiresAt}     // t.me/<bot>?start=<code>
DELETE /admin/telegram        → 204
```

The link carries a one-time `auth_tokens` code (kind `telegram_link`, 15 minutes); a new
one revokes the previous. Bot not configured → `503 telegram-not-configured`. The chat
id itself is never sent to the frontend.

---

## Integrations

### Job reporting

Scheduled jobs (in `coin-parser`) report their runs; there is no user or session.

```
POST  /internal/job-runs        {job, status?, startedAt?, runDate?, summary?, stats?, details?, exitCode?}
                                → 201 JobRunOut
PATCH /internal/job-runs/{id}   {status: ok|partial|failed, runDate?, summary?, stats?, details?, exitCode?}
                                → 200 JobRunOut
```

- Header `X-Job-Token` with the shared secret `JOB_REPORT_TOKEN`, compared in constant
  time. Wrong or missing → `401 invalid-job-token`; secret unset on the server → `503
  job-reporting-disabled` (unset disables, never opens).
- `job` matches `^[a-z][a-z0-9-]{1,63}$`. `POST` opens a run (`status` default
  `running`) but also accepts an already finished one, so a report isn't lost when
  opening failed. `PATCH` may be repeated (retry after a network error). Unknown run →
  `404 job-run-not-found`.
- A finished run is sent to every linked admin chat in the background (`admin.md`).

### Telegram webhooks

```
POST /telegram/webhook            admin bot
POST /support/telegram/webhook    support bot
```

The secret is checked from `X-Telegram-Bot-Api-Secret-Token` **before** the body is
handled: bot not configured → `404` (as if the route didn't exist), wrong secret →
`403`, otherwise always `200` — any other code makes Telegram retry the same update for
hours. The admin bot handles only `/start <code>` and `/last` from private chats and
ignores everything else silently. Support-bot behavior: `telegram-support.md`.

### Support links

```
GET  /support/telegram                         guest   → {url}
POST /support/telegram/link  {sourcePath?}             → {url}
```

`GET` is the plain public link. `POST` (signed in) returns a link that ties the chat to
the user, with `sourcePath` (≤ 500 chars kept) noting which screen they came from. Bot
not configured → `503 support-not-configured`.

### Health

`GET /health` → `{status: ok|degraded, database, redis, storage}`, each
`{status: ok|error, detail?}`. Any failing component → `503` with `degraded`. Used by the
deploy smoke check (`infra.md`).

---

## Not implemented

These exist only as deferred plans (`product.md`, "Out of scope"); there are no endpoints
for them:
user-triggered price refresh and manual price entry for personal positions, uCoin and
Excel import (dedup rules are specified in BR-3), Excel export, an in-app job queue,
catalog photo upload outside draft review, and a rates endpoint (current rates come with
`/bootstrap`; history is loaded by `coin-parser`).
