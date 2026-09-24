# Bakost Numismatics (technical name CoinKeeper) — project rules

## What this is

A web version of a desktop app for tracking a coin collection. The desktop version
(Electron/Tauri) **is discontinued and unsupported** — its sources are partly lost. The
owner's real collection data migrated to this app once, early on; nothing from the old
app remains in this repository.

Written from scratch: **Python backend + PostgreSQL + React frontend.**

## Stack — locked in, don't change without discussion

| Layer | Technology |
|---|---|
| API | FastAPI, Pydantic v2 |
| ORM | SQLAlchemy 2.0 (async), Alembic |
| DB | PostgreSQL 16 |
| Background | ARQ + Redis |
| Scraping | Playwright (headless Chromium) |
| File storage | S3-compatible (MinIO locally) |
| Frontend | React 19 + TypeScript + Vite + TanStack Query |
| Deploy | Docker Compose on Hetzner, Caddy as reverse proxy |
| CI/CD | GitHub Actions (reusable workflow), images in GHCR, deploy over SSH |
| Python | 3.12+ |

## Languages in the project

Rule number one, because it's the one that gets broken most often.

### Code — English only, no exceptions

English in code means **everything** written in it, not just identifier names:

- names: variables, functions, classes, modules, tables, columns, config keys;
- docstrings and comments, including `TODO` and `FIXME`;
- log messages;
- API error text (`detail` in RFC 7807) and exception messages;
- commit messages and branch names;
- Alembic migration names and docstrings;
- test data, fixtures, test names.

Mixed-language code is a typical source of mess: `# получаем курс` next to
`def get_rate()`, a log line `"Не удалось распарсить цену"`, a branch
`feature/архивация`. We don't do that anywhere, not even in a throwaway script.

The one exception is **data**: coin, country and series names are stored in their
original language — that's database content, not code.

### Interface — Ukrainian and English

`'uk' | 'en'`, default `'uk'`. No Russian in the interface.

Interface strings live **only in localization files**. Not a single user-facing string
sits directly in code — not in components, not in validators, not in API responses the
frontend shows verbatim.

### Documentation

`docs/` — **in English**, same as the code. It was in Russian until the 2026-09-24
repository-migration prep; translation is in progress file by file — until a given file
is converted, treat any Russian left in it as not-yet-migrated, not as an active rule.

In short: code and everything around it in the repository (commits, branches,
migrations, docs) — English; the interface — Ukrainian and English through localization.

## Rules for working with code

- All money amounts are `Numeric(14, 2)`, never `float`. The legacy database used `REAL`
  — a source of rounding errors we must not repeat.
- Stored dates are `date`/`timestamptz`, not strings. In legacy everything was `TEXT`.
- Any schema change goes through an Alembic migration. Never edit the schema by hand.
- Records in the **shared** catalog are never deleted, only archived (`is_archived` +
  reason): other users' instances, purchases and expenses hang off them. Physical
  deletion is a rare admin operation, only after archiving and only when nothing
  references the record anymore. The storefront, search and completeness are all
  computed from active records (`docs/04-business-rules.md`, item 10).
- Prices from external sources are validated **before** being written to the DB. Details
  and known parser bugs are in `docs/05-integrations.md`. Don't repeat the legacy
  mistake of fixing bad prices with one-off migrations after the fact.
- **Docs live with the code.** Every completed part of a stage updates the status in
  `docs/11-roadmap.md` and the affected documents (`08-ui-map.md`, `10-infra.md`,
  `README.md`, etc.) in the same set of commits as the code. A gap between `docs/` and
  the code is worse than no document at all.

## Three data layers — the main architectural rule

`catalog_items.created_by` determines a record's layer:

| Layer | Marker | Who writes |
|---|---|---|
| Shared catalog | `created_by IS NULL` | only admin and system background jobs |
| Personal position | `created_by = <user>` | its author, full CRUD |
| Collection | `collection_items.owner_id` | only the owner |

- **The shared catalog is read-only for the user.** They never create, change or delete
  records with `created_by IS NULL`. Attempting to — `403`.
- The original spec's rule "external sources don't create catalog records" is
  **strengthened**: now users don't create records in the SHARED catalog either. The
  only exception is the system job against the official NBU catalog.
- Import (Excel, uCoin by URL) creates **only personal positions**. If it matches the
  shared catalog, we link to it instead of creating a new record.
- The visibility filter `created_by IS NULL OR created_by = :user_id` lives **in the
  repository layer**, next to `owner_id` — not in the routes.

## Price snapshot visibility

`market_price_snapshots.created_by` works the same way:

- `NULL` — a snapshot from the central daily job (UA-Coins against the shared catalog),
  visible to everyone;
- `<user>` — manual entry, a personal-position update, an Excel import: visible and
  counted in valuation only for its author.

Collection valuation uses shared snapshots **plus the user's own snapshots**. There's no
"update price" button for shared positions in the MVP.

## Image provenance

Every `media_files` record has a `source` (`user_upload | ucoin | nbu | manual`), which
drives visibility:

- `user_upload` — the owner's private photos;
- `nbu`, `manual` — public catalog photos;
- `ucoin` — visible only to whoever imported it; a placeholder shows on the public card.

We don't own the rights to uCoin images. Downloading a copy to our own storage doesn't
change that: `source` is preserved. Details in `docs/06-media-storage.md`.

## Rules for working with data

**The repository is public.** Nothing of the following goes into git:

- any `.db`, `.env`, dumps, API keys, real collection photos

Check `git status` before committing for anything accidentally staged.

## Structure

```
docs/       specs -- read before writing code
backend/    FastAPI application
frontend/   React application
```

### `docs/current_ref/` is not documentation

A scratch folder: the owner drops screenshots there to show the assistant in the current
conversation. Its contents live for one conversation and change without notice — the
same `img.png` will be a different screen tomorrow.

**Nothing should ever link to a file from there** — not in code, not in comments, not in
tests, not in docs, not in commit or migration messages. A link to such a file goes stale
the same day it's written, and the reader ends up looking at someone else's screenshot.
If a screenshot led to a decision, describe in words what it showed and what was decided,
right in the document that decision belongs to.

## Where to start reading

1. `docs/00-overview.md` — map of the documents
2. `docs/01-scope-mvp.md` — what we're doing, and what we're deliberately deferring
3. `docs/11-roadmap.md` — current stage and the next task
4. `docs/12-user-facing-scope.md` — the same thing in plain language, for the overall picture

## What not to do

- Don't restore the desktop version, don't touch Electron/Tauri.
- Don't carry the legacy schema into Postgres as-is: it was built for SQLite, has no
  users, `REAL` for money and `TEXT` for dates. The correct target schema is in
  `docs/02-data-model.md`.
- Don't add functionality marked as deferred in `docs/01-scope-mvp.md` until the MVP is
  closed.
- Don't give the user write access to the shared catalog "for convenience": it's
  read-only, full stop. If they need their own record, that's a personal position.
- Don't run a scheduled server-side crawl of uCoin: Cloudflare, rights to someone else's
  data. Scheduled jobs are only for NBU and UA-Coins.
- Don't show uCoin images to anyone but the person who imported them.
- Don't delete shared-catalog records — archive them. This applies to background jobs
  too: the NBU catalog job archives what's been discontinued, but never deletes anything,
  ever.
- Don't write anything in Russian in the repository — see "Languages in the project".
