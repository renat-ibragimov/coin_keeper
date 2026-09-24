# CoinKeeper backend

FastAPI + PostgreSQL + Redis. Scheduled jobs (rates, prices, NBU catalog sync)
are not here — they run in the separate `coin-parser` repository and report to
this API. Local setup and the CI check list: `../docs/development.md`.

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

## Verifying media URLs on the server

`S3_ENDPOINT` (`http://minio:9000`) only resolves inside the docker network. On
the server, `S3_PUBLIC_ENDPOINT` must be set to the public media path
(`https://<domain>/media`, see `.env.example` and `docs/media.md`) so
that presigned URLs point somewhere a browser can reach. After a deploy that
touches `S3_PUBLIC_ENDPOINT` or the Caddy `/media/*` block, confirm both legs
by hand:

```bash
# 1. The API returns a presigned URL on the public host, not the internal one.
url=$(curl -s https://<domain>/api/v1/catalog/<id> | grep -o 'https://[^"]*/media/[^"]*' | head -1)
echo "$url"

# 2. That URL actually serves the object through the proxy — expect HTTP/2 200.
curl -sI "$url"
```

A `404`/`403` here usually means the Caddy `/media/*` block is still `handle`
instead of `handle_path` — MinIO is being asked for `/media/<bucket>/<key>`
instead of its own `/<bucket>/<key>`. A signature error (`SignatureDoesNotMatch`)
means the `Host` reaching MinIO does not match the host `S3_PUBLIC_ENDPOINT`
was signed for — check the reverse proxy is not rewriting `Host`.

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

## Removing white backgrounds from coin photos

Classic (non-ML) cleanup over `media_files` rows that already hold their own
`storage_key` — a white, round coin photo is cut to a transparent WebP; a
rectangular blister pack or a colored background is left alone. Rule and
runbook detail: `../docs/media.md`, "Background removal". The
classifier is `app/services/media_background.py`; the command line is
`scripts/remove_photo_backgrounds.py`.

```bash
# dry run: classifies every candidate, writes nothing
docker compose run --no-deps api python scripts/remove_photo_backgrounds.py --dry-run
```

Read `migration-reports/nobg-review.html` before applying: it shows a
before/after thumbnail for every photo the classifier would cut, and a table
of everything skipped, grouped by reason. `migration-reports/nobg-review.csv`
(UTF-8 with BOM, opens cleanly in Excel) has the same rows plus the exact old
storage key of each one — that pairing is the rollback plan, since the
original is never deleted or overwritten.

```bash
# write the cut images and repoint the rows — long runs from tmux
docker compose run --no-deps api python scripts/remove_photo_backgrounds.py --apply

# re-run against specific rows only (a retry, or after fixing something)
docker compose run --no-deps api python scripts/remove_photo_backgrounds.py --apply \
  --only-ids 101,102,103
```

Idempotent: a row whose `storage_key` already carries the `-nobg` marker this
script writes is skipped without a network call, so re-running the same
command touches nothing twice.

**Rollback** for one row: the CSV's `oldKey` and the row's current (`-nobg`) keys share the
same base and the same set of sizes, so `thumbnail_key`/`variants` are mechanically
reconstructible from `oldKey` alone — no need to have recorded them separately.

```bash
docker compose exec api python -c "
from app.core.media_keys import preview_key_of, primary_key_of, stored_variants, variant_key
from app.db.session import get_session_factory
from app.models import MediaFile
import asyncio

async def main():
    old_base = 'catalog/42/obverse/ab12cd34'  # oldKey from the CSV, minus _<size>.webp
    async with get_session_factory()() as session:
        row = await session.get(MediaFile, 123)  # mediaFileId from the CSV
        sides = sorted(int(s) for s in row.variants)
        keys = {side: variant_key(old_base, side) for side in sides}
        row.storage_key = primary_key_of(keys)
        row.thumbnail_key = preview_key_of(keys)
        row.variants = stored_variants(keys)
        await session.commit()

asyncio.run(main())
"
```

The `-nobg` object itself is not deleted by this — it is simply no longer referenced.

### Re-trimming photos cut before the margin trim existed

The cut now ends by cropping to the alpha bbox (`app.services.media_background.trim_to_alpha`)
so a coin fills its frame regardless of how much empty margin the source photo had — otherwise
tiles show coins at different visible sizes. `--trim` re-applies that crop to rows already cut
by an earlier run: it walks only `-nobg` rows, re-crops the stored object, and rewrites it at its
own key (no new key is minted — the pre-cut original is still the rollback plan).

```bash
# dry run: computes old/new size for every -nobg row, writes nothing
docker compose run --no-deps -v /home/deploy/coinkeeper/migration-reports:/app/migration-reports \
  api python scripts/remove_photo_backgrounds.py --trim --dry-run

# apply: re-encodes the trimmed object under its existing key
docker compose run --no-deps -v /home/deploy/coinkeeper/migration-reports:/app/migration-reports \
  api python scripts/remove_photo_backgrounds.py --trim --apply
```

`migration-reports/trim-review.csv` has the old/new pixel size and the trimmed fraction per row;
`migration-reports/trim-review.html` is a before/after sheet on a sample of the trimmed rows.
Idempotent the same way as the main mode: a row already trimmed to its bbox is reported unchanged
and left alone, so a second `--trim --apply` over the same rows applies nothing.

## Admin title editing

Admin title editing (`titleUk`/`titleEn`/`titleOriginal` on a shared record)
is the existing `PATCH /catalog/{id}` — see `../docs/api.md`,
"Editing names": it now always stamps `*_source = 'manual'` and rejects an
empty string. No new endpoint, no new screen — the admin edit form is part
of the deferred shared-catalog editor (`../docs/product.md`, "Out of scope");
the API contract is already there.

## Layout

```
app/api/           routes, dependencies, RFC 7807 problem responses
app/services/      use cases (authentication)
app/repositories/  data access
app/models/        SQLAlchemy models — the whole schema, including tables the
                   app does not use yet (docs/product.md, "Out of scope")
app/schemas/       Pydantic v2, camelCase on the wire
app/core/          settings, security, rate limiting, mail backends, logging
app/reference_data/ countries, denomination units, materials — data and parsers,
                   seeded into the database by migration 0003
app/db/            engine and session
alembic/           migrations
scripts/           operational scripts
```
