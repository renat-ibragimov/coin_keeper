# CoinKeeper backend

FastAPI + PostgreSQL + Redis. Stage 1 of `docs/11-roadmap.md`: the schema,
authentication, health, and the deployment contour. No catalog or collection
API yet — that is stage 3.

Specifications live in `../docs/`. When code and documentation disagree, the
documentation is wrong only if it is fixed in the same change.

## Running locally

Everything runs through docker compose from the repository root.

```bash
cp .env.example .env          # fill in placeholders; MAIL_BACKEND=console is fine
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

`docker-compose.dev.yml` adds published ports and hot reload. It is not called
`docker-compose.override.yml` on purpose: compose would load that automatically,
and the server checks out the same repository, where publishing the database
port would be a real problem. Copy it to the (ignored) override name if you want
the shorter `docker compose up`.

The API is on http://localhost:8000, OpenAPI on `/api/v1/docs`.

With `MAIL_BACKEND=console` no mail leaves the process: verification and reset
messages are written to the log, link included.

```bash
docker compose logs -f api | grep -A5 'outgoing email'
```

That is the whole point of the switch — signup works end to end locally with no
SMTP credentials.

## Working on the code directly

For tests and Alembic outside the container, point a local `.env` at the
published ports:

```
DATABASE_URL=postgresql+asyncpg://coinkeeper:<password>@localhost:5432/coinkeeper
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=http://localhost:9000
```

```bash
uv sync --extra dev
uv run alembic upgrade head
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app scripts
```

## Tests

`pytest` needs Postgres and Redis running (`docker compose up -d postgres redis`).

**Test database.** Each session creates a throwaway database on that Postgres
instance, runs `alembic upgrade head` against it, and drops it at the end.
Individual tests run inside a transaction that is rolled back afterwards, so
they neither see nor leave state behind.

Two alternatives were considered:

- *A separate schema in the development database.* Cheaper still, but the
  application would need to be schema-aware for tests only, and a failed run
  can leave half-written rows in the database being developed against.
- *testcontainers.* Would spin up its own Postgres per run. That adds a
  docker-in-docker dependency to CI, where a Postgres service container is
  already available, and buys nothing extra: the isolation is the same.

Running the real migration rather than `metadata.create_all()` is deliberate:
the migration is what will run in production, so it is the thing worth
covering. A model that drifts from the migration then fails a test instead of
failing a deploy.

Redis uses database index 15 and is flushed around every test, so rate limit
counters cannot leak between cases.

`MAIL_BACKEND` is forced to `console` in the test environment. A test that
would send real mail is a broken test.

## Scripts

```bash
uv run python scripts/promote_admin.py --email <admin-email>
uv run python scripts/promote_admin.py --email <admin-email> --demote
```

The second administrator registers through the normal form — a deliberate test
of the new-user path — and only then gets the role. The script refuses to
promote an account whose address has not been confirmed.

No email address or password is ever hardcoded, in code, tests or examples:
the repository is public.

## Layout

```
app/api/           routes, dependencies, RFC 7807 problem responses
app/services/      use cases (authentication)
app/repositories/  data access
app/models/        SQLAlchemy models — the whole schema, including tables the
                   MVP does not use yet (docs/01-scope-mvp.md)
app/schemas/       Pydantic v2, camelCase on the wire
app/core/          settings, security, rate limiting, mail backends, logging
app/db/            engine and session
alembic/           migrations
scripts/           operational scripts
```
