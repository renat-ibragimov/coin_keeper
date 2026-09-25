# UI

Screens, navigation and the visual rules of the web frontend (`frontend/src`). UI copy
lives in `frontend/src/shared/i18n/{uk,en}.json`; this document quotes a Ukrainian label
only to identify a screen or control. Business rules: `business-rules.md` (BR-N).
Endpoints: `api.md`.

---

## Screens and routes

| Screen | Route | Access |
|---|---|---|
| Landing | `/` | guests; signed-in users are redirected to `/collection` |
| Overview ("Огляд") | `/collection` | everyone; guests see onboarding |
| My coins ("Мої монети") | `/collection/coins` | everyone; guests see onboarding |
| Completeness ("Комплектність") | `/collection/completeness` | everyone; guests see onboarding |
| Completeness group detail | `/collection/completeness/:groupBy/:value` | signed in |
| Money ("Гроші") | `/collection/money` | everyone; guests see onboarding |
| Add ("Додати") — purchase or expense | `/collection/add` | signed in |
| Edit purchase | `/collection/coins/:id/edit` | signed in |
| Catalog | `/catalog` | everyone |
| Coin card | `/catalog/:id` | everyone |
| Settings | `/settings` | signed in |
| Administration | `/admin` | admins; others are redirected to `/collection` |
| Privacy policy, terms | `/privacy`, `/terms` | everyone |
| Sign-in, registration, password reset request, "check your email" | `/login`, `/register`, `/forgot-password`, `/check-email` | open the auth dialog over a public page |
| Email verification, password reset, Google completion | `/verify-email`, `/reset-password`, `/google-complete` | standalone compact screens |

All routes are declared in `frontend/src/app/App.tsx`. After sign-in the user lands on
the overview.

### Redirects

Retired paths redirect and keep the query string:

- `/dashboard` → `/collection`
- `/series`, `/collection/series` → `/collection/completeness`;
  `/series/:id`, `/collection/series/:id` → `/collection/completeness/series/:id`
- `/missing`, `/collection/missing` → `/catalog?owned=false` (the catalog's own
  "not in collection" filter, same query format `useCatalogFilters` writes)
- `/expenses` → `/collection/money`
- `/collection/new`, `/collection/coins/new` → `/collection/add` (so old
  `?catalogItemId=` links still work)
- `/collection/:id/edit` → `/collection/coins/:id/edit`
- any unknown path → `/catalog`

---

## Guest access and authentication

- **Guests** can browse the catalog, open coin cards (without prices and without the
  ownership layer, BR-2 and `auth.md`), and open the four collection sections, which
  show onboarding (see "Empty states") with a permanent sign-in button.
- **Auth dialog.** Sign-in, registration, password reset request and the "check your
  email" message open in one shared modal (`AuthDialog`) over the current page. A normal
  sign-in keeps the user on the same page; sign-in started from an "add" action
  continues to the purchase form for that coin without saving anything automatically.
  Direct `/login`, `/register`, `/forgot-password`, `/check-email` open the same dialog
  over a public page. Closing it leaves the site usable; the handled sign-in request is
  removed from history state so "Back" doesn't reopen it.
- **Registration** has a hidden honeypot field (`website`): invisible, out of tab
  order, `autocomplete="off"`, `aria-hidden`. If filled, the form answers as on success
  and nothing is created. Login errors never reveal whether an address exists; the reset
  request answers the same either way.
