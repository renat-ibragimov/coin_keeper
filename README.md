# Bakost Numismatics

A web app for tracking a coin collection: a shared catalog of issues, personal positions,
a personal collection, purchases and expenses, market prices, completeness.

The shared catalog is read-only for users — it's maintained by admins and a daily sync
against the official NBU catalog. Whatever isn't in it, a user adds as a personal
position, visible only to them. Registration is open; the interface is in Ukrainian and
English. `coinkeeper` is the technical name (packages, containers) until the repository
is renamed.

## Stack

FastAPI · SQLAlchemy 2.0 · Alembic · PostgreSQL 16 · Redis · MinIO ·
React 19 · TypeScript · Vite · Docker Compose · Caddy

Background jobs (NBU rates and catalog, UA-Coins prices) run in the separate
`coin-parser` repository.

## Structure

```
AGENTS.md   rules for coding agents (Codex, Claude Code) and contributors
docs/       specs — start at docs/README.md
backend/    FastAPI application
frontend/   React application
```

## Getting started

- [`docs/development.md`](docs/development.md) — local setup, tests, CI checks
- [`docs/product.md`](docs/product.md) — what the app does
- [`docs/README.md`](docs/README.md) — map of all specs
- [`AGENTS.md`](AGENTS.md) — project rules

## Status

The MVP is live at `coins.renat-ibragimov.com` (Swagger at `/api/v1/docs`), deployed by
GitHub Actions on push to `main`. Open work: [`docs/backlog.md`](docs/backlog.md).

## Data

The repository is public. Real collection data, database dumps, `.env` files and photos
never go into git.
