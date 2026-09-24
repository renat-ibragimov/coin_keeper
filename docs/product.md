# Product

What Bakost Numismatics does, in plain language — no schema, endpoints or table names.
Start here when explaining the app to someone. Exact rules: `business-rules.md`,
`auth.md`, `media.md`.

---

## In short

An app for coin collectors. It answers four questions:

1. **Which coins exist?** — a shared catalog of issues.
2. **Which of them do I have?** — a personal collection.
3. **How much did I spend?** — purchases, related expenses, exchange rates on the
   purchase date.
4. **What is it worth now?** — market prices and a valuation of the collection.

It runs in the browser, phone included. Registration is open: anyone signs up with
email and password or with Google. The interface is in Ukrainian (default) and English.

Without an account you can browse the catalog and open any coin card — without prices
and without "in my collection" marks. The collection sections show a guest guided
examples and a sign-in button instead of real data. The home page (`/`) is a public
landing page with a hands-on demo of the collection and expenses screens.

---

## Three layers of data

The most important idea: data lives in three layers that behave differently.

### 1. The shared catalog — a reference for everyone

Coin issues: year, denomination, metal, mintage, catalog numbers, photos. An entry exists
whether or not anyone owns the coin.

- The same for everyone; visible to guests too.
- Users **cannot change it** — not add, edit or delete.
- Maintained by administrators and by a daily job that reads the official numismatic
  catalog of the National Bank of Ukraine (NBU). New Ukrainian issues arrive as drafts;
  an administrator reviews and publishes them.
- Only Ukraine's catalog is built and verified. Coins of other countries appear only in
  the collections of people who own them.

Why users can't edit it: it's shared. One person's mistake would be everyone's.

### 2. Personal positions — what the shared catalog lacks

If a coin isn't in the shared catalog, you add it yourself as a **personal position**.
It's a normal path, not a workaround.

- Visible **only to you**; you edit and delete it freely; it has your own photos.
- Behaves like any catalog entry: filters, search, completeness, valuation.

You create it **on the "Додати" page while recording a purchase**: pick a country, start
typing the name; if the coin is in the catalog, the purchase attaches to it; if not,
"about the coin" fields appear and the coin and the purchase are saved in one step.
Required: country, name, year, type and material; the rest can be filled in later. The
name you type is kept as is; Ukrainian and English versions are filled in automatically
in the background.

### 3. The collection — your actual coins

Specific purchases: when, for how much, from whom, in what grade, where it's stored.
Always private. A collection item points at a shared entry or at your personal one.

---

## What happens to my coin if an entry leaves the catalog

**Nothing.** Your coin, money and history stay.

Sometimes an entry has to leave the shared catalog — a cancelled issue, a duplicate, a
mistake. It is never deleted, only **archived**, always with a reason.

- It disappears from the catalog and search, and stops counting in completeness —
  neither in "collected" nor in "total", so a series can never show "21 of 20".
- Your item stays in your collection, the purchase still counts in spending, your photos
  and the price history stay, and the coin card still opens, with a banner giving the
  reason.

Archiving is reversible: an administrator restores the entry in one action.

---

## What is public

| What | Who sees it |
|---|---|
| Shared catalog: descriptions, specs, official photos | everyone, guests included |
| Prices collected by the daily job | signed-in users; guests see an invitation to sign in |
| Your personal positions | only you |
| Your collection, purchases, amounts, notes | only you |
| Your coin photos | only you |

Guests never see who owns what: ownership status, "my items" and the "in collection"
filter need an account. There are no public profiles, feeds or browsing of other people's
collections.

---

## Prices

**Automatically, daily.** Prices of shared-catalog entries update from the UA-Coins
site. Nothing to press; everyone sees these prices.

**Coverage is Ukrainian coins only.** UA-Coins has no other countries. Prices for US and
USSR coins are whatever came over from the owner's previous app; there's no way yet to
refresh them or enter a price by hand.

Every price is **checked before it's saved**: glued numbers, a year instead of a price, or
metal value instead of coin value are rejected and logged instead of silently inflating
your valuation.

Price history is never overwritten — every update is a new point on the chart.

---

## Photos

Where a photo comes from decides who sees it:

| Source | Who sees it |
|---|---|
| Your own upload | only you |
| NBU official photos, UA-Coins, administrator uploads | everyone |
| uCoin | only whoever imported it; others see a placeholder |

We don't own the rights to uCoin images, so they're never shown publicly.

You can upload photos for personal positions and for your collection items, with rotate,
zoom and round crop in the browser. Camera data and geotags are stripped on upload.

---

## Money

- A purchase is recorded in the currency it was made in. The NBU rate **on the purchase
  date** is filled in automatically; the original amount is never lost.
- Related expenses count too: shipping, albums, holders, literature, storage, grading.
  They can be added **with the purchase**, in a collapsible block at the bottom of the
  form; afterwards they're ordinary journal rows. Deleting the coin doesn't delete its
  shipping cost — the money was still spent.
- A setting decides whether related expenses count toward what a coin cost you.
- You see: spent on coins, spent on everything else, what the collection is worth now,
  and the difference — in hryvnias, with USD or EUR alongside.
- The app also shows **how many missing coins have no price**, so you know how far the
  "how much more to spend" estimate can be trusted.

---

## Completeness

Group your coins by series, year, denomination, material, edge or strike quality —
whichever matters for your collection — and optionally narrow to precious or
non-precious metal. Each group shows total, collected, missing, percent, money spent and
current value.

An entry counts as collected if you have **at least one** of it. Only active entries
count. Completeness follows your current filters (country, years, metal), not the whole
catalog — otherwise it would say "2,443 coins left to collect".

---

## Account

- Open registration with email and password, or with Google. An email account can later
  link Google sign-in for the same address, and the other way round.
- **Email must be confirmed**: the account is inactive until the link in the email is
  opened.
- Password reset by email link; password change in settings.
- Settings: display name and avatar, theme (light, dark, system), language, secondary
  currency (USD or EUR), catalog and collection view mode, default grade, souvenir
  packaging variants on or off, whether related expenses count toward cost, storage
  locations.
- Deleting an account removes its collection, purchases, photos and personal positions;
  the shared catalog is unaffected. There is no self-service account deletion in the
  interface yet.

## Footer, donations, support

Every page has a footer with a donation button (a monobank link) and a link to the
Telegram support bot — for ideas, questions or reaching the administrators.

---

## Out of scope

### Deferred — may come later on an explicit decision

- sales and a sold-coins archive; collecting goals; a "considering buying" list;
- varieties (mints, mint marks) as separate required entries;
- grading details: company, slab number, grade;
- automatic prices for countries other than Ukraine (Numista would need each user's own
  API key);
- entering a market price by hand; refreshing prices of personal positions;
- import from uCoin (Excel export, coin or catalog section by link) — always at the
  user's request, never a scheduled crawl;
- export of the collection to Excel;
- suggesting an entry for the shared catalog; an administrator promoting a personal
  position into it; merging duplicate entries (until then duplicates are archived);
- a shared-catalog editor in the admin area;
- mobile apps (the website works on phones);
- two-factor authentication.

### Not part of the project

- offline mode and a local database on the device;
- a desktop or portable build, or sync with one;
- stamps and other collectibles;
- yearly PDF reports.

---

## In one paragraph

You create an account — by email or with Google — confirm the address and get a shared
catalog of Ukrainian coins with photos (guests can browse it too, without prices). You
record the coins you have and what you paid. What's missing from the catalog you add
yourself. The app shows how much you've spent, what the collection is worth today and
what's left to complete each series, and updates Ukrainian coin prices by itself every
day.
