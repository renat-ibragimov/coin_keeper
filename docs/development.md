# Development

How to run, test and check the project locally. Deployment and servers: `infra.md`.
Backend runbooks (operator scripts, photo background removal): `backend/README.md`.

## Prerequisites

- Docker with Compose v2.
- [`uv`](https://docs.astral.sh/uv/) for the backend. If it's installed to
  `~/.local/bin`, non-interactive shells (agents, scripts) may not have it on `PATH` —
  prefix commands with `export PATH="$HOME/.local/bin:$PATH"`.
- Node.js + npm for the frontend.

## Full stack in Docker

```bash
cp .env.example .env    # fill in placeholders; MAIL_BACKEND=console is fine locally
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

API on http://localhost:8000, OpenAPI on `/api/v1/docs`. With `MAIL_BACKEND=console`
verification and reset emails go to the API log:
`docker compose logs -f api | grep -A5 'outgoing email'`.

`docker-compose.dev.yml` is deliberately not named `docker-compose.override.yml`: the
server checks out the same repository, and an auto-loaded override would publish the
database port there.

## Backend tests

Tests need Postgres and Redis only. Without a root `.env`, start them with inline values:

```bash
DOMAIN=localhost POSTGRES_PASSWORD=devpass S3_ACCESS_KEY=minioadmin S3_SECRET_KEY=minioadmin \
  docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis
```

The password must be `devpass`: `backend/tests/conftest.py` defaults to
`postgresql+asyncpg://coinkeeper:devpass@localhost:5432/postgres`. Each test session
creates a throwaway database, runs `alembic upgrade head` on it (the real migrations, not
`create_all`) and drops it; each test runs in a rolled-back transaction. Redis uses DB 15
and is flushed around every test.

```bash
cd backend
uv sync --extra dev
uv run pytest -q                       # or: uv run pytest tests/test_catalog_read.py -q
```

## Checks (same as CI)

CI (`.github/workflows/build-deploy.yml`) runs these in order and stops at the first
failure. Run all of them before saying "checks pass" or pushing.

```bash
# backend/
uv run ruff format --check .
uv run ruff check .
uv run mypy app scripts
uv run pytest -q

# frontend/
npm run format:check                   # Prettier runs FIRST in CI — easy to forget
npm run lint -- --max-warnings=0       # CI is stricter than a bare `npm run lint`
npm run typecheck
npm test
npm run test:seo
npm run build
```

Don't pipe a check to `tail`/`head` when you need its result — the pipe hides the exit
code, and a failing `ruff check` once slipped into a commit that way.

## Frontend

```bash
cd frontend
npm ci
npm run dev          # Vite on :5173
npm run gen:api      # regenerate src/shared/api/generated/openapi.ts from the deployed OpenAPI
```

**`npm run dev` talks to the deployed backend, not a local one:** `vite.config.ts`
proxies `/api` to `https://coins.renat-ibragimov.com` so cookies work same-origin.
Anything you do in the dev UI while logged in there acts on real data. To work against a
local API, point the proxy target at `http://localhost:8000` temporarily (don't commit it).

Every user-facing string goes to `src/shared/i18n/uk.json` and `en.json`;
`i18n.test.ts` checks that the two stay in sync.

### Screenshots without real credentials

There are no dev credentials for the deployed API, and creating accounts there without
the owner's say-so is off-limits. For visual checks, drive the local Vite server with
mocked API responses: `playwright-core` + the system Chrome
(`executablePath: '/usr/bin/google-chrome'`, `args: ['--headless=new']`), with
`context.route('**/api/v1/**', …)` mocks and `localStorage` keys `ck-theme`,
`ck-locale`, `ck-remember=1` set in an init script so the app restores a session from
mocked `/auth/refresh` + `/auth/me`. Screens with real data are checked by the owner.

## Migrations

```bash
cd backend
uv run alembic revision -m "short_english_name"    # write it by hand, review autogenerate output
uv run alembic upgrade head
```

Migrations run automatically when the API container starts, so pushing one to `main`
changes the production database — take a dump first and get explicit approval.
