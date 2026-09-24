# Bakost Numismatics

A web app for tracking a coin collection: a shared catalog of issues, personal positions,
a personal collection, purchases and expenses, market prices, series completeness.

The shared catalog is read-only for the user -- it's maintained by the admin and a
background task against the official NBU catalog. Whatever isn't in it, the user adds as
personal positions or loads via import; those are visible only to them. Registration is
open, the interface is in Ukrainian and English.

Successor to the discontinued desktop CoinKeeper app (Electron + SQLite); the technical
name `coinkeeper` (packages, containers, domain) stays until the move to a new repository.
Written from scratch: Python backend, PostgreSQL, React frontend.

## Stack

FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis · ARQ · Playwright ·
MinIO · React 19 · TypeScript · Vite · Docker Compose

## Structure

```
docs/       specs -- read before the code
backend/    FastAPI application
frontend/   React application
```

## Where to start

1. [`docs/00-overview.md`](docs/00-overview.md) -- map of the documents and background
2. [`docs/01-scope-mvp.md`](docs/01-scope-mvp.md) -- MVP boundaries
3. [`docs/11-roadmap.md`](docs/11-roadmap.md) -- stages and the current task
4. [`CLAUDE.md`](CLAUDE.md) -- project rules

## Documentation

| | |
|---|---|
| [00-overview](docs/00-overview.md) | Overview, what survived from the previous version |
| [01-scope-mvp](docs/01-scope-mvp.md) | What we're doing and what we're deferring |
| [02-data-model](docs/02-data-model.md) | PostgreSQL schema |
| [03-api-contract](docs/03-api-contract.md) | REST endpoints |
| [04-business-rules](docs/04-business-rules.md) | Completeness, currencies, deduplication, record permissions |
| [05-integrations](docs/05-integrations.md) | NBU (rates and catalog), UA-Coins, uCoin |
| [06-media-storage](docs/06-media-storage.md) | Image storage, provenance and rights |
| [07-auth](docs/07-auth.md) | Authentication, registration, access |
| [08-ui-map](docs/08-ui-map.md) | Screens and copy |
| [09-data-migration](docs/09-data-migration.md) | SQLite -> PostgreSQL migration |
| [10-infra](docs/10-infra.md) | Docker Compose, Hetzner, CI/CD, mail, backups |
| [11-roadmap](docs/11-roadmap.md) | Order of work |
| [12-user-facing-scope](docs/12-user-facing-scope.md) | What the app does, in plain language |

## Status

As of 2026-09-04: stages 0-4 and stage 4.5 are complete. The backend (authentication, the
migrated collection database, catalog/collection/expenses/series/dashboard APIs) and the
web interface (sign-in, catalog, dashboard, coin card with price history, collection and
purchases, personal positions, series, "Не вистачає", "Гроші", settings; two themes,
Ukrainian and English, mobile layout) ship to `coins.renat-ibragimov.com` on push to `main`
(Swagger at `/api/v1/docs`).

Stage 4.5 gave the catalog a three-language model (each entity has the original in the
issuer's language plus Ukrainian and English translations, each with its own source) and a
Ukrainian pipeline: official names, series and photos from the NBU catalog, prices from
ua-coins.info, everything downloaded once into our own storage. Running the pipeline
against production data follows the runbook in `backend/README.md`. Next: a demo for the
collection's owner (`docs/11-roadmap.md`).

## Data

The real collection database and photos live in `legacy/data/` and are **excluded from
git**: the repository is public, and that data is personal -- purchases, amounts, dates.