- **Email links** (`/verify-email`, `/reset-password`) and `/google-complete` keep their
  own addresses and use a compact screen with a way back to the site. `/verify-email`
  always asks for a new password. Google sign-in runs in a separate window; its errors
  and notices (an existing account to link, an address Google doesn't vouch for) come
  back into the dialog of the original tab.
- **Sign-out.** Public pages and the four collection root sections keep their address
  and switch to the guest view. Add/edit pages go to `/collection/coins`, the
  completeness detail to `/collection/completeness`, settings and admin to `/`. The auth
  dialog does not open after a voluntary sign-out. Signing out in one tab signs out the
  viewer's other open tabs too, the same way.
- **Session expiry** switches the UI to guest mode and offers to sign in again with an
  explanation.
- **Form drafts.** Unsaved add/edit forms for purchases and expenses are kept in memory
  of the current tab for the same account (`sessionDrafts.ts`); sign-out or an account
  change clears them. An interrupted save is never retried automatically.

---

## Navigation and layout

### Header and account menu

Two main contexts: **"Моя колекція"** (`/collection`) and **"Каталог"** (`/catalog`);
**"Адміністрування"** (`/admin`) appears only for `role === 'admin'`, set apart by a
divider.

The account menu (avatar or placeholder silhouette, `displayName || email`, chevron)
holds: user block, interface language (UA/EN), theme (light / dark / system — "system"
follows `prefers-color-scheme` live), Settings, Administration (admins), Sign out. On
desktop, language and theme are also separate switches in the header and the duplicate
rows are hidden from the menu; on phones they live only in the menu. Menus and drawers
close on outside tap, item choice, route change and Escape (`shared/lib/useDismissable`).

### Collection tabs and mobile bottom bar

Every `/collection/*` page shows a second, centered row of tabs: Overview, Coins,
Completeness, Money (rendered by `AppLayout` from the location).

The phone bottom bar is contextual: outside "Моя колекція" (catalog, coin card) it has
two items, Catalog and My collection; inside it has five — Catalog, Overview, Coins,
Completeness, Money. It is fixed, height `--bottom-nav-inset` (56px +
`env(safe-area-inset-bottom)`), with `viewport-fit=cover` and `100dvh`; content, toasts
and modals are offset by the same inset.

Page headers are centered everywhere (`PageHeader align="center"`): title, subtitle and
actions stacked; the breadcrumb slot, where present, stays left-aligned.

### Footer, support and donation

`SiteFooter`: "made in Ukraine", copyright, links to `/privacy` and `/terms`, a support
link and a donation button. The support link comes from the API (`/support/telegram`,
or a personal `/support/telegram/link` for a signed-in user — `telegram-support.md`); on
failure a toast says support is unavailable. The donation dialog links to the donation
jar and shows a QR code (`qrcode.react`, lazy-loaded).

### Page scrolling

On desktop the page scrolls inside the area under the header (`AppLayout` →
`.scrollArea`, `data-scroll-area`), not the window: the header is its own row, the
scroll container has `overflow-y: auto` and `scrollbar-gutter: stable`. The gutter is
therefore always reserved (no sideways jump between short and long screens or when a
modal locks scrolling), and the header always reaches the window edge. On phones
(`max-width: 900px`) the document scrolls again so the browser can collapse its address
bar; the header is `position: sticky`.

Scroll-to-top and background locking go through `shared/lib/pageScroll.ts`
(`scrollPageToTop`, `lockPageScroll`), which find the live container — `ScrollToTop`,
`Pagination`, `Modal` and `Lightbox` don't need to know which one it is.

---

## Visual system

All colors, radii, shadows and motion are tokens in
`frontend/src/shared/theme/tokens.css`; components never paint the theme by hand, so
both themes stay in sync on every screen.

### Themes

Two equal themes, light by default, switchable in the header; the choice is remembered,
and without one the app follows `prefers-color-scheme`.

- **Light — "archive stone".** A neutral warm mineral background, ivory for raised cards,
  charcoal-brown text, brass **only as an accent**, never on large surfaces. A light
  neutral background is chosen for the coins: silver, copper and nickel read better on
  it than on dark.
- **Dark — graphite and blued steel.** All large surfaces are **pure neutral grey
  (R = G = B)**; hierarchy comes from lightness only. Warmth comes only from "hardware":
  brass accents, active navigation, buttons, focus, the coins themselves. Resting borders
  are neutral steel (`--color-border`); brass marks only hover, focus, selected and
  active states. No brown, coffee, leather or wood tones on surfaces.
- **Surface ladder** (both themes): `bg` → `surface-sunken` → `surface` →
  `surface-control` → `surface-raised` → `surface-hover`. Structural panels (filters,
  charts, tables, overview columns) use `Card variant="panel"`: one step lower, smaller
  radius, almost no shadow. Raised cards get a top-edge highlight and a two-layer shadow.
- **Owned / absent colors.** `--color-owned` / `--color-absent` (text, per-theme for
  contrast) and `--color-owned-icon` / `--color-absent-icon` (badge fills, same in both
  themes) are separate from `--color-success` / `--color-danger`, which belong to
  financial deltas and errors. `--color-owned-surface` tints owned catalog tiles and rows.

### Typography

- **Playfair Display** (`--font-display`) belongs to **content**: page titles, coin and
  series names, auth screen titles, large price values, stat tile values. It is applied
  explicitly (`.display` or an own `font-family`), never to all `h1–h3`.
- **Source Sans 3** (`--font-body`) for all interface text: panel and dialog titles,
  form sections, tabs, buttons, table headers, labels, helper text.
- Numbers are always `tabular-nums`.
- Any font must have full Ukrainian coverage (`є ї ґ`, apostrophe).

### Texture, decoration, motion

- **Page texture:** one seamless 256×256 WebP tile per theme
  (`frontend/src/assets/textures/`), drawn once globally by `body::before` in
  `tokens.css` (`position: fixed`, under `#root`). Opacity `--page-texture-opacity`
  (0.055 light, 0.065 dark) — above ~0.1 the grain reads as noise. Off under
  `prefers-reduced-data: reduce` and `forced-colors: active`. The texture belongs to the
  page background only: header, cards, panels, tables, fields, menus and modals paint
  opaque surfaces over it.
- **Decoration:** CSS and SVG only, no heavy raster backgrounds. Gradients only as the
  material of a control (the primary button), not as scene decoration. No glass
  (`backdrop-filter`), glows or halos behind coins; the photo stand is a plain surface.
- **Motion:** CSS transitions only, 120–180 ms (`--duration-fast`, `--duration-normal`,
  `--ease-standard`); hover lift ≤ 2px, coin photo zoom 1.5–2.5%. No continuous
  animation or springs. `prefers-reduced-motion: reduce` disables motion globally except
  `.motion-essential` (the spinner).

### Scrollbar

One global style in `tokens.css`: 8px, rounded thumb `--color-border-strong`
(`--color-text-muted` on hover), transparent track, no arrow buttons. Blink ignores all
`::-webkit-scrollbar-*` rules once `scrollbar-width` is set, so the standard properties
live under `@supports not selector(::-webkit-scrollbar)` (Firefox only). No screen styles
its own scrollbar.

### Icons

`lucide-react` everywhere, `strokeWidth={1.75}`; never text glyphs (`×`, `✓`, `☰`,
`↑`…) for things that have an icon. Color is never the only carrier of meaning: owned
status also has an icon and an accessible label.

---

## Shared patterns

### Filter panels

The catalog and "Мої монети" share one shell (`FiltersShell` / `FiltersToolbar` in
`shared/ui`): a framed row of fields, a row of active-filter chips, and a bottom line
with "shown X of Y", view switch, sort field and direction. Filter state lives in the
URL (`useCatalogFilters`, `useCollectionFilters`), so links and "Back" keep it.

- **Desktop:** fields apply immediately.
- **Phones (< 900px) — apply-on-confirm:** fields hide behind a "Фільтри" button that
  opens a drawer. The drawer edits a local **draft** copied from the applied filters when
  it opens; "Застосувати" writes the draft to the URL at once, closing without it
  discards the draft. Each field is full width in the drawer so its dropdown fits.
- **Catalog fields:** search, country, series (cascades from the chosen countries,
  `GET /series?countryId`; changing the country resets series and denomination; the
  series list has its own search box), period (see below), denomination, type
  (circulation / collector / commemorative / other), metal, metal kind
  (precious / base), availability (owned / missing; signed-in only).
  `scope` (`all | shared | own`) and `archived=true` are read from the URL but have no
  control (see "Not built").
- **"Мої монети" fields:** the same set plus **grade** (fixed `GRADES` list). Grade
  selects positions that have at least one purchase with that grade, while the
  position's aggregates still count all its purchases. Country, series and denomination
  lists come from `GET /collection/countries`, `/series`, `/denominations` — only what
  the user owns.
- **Catalog search** matches word prefixes (`to_tsquery` with `:*` per word, built
  server-side; tsquery syntax characters are ignored). Country and catalog numbers match
  as substrings.
- **Selects:** `Select`, `MultiSelect` and `Combobox` share one chrome
  (`Select.module.css`). A select can take `triggerLabel` (show custom content in the
  trigger) and `active` (highlight a non-default pick). `Combobox` = free typing plus a
  suggestion list.

### Period filter

`shared/ui/PeriodFilter.tsx`: one dropdown in the filter row instead of loose year
fields. The panel lists three modes — **year**, **year range**, **date range** — and
under it the active mode's fields: one `Combobox` for a year, two for a range, two text
inputs plus a `react-day-picker` calendar for dates.

- Switching mode doesn't clear other modes' values; only the active mode is sent
  (`periodToApiParams()` in `shared/lib/periodFilter.ts`), so hidden values never leak
  into the query.
- The trigger shows a summary (`1990`, `1990–2010`, `06.09.2026–11.09.2026`) or the mode
  name; its width is fixed (210px) so the toolbar doesn't jump.
- Year bounds come from `shared/lib/yearRange.ts` (`computeYearBounds`,
  `buildYearList`); `clampPeriod()` clamps year values to the new country's bounds when
  the country changes (dates aren't clamped).
- URL keys: `year`, `yearFrom`, `yearTo`, `dateFrom`, `dateTo`, and `periodMode`
  (written only when the mode isn't "year range", so old `yearFrom`/`yearTo` links still
  work). Date range filters by `issue_date`, falling back to `issue_year` (`api.md`).
- **Calendar:** `react-day-picker` with its `uk` / `enUS` locales, because the native
  date input takes its language from the browser, not from the app. Text inputs accept
  `dd.MM.yyyy` (uk) / `MM/dd/yyyy` (en). Themed by overriding `--rdp-*` with project
  tokens. Month and year are dropdowns (`captionLayout="dropdown"`), the year range is the
  country's year bounds. Day clicks move the boundary whose text field was focused last
  (`activeField`), not whichever is closer; a hint above the calendar says which.

### Tables

One table component for the whole site, `shared/ui/DataTable`: panel, header, row
rhythm and the sort control. Features add only column widths and cell content. Used by
the catalog table, "Мої монети" (`PositionTable`) and the Money journal.

- **Every column sorts**, with the same `SortHeader`: clicking the active column flips
  direction, another column starts ascending. State lives in the URL (`?sort&order`).
  The catalog and "Мої монети" also offer the sort fields in the toolbar dropdown.
- **Sort icon:** one double chevron (`SortIcon`) in all states; the active half is
  highlighted. A spacer of the icon's width on the other side (`.sortButton::before`)
  keeps the label itself centered.
- **Alignment:** everything centered except names and descriptions (left). Headers are
  centered by the global `th { text-align: center }` in `tokens.css`; the default
  alignment is set on `.table` and inherited, so a class on a cell always wins.
- **Fixed geometry:** every column has an explicit width, and long text (coin name,
  series, material) is clamped to two lines, so row height doesn't change between pages.
  In "Мої монети" the coin name sits in a fixed two-line box above its second line
  ("1965 · 1 рубль"), and the "archived" badge sits on that second line.
- Whole rows are links (stretched-link pattern: keyboard, middle click and context menu
  work), except the actions column.

### Coin images

One component, `CoinImage`. A missing photo and a photo that failed to load look the
same: a stylized coin in theme colors — no broken `<img>`, no retries of a dead URL.
Size by place (`shared/lib/coinImage.ts`): lists 300px, card 600px, lightbox 1200px,
each offering the next size as 2x in `srcset`; `loading="lazy"`. Real photos use
`fit='contain'`: nothing is cropped. No `mix-blend-mode` in either theme — photos lie
on the card surface. Most photos have transparent backgrounds (`media.md`, background
removal); a few still show their solid background as a rectangle, and the frontend
doesn't mask that.

### Coin titles, material and response language

- **Title** = `title_<locale>` → `titleOriginal` (`shared/lib/coinTitle.ts`); the API
  sends `title` by the same rule. When a translation is shown, the card also names the
  original and its language (BR-12).
- **Material** in lists comes from `shared/lib/coinMaterial.ts`: dictionary name
  (`composition.name`), else free text (`material`), else nothing. `metalKind` is a
  filter facet, not a material — only the coin card falls back to it. On catalog tiles
  the material is shortened to two words (`shortMaterial`), full text in the tooltip.
  There is no material dictionary on the frontend.
- **Series fallback:** where a series is shown and a circulation coin has none, the UI
  shows "Обігові монети" (`seriesLabel`, display only, not a filter value).
- **Response language:** the client sends `Accept-Language` from the current locale and
  clears the whole query cache when the locale changes.

### Money and dates

Formatted by `shared/lib/format.ts` from API strings, tabular numerals. The secondary
currency (`USD`/`EUR` setting) is shown small next to UAH (`shared/lib/secondaryAmount.ts`,
BR-6).

### Empty states

- **Empty collection** — a guest, or a user whose `bootstrap.dashboard.isEmpty` is true
  (no instances and no personal positions). The same criterion on every screen, no local
  heuristics. The four sections (Overview, Coins, Completeness, Money) then show a header
  without actions and one `CollectionOnboarding` card with three example slides marked
  "Приклад" (overview: KPIs, spend vs value, series progress; coins: views, search and
  filters, instances; completeness: grouping, progress, missing coins; money: expense
  kinds, chart period, journal categories). Numbers are demo data on the client. Guests
  get "Увійти" (opens the auth dialog); users get "Перейти до каталогу" and "Додати
  монету". Real tables, filters and zero KPIs are not rendered. Loading, errors and empty
  filter results are never replaced by onboarding.
- **Onboarding card:** `width: 100%; max-width: 560px`; slides share one CSS grid so the
  card never changes size between slides or sections; hidden slides are out of the
  accessibility tree and focus order. Arrows and dots loop; ←/→ and Home/End work;
  horizontal swipe doesn't block vertical scroll; no autoplay; changing section opens
  its first slide.
- **Other empty states** use `EmptyState` (`shared/ui/States.tsx`); "nothing found"
  after filters or search is borderless and full width (`variant="plain"`). Icons:

  | State | Icon |
  |---|---|
  | Overview | `LayoutDashboard` |
  | My coins | `Coins` |
  | Completeness ("Мої" empty, "show all") | `Layers` |
  | Money | `Wallet` |
  | Nothing found after filters/search | `SearchX` |
  | `ComingSoon` placeholder | `Hourglass` |
  | `ErrorState` | `CircleAlert` |
  | `EmptyState` default | `CircleDashed` |

### Destructive actions

Actions that change money say what else happens: deleting an instance says the purchase
expense goes with it (BR-10); the purchase form says instance and expense are created
together. Deleting an instance or a purchase invalidates the same set of queries
(`COLLECTION_DEPENDENT_KEYS`, includes expenses), so every aggregate refreshes together.

### Localization

UI strings live in `shared/i18n/{uk,en}.json`; `i18n.test.ts` checks the key sets match
(plural forms aside). Language switches without reload; default `uk`, stored in
`user_settings.locale`. Exception: the long-form copy of the landing page
(`features/landing/copy.ts`) and the legal pages (`app/legal/copy.ts`) is kept in typed
`uk`/`en` objects next to those pages.

---

## Landing page

`/` for guests (`features/landing`): hero, collection and expense demos, two main CTAs
and a closing invitation. "Create collection" opens registration for a guest (or goes to
`/collection` when signed in); "browse catalog" goes to `/catalog`. The collection demo
filters its three sample coins by search, series and year and sorts by amount spent;
the expense demo's period limits only its chart and category limits only its journal.
Demo tables scroll horizontally on phones and rows aren't clickable. The dark wordmark
is generated by `frontend/scripts/build-brand.py` (`npm run brand`): lighter letters,
original gold shield and coin.

---

## Catalog

`/catalog` — the storefront of the shared catalog plus the user's personal positions
(BR-2), read-only. Only records of a `catalog_confirmed` country appear here (BR-13a).

- **Views:** cards and table (`?view=cards|table`; `?view=map` falls back to cards). The
  choice is stored in account settings for signed-in users, with a local cache
  (`ck.viewMode.catalog` / `ck.viewMode.collection`); guests default to cards and keep
  their choice under `ck.viewMode.catalog.guest`. An explicit `?view=` always wins.
- **Page size** 30 in the card grid (a multiple of 1/2/3/5 columns).
- **CTA on tile and row:** not owned → "Додати до колекції" (purchase form with the coin
  preselected); owned → "У моїй колекції" status (plus "Додати ще екземпляр" on the
  tile). Both forms of the action share `--catalog-action-width` so the column doesn't
  change width between pages. Guests get an add button that opens the auth dialog.
- **Owned highlight:** owned tiles and rows get `--color-owned-surface` (25% owned color
  over the raised surface) plus an owned-color frame/icon; the table has a leading
  `CircleCheck` column with an accessible label. Hover stays visible on top of the tint.
- **Tiles:** obverse and reverse side by side as two squares (`.media` 2:1, 2px gap), so
  a round coin fills its square; material to the right of the denomination.
- **Table:** Coin (≤ 26% width), country, series, year, denomination, material, and the
  rest; `min-width` 980px.
- **Personal positions** carry an "own" badge. There is no create or edit entry in the
  catalog — personal positions are created from the purchase form.
- **Archived records** are hidden unless `archived=true` is in the URL; then admins see
  the whole archive and users only archived records they own an instance of (BR-10).

### Catalog KPI tiles

`CatalogSummaryTiles` from `GET /catalog/summary`: owned / total, missing (with "no
price: N" when some are unpriced), spent on coins, budget to complete. Computed with the
same filters as the list **except `owned`**, so the tiles always show both sides of the
coverage ratio. Not links. Shown only to a signed-in user with at least one coin
(`dashboard.collectionItems > 0`); otherwise the endpoint isn't called.

---

## Coin card

`/catalog/:id` (`features/catalog/card/CoinCardPage.tsx`). Data: `GET /catalog/{id}`,
`GET /catalog/{id}/prices`, `GET /catalog/{id}/collection-items` (the viewer's own
instances only). The card opens by direct link regardless of storefront rules (BR-13).

- **Header:** breadcrumbs and a Back button that follows history (so catalog filters in
  the URL survive; on a direct link it goes to the catalog). Title per the title rule,
  subtitle "denomination · country · year", badges for own position and archived.
- **Archived banner** on top, with `archiveReason`: the record left the catalog and
  completeness, and the user's coins, purchases and price history are kept.
- **Photos:** obverse and reverse via `CoinImage`; "enlarge" opens the lightbox, only
  for a side that has a file.
- **Sections**, all visible at once (no tabs): description (only when the record has
  `descriptions`; general paragraph plus obverse/reverse columns, current locale with
  fallback to the other), specifications (only filled fields, grouped: identity, issue,
  technical, catalog numbers — KM# / UC# / Numista on one line, mintage actual or
  announced with a note), price history, and the viewer's instances (only when owned).
- **Ownership block:** a status sentence with a round icon badge (`CircleCheck` /
  `CircleMinus`) — "you have this coin" / "not in your collection"; quantity; bought for
  and current value only when owned (value = price × quantity; the headline cost
  includes supporting expenses per the setting, BR-4); the action "Додати до колекції"
  or "Додати ще екземпляр", both to `/collection/add?catalogItemId=`. The current-price
  block is framed, with source and date.
- **Price history:** an interactive `lightweight-charts` chart — wheel zoom, drag,
  range presets (1M / 6M / 1Y / all); the line uses regular snapshots; suspect snapshots
  (`isSuspect`) and the viewer's own (`isOwn`) are separate markers and don't affect the
  axis scale; a tooltip at the cursor shows date, price, source, grade and flags.
  Source names are localized (`sources.*`).
- **Instances** (`InstancesList`): a list, not a table — each row repeats its labels
  above the values, two columns on narrow screens. Purchase date first with quantity
  under it, seller, price in the purchase currency (and UAH if different), rate as
  "X ₴ per 1 $", grade, note, and actions: edit (`/collection/coins/{id}/edit`) and
  delete (`DeleteInstanceDialog`, which names the coin and says the purchase expense is
  deleted too).
- **Guests** see the catalog part; price and ownership blocks show a locked state with
  sign-in.
- **Not found** (someone else's personal position or no such record) → a not-found
  state with a link to the catalog.
- **Admins** see `ProposalActions` on a `draft` card (see "Coin proposals").

---

## My coins ("Мої монети")

`/collection/coins`. `GET /collection` returns **positions**, not purchases: one tile or
row per catalog item, with all its purchases aggregated (`api.md`). Individual purchases
are edited and deleted on the coin card.

- **Filters:** see "Filter panels".
- **KPI tiles** (`CollectionSummaryTiles`, shared with the overview): coins in
  collection, total spent, current value, difference — from `GET /collection/summary`
  with the page's filters. Spent is money on the coins in the collection, not on the
  hobby, so it can be lower than the overview's. With `includeSupportingExpenses` off,
  spent and difference use coin prices only and the "incl. related" line is hidden;
  the overview always counts everything.
- **Tile** (`PositionCard`): a large obverse (unlike the catalog's pair), grade badge
  (one grade, several joined with " · ", none → no badge), quantity, spent, current value
  (or "no price"), last purchase, and a "new release" badge for an issue date within the
  last 30 days (`shared/lib/recentRelease.ts`). The whole tile links to the coin card; the
  one action is "+ Додати ще екземпляр" (`?catalogItemId=`).
- **Table** (`PositionTable`): coin, country, series, quantity, spent, current value,
  last purchase, grade; whole row links to the coin; no row actions.
- **Sort:** last purchase (`lastAcquisitionDate`), name, amount (`totalSpendUah`).

---

## Add ("Додати")

`/collection/add` — one page for everything that costs money. The first field is
**type**: "coin purchase" (default) or any manual expense category (`MANUAL_CATEGORIES`),
written to the URL (`?type=coin_purchase`, `?type=delivery`, …). Fields that mean the
same on both sides — amount/price, currency, date, seller, note — survive a type change
(`carried.ts`). Layout: a centered column, the selected coin block (`SelectedCoin`,
shared with the edit page) and a 640px form card.

### Coin purchase branch

1. **Country** — searchable select over all issuers (`GET /countries?scope=all`),
   Ukraine first.
2. **Coin name** — a text field with live suggestions within that country
   (`GET /catalog/lookup`, 300 ms debounce, from two characters; BR-13a exceptions).
   Suggestions show photo, name, country · year · denomination and own / owned badges.
   Country comes first because a name alone ("10") means nothing. The field is `text`,
   not `search` (Chrome clears search inputs on Escape).
3. **Suggestion picked** → the form collapses to the coin block, photos, "choose another
   coin" and the purchase fields.
4. **No suggestion** → the **"about the coin"** block opens for a new personal position:
   year\*, denomination, series, coin type\*, material\*, metal; under "more details":
   mintage, weight, diameter, thickness, edge, strike quality, shape, **one catalog
   number** field (stored in `catalog_number`), and three descriptions (general,
   obverse, reverse → `descriptions` in the request locale). Required: country, name,
   year, type, material.
   - Material, denomination and series are `Combobox` (dictionary + free text); edge and
     quality are dictionary-only `Select` (BR-14). Year is a `Combobox`, newest first.
   - Sent as **one** `POST /collection` with a nested `newCatalogItem` (BR-4).
5. From the catalog, `?catalogItemId=N` preselects the coin and skips the search.

- **Unit price starts at 0** (coins found in change or received as gifts exist); the zero
  is selected on focus so typing replaces it. An emptied field still asks for a number.
- **Own photos:** hovering obverse/reverse shows "change photo" (a small permanent button
  on touch screens); it opens the circular crop dialog (`CoinPhotoCropDialog`). For a new
  coin there are two "+ photo" placeholders. Photos are kept in form state and uploaded
  with sequential `PUT`s after `POST /collection` succeeds — no server-side drafts
  (`media.md`).

### Supporting expenses in the purchase

A collapsed "related expenses" block at the end of both purchase variants (BR-4). Each
row: category · amount · currency, with a remove button; date and seller come from the
purchase. Opening the block adds the first row; "add another" adds more. A row with an
untouched amount is ignored; an unreadable or zero amount is a field error (zero is not
allowed here). Sent in the same `POST /collection` as `extraExpenses`. In Money these
rows are ordinary manual expenses linked to the coin; deleting one never touches the
coin.

### Expense branch

Amount, currency, date, seller, description; the category is the type selector. An
optional **related coin** block: a coin name field with the same suggestions across all
issuers (no country step) that only **links** an existing shared or own record
(`catalogItemId`) and never creates one. The picked coin shows both as the large block
above the form and as a short line inside the related-coin block, each with "choose
another coin".

### Entry points

Every "Додати монету" button (collection, overview, completeness, empty states, catalog
tiles and rows, coin card) goes to `/collection/add`, with `?catalogItemId=` when the
coin is known. "+ Додати витрату" on Money goes to `/collection/add?type=other`. Editing
an existing expense stays a modal on the Money page.

---

## Overview ("Огляд")

`/collection`, all from one `GET /bootstrap`.

- **Header:** centered title and a fixed subtitle.
- **Four equal KPI tiles**, each a stretched link: coins in collection
  (`collectionItems`) → My coins; total spent (`totalSpendUah`, with related spend as a
  third line) → Money; current value (`marketValueUah`) → Money; difference
  (`marketValueUah − totalSpendUah` and %) → Money. Icons `Coins` / `Wallet` /
  `TrendingUp` / `Scale`; `StatTile` sets its own compact padding.
- **My series:** every series with at least one owned coin (`seriesBreakdown`, no limit,
  BR-9), sorted by completion descending with finished series last; a progress ring
  "X of Y" and the nearest missing count. Each row links to
  `/collection/completeness/series/{id}`. The list fills the card height and scrolls
  within it. Empty state only when no series is started.
- **Finance** (right column): spent on coins + related = total; current value;
  difference and % (computed on the client); missing budget with "no price: N". No
  period dynamics — there's no history of valuations.
- **NBU rates:** USD and EUR with their date from `exchangeRates`; missing → "no data".
  The rates card stretches so both columns end level (`align-items: stretch`).
- **By country:** `owned of count`, share and a bar; a full-width row under the columns.
- Loading → skeletons of the same shape; error → `ErrorState` with retry. Phones: one
  column, KPI tiles 2×2.

---

## Completeness ("Комплектність")

`/collection/completeness` — completeness grouped by any field (BR-5; `api.md`,
`/completeness/*`).

- **Toolbar:** search by group label (400 ms debounce), country filter, `groupBy`
  switch (series / year / denomination / material / edge / strike quality), a
  **metal-kind** select, scope "Мої" / "Усі", sort (by completion % / by value).
- **Metal kind is a filter, not a grouping:** it narrows whichever `groupBy` is active.
  Its trigger names the current pick and is highlighted when not "all" (`active`); an
  invisible copy of the default label reserves its width so the toolbar never re-wraps
  (`MetalKindSelect`).
- **Scope:** "Мої" (default, not written to the URL) shows groups with `owned > 0`;
  "Усі" (`scope=all`) shows every group — a client-side filter, no new request. If no
  group is started, "Мої" shows "nothing started yet" with a "show all" button.
- **Rows:** progress ring, group name (link), country and period, and four numbers —
  collected (owned/total), spent, current value, missing. Opening a row carries the
  current `countryId` and `metalKind` into the detail screen so its numbers match the
  row.
- **Detail screen** (`/collection/completeness/:groupBy/:value`): its own toolbar —
  country, metal kind, "owned only" — seeded from the list but independent. Tiles come
  from `GET /completeness/items`, never from `GET /catalog` (BR-13a). "Open in catalog"
  appears only for `groupBy=series` when the country is `catalogConfirmed`; otherwise a
  note says only the personal collection is shown.
- Empty collection → onboarding; no groups at all for the chosen field/country → "no
  records yet"; nothing matches the search → the generic "nothing found".

---

## Money ("Гроші")

`/collection/money` — the hobby's financial journal. Coin purchases (`coin_purchase`)
appear automatically; other expenses are entered by hand.

- **KPI tiles:** total on the hobby, on coins, related, this month (with the delta to
  last month, or "no spending last month").
- **Chart period** (`ExpensesPeriodPicker`): presets 1M / 3M / 6M / 1Y (default 1Y) plus
  two date fields; a preset recomputes the dates from today, a manual date clears the
  preset highlight. `dateFrom > dateTo` is validated on the client (no request) and
  rejected by the backend with `422`. On desktop the date labels sit left of the fields
  on the preset row; on phones they sit above.
- **Charts** from `GET /expenses/chart-summary?dateFrom&dateTo`, shown only if the user
  has any expenses (`recharts`, two cards ~2:1, stacked under 900px):
  - spending by period — stacked bars, coins below and related above; daily for ranges
    ≤ 31 days, monthly otherwise, with zero-filled gaps; X-axis
    `interval="preserveStartEnd"`;
  - by category — a donut with legend (category, amount, share) for the same range; an
    empty range shows a text instead of an empty ring.
  - Tooltips follow the cursor exactly (`isAnimationActive={false}`,
    `allowEscapeViewBox={{ x: false, y: true }}`, `wrapperStyle={{ zIndex: 1 }}`).
  - Chart colors are read from theme tokens at render and re-read on theme change
    (`useChartPalette`).
  - `GET /expenses/summary` (fixed windows) feeds only the KPI tiles and category chips.
- **Table:** description — for `coin_purchase` the coin title links to its card; a
  manual expense linked to a coin shows the coin as a second, muted link line. Amount in
  UAH and a USD column (headed), and an "Actions" column.
- **Row actions — pencil and bin on every row.** For manual expenses they edit (modal)
  and delete the expense. For purchase rows they act on the **instance**: pencil →
  `/collection/coins/{collectionItemId}/edit` (returns to Money with filters and page),
  bin → `DeleteInstanceDialog`, which deletes the coin together with its purchase expense
  (BR-10). A purchase row without `collectionItemId` has no actions.
- **"+ Додати витрату"** (header and empty state) → `/collection/add?type=other`.
- **Empty collection** → onboarding. A non-empty collection with no expenses keeps the
  header action and shows a borderless notice with its own CTA; KPIs and charts are not
  rendered.

---

## Settings

`/settings`, two columns; every control saves on its own (one request per change, no
"Save" button).

- **Profile:** role badge, avatar (`AvatarSection`, circular crop), email (read-only),
  display name (saved on Enter or blur, unchanged value sends nothing), password change
  (`PasswordForm`; a Google-only account sets a new password without the current one),
  and — when Google sign-in is enabled on the backend — linking a Google account (its
  address must match the account's).
- **Appearance:** theme (light / dark / system), interface language (applies at once),
  secondary currency (USD / EUR).
- **Catalog and collection:** default view for the catalog and for My coins, default
  grade for new purchases (`GRADES`), show packaged variants as separate cards (BR-15),
  count supporting expenses in collection value (`includeSupportingExpenses`, BR-4), and
  the default storage location — a `Combobox` of used names, Enter adds a new one, a
  custom name can be deleted after confirmation (BR-16).

---

## Administration

`/admin`, admins only (`admin.md`). Three tabs via `?section=jobs|users|proposals`,
default jobs.

### Background jobs

Job runs, newest first: state, job, start, duration, the one-line self-report; a job
filter appears once more than one job has reported. States are colored: success green,
partial yellow, error red, running neutral. A run stuck in "running" for over six hours
shows yellow with a "looks stopped" note — a killed job can't report its own death.
Clicking the state opens the run card (`JobRunDialog`): start/end, duration, data date,
exit code, report, counters as name–value pairs, and details (only failed runs have
them, `admin.md`). Empty → "no runs yet".

### Telegram notifications

A card above the list (`TelegramCard`): connected / not connected and one button.
"Connect" opens the bot in a new tab with a one-time code and asks to press Start; the
chat connects itself via the webhook, so the screen polls the status every 3 seconds and
reports success. Disconnect is the same button. The chat id never reaches the browser.

### Users

Two tiles (total users, users who added at least one coin) and a table: user, sign-up
date, email verified, coin count, role with "make admin" / "remove role". The button is
disabled for oneself (`isSelf`) and for promoting an inactive or unverified account
(`cannotPromote`) — the same guards as the backend (`api.md`).

### Coin proposals

A grid of `draft` records (`CoinCard` in `review` mode). Empty → "no proposals yet".
Clicking a card opens the regular coin card, where `ProposalActions` shows "awaiting
review" and three actions: **publish**; **reject** (confirmation dialog; the record is
archived with a fixed reason, no free text); **edit** — a modal with the same fields as
the new-coin form (`NewCoinFields`) plus obverse/reverse photo replace/remove.
"Save and publish" updates fields, then photos, then publishes, in that order. After any
action: a toast and back to `/admin?section=proposals`.

---

## Legal pages

`/privacy` and `/terms` (`app/legal/LegalPage.tsx`), content in `app/legal/copy.ts` per
locale. For guests, the logo and back links lead to the landing page.

---

## Not built

Deliberately absent from the UI (see `product.md`, "Out of scope", and `backlog.md`):

- **Edit or delete a personal position.** The API supports it (`PATCH` / `DELETE
  /catalog/{id}`, BR-10), but no screen offers it; `PATCH /catalog/{id}` is used only by
  the admin proposal editor.
- **Archive / unarchive a shared record** — API only, no admin UI.
- **Catalog `scope` and "show archived" controls** — the parameters work from the URL,
  there is no control for them.
- **Manual price entry and per-position price refresh** (BR-7), completeness map view,
  sales, uCoin import, Excel export, collecting goals.
- **Offline mode.** The PWA manifest and icons ship (installable); there is no service
  worker.
- **List virtualization** — lists are paginated instead.
