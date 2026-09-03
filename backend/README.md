# CoinKeeper backend

FastAPI + PostgreSQL + Redis. Stages 1–3 of `docs/11-roadmap.md`: the schema,
authentication, the deployment contour, the legacy data migration, and the
catalog / collection / expenses / series / bootstrap API. Background jobs and
external price sources arrive in stage 5.

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

## Ukrainian sources reconnaissance (stage 4.5, part A)

Read-only survey of the three sources on Ukrainian coins (the NBU catalogue,
ua-coins.info, the Ukrainian Wikipedia lists) against the shared catalogue.
Findings and the page structures it established: `../docs/05-integrations.md`,
section 8. Nothing is written to the database or to MinIO; the outputs are the
report, three source indexes next to it, and the page cache.

The parsers live in `app/ukraine_recon/`; `scripts/recon_ukraine.py` is the
command line. It reads the database through the same `DATABASE_URL` as the API,
so it runs inside the api container, the way the migration does.

### Run it on the server

`/reports` (the `migration-reports` directory, uid 1001) already exists from
the migration runbook; the cache goes next to the report so a second run does
not hit the sites again.

```bash
docker compose run --rm \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/recon_ukraine.py \
    --report /reports/recon.json \
    --cache-dir /reports/ukraine-cache \
    --catalog-export /reports/recon-catalog.json
```

Budget of a cold run: 2 pages of ua-coins (the all-years table in Ukrainian
and in Russian) plus its series and plan pages, 12 POSTs to the NBU search,
3 Wikipedia pages, robots and terms, and up to ~150 HEAD requests for images;
with the 450 ms pause per host that is a few minutes. Progress goes to stderr,
the summary to stdout.

Flags:

- `--ua-coins auto|live|wayback` — ua-coins.info does not answer from outside
  Ukraine. `auto` (default) tries the site and falls back to the Wayback
  Machine copy; the report says which one it used (`sources.ua_coins.access`).
  **Whether the site answers from Hetzner is the first thing to read in the
  report.**
- `--catalog-export FILE` writes the catalogue side (shared Ukrainian items and
  series, no personal data) so the triangulation can be re-run locally with
  `--catalog-from FILE` and without a database; `--skip-catalog` runs the
  three-source comparison alone.
- `--limit-years N` — a trial on the N most recent years (NBU is asked with a
  date filter, the others are cut after parsing).
- `--skip-images`, `--image-sample N` (default 50), `--pause SECONDS`.

Exit codes: `0` fine, `2` bad arguments, `3` no source could be read.

### What to read in the report

`recon.json` and the stdout summary: the three index sizes and how each was
reached; the year × source table with its flags; series × source with the
unmapped series to add to `app/ukraine_recon/series_map.json`; matches by
strategy A/B/C/C1 with conflicts; our items without a match; candidates to add
(coins in two or more sources that we lack); image availability and sizes; the
price ratio ua-coins/ours; title differences; the quoted terms of use.

## Legacy data migration

Moves the desktop SQLite database into PostgreSQL. Specification:
`../docs/09-data-migration.md`. Runs on the server, inside the api container.

The owner's database is not in this repository and never will be. The script is
developed against the synthetic fixture in `tests/fixtures/build_legacy_db.py`.

### 1. Put the data on the server

```bash
# from the machine holding the database, into the project directory
scp coinkeeper-2026-08-06.db <user>@<host>:<project-path>/legacy-data/
scp -r media <user>@<host>:<project-path>/legacy-data/
```

`legacy-data/` is covered by `.gitignore`. It holds personal data: purchases,
amounts, dates. It must never be committed and should be removed from the
server once the migration is done and verified.

### 1b. A writable directory for the reports

The data mount is read-only, so the report cannot go there — the first real dry
run tried and lost its report at the very end. Make a separate directory, owned
by the user the container runs as:

```bash
mkdir -p migration-reports
# The image runs as uid 1001, not as root, so the directory has to be its own.
sudo chown 1001:1001 migration-reports
```

`migration-reports/` is in `.gitignore` too: the reports carry counts and sample
rows from the real database.

The script checks this before it starts and refuses with a usage error rather
than working for twenty minutes and then failing to write.

### 2. Dry run first

Reports everything and writes nothing — not a single row:

```bash
docker compose run --rm \
  -v "$PWD/legacy-data:/legacy-data:ro" \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/migrate_legacy.py \
    --sqlite /legacy-data/coinkeeper-2026-08-06.db \
    --media  /legacy-data/media \
    --owner-email <owner-email> \
    --expect scripts/expected_legacy_2026-08-06.json \
    --dry-run --report /reports/dry-run.json
```

Read the report before going further: row counts, how many price snapshots were
flagged and by which rule, how many photo files are missing, and the checks at
the bottom. Every check must say `ok`.

Look at `media.stored` in particular. It should be close to the number of files
actually sitting in `legacy-data/media`; `stored: 0` with a large
`missingFiles` means the file names are not matching, which is what the first
dry run hit.

`--expect` turns on the numbers from the migration document (3063 catalog
items, 620 coins, 42 765,66 spent). Without it the script still reconciles the
result against the source; with it, it also holds the source to the documented
profile.

### 3. The real run

```bash
docker compose run --rm \
  -v "$PWD/legacy-data:/legacy-data:ro" \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/migrate_legacy.py \
    --sqlite /legacy-data/coinkeeper-2026-08-06.db \
    --media  /legacy-data/media \
    --owner-email <owner-email> \
    --owner-password \
    --expect scripts/expected_legacy_2026-08-06.json \
    --report /reports/migration.json
```

`--owner-password` without a value prompts for it, so the password stays out of
the shell history and out of `ps`. It has to pass the same rule as an ordinary
registration: at least 10 characters, no exception for seeding.

Images take the longest; progress is printed as they upload. If MinIO has no
bucket yet, run `docker compose up minio-init` once.

Exit codes: `0` fine, `2` bad arguments or a rejected password, `3` the source
database cannot be read, `4` the checks did not reconcile, `5` the migration
stopped (for example a non-empty target without `--resume`).

**A non-zero exit means the data is not to be trusted.** The script is meant to
catch that, so do not work around it.

### 4. After it

```bash
# the owner can sign in, and is an admin
docker compose exec api python -c "print('sign in at https://<domain>')"

# the second administrator registers through the form, then:
docker compose exec api python scripts/promote_admin.py --email <admin-email>
```

Then the manual checks from `../docs/09-data-migration.md`: open ten or fifteen
coins and look at the characteristics, photos, price and purchase.

### Useful flags

| Flag | What it is for |
|---|---|
| `--dry-run` | report only, writes nothing |
| `--skip-media` | defers the media step entirely — a fast structural pass |
| `--resume` | continue on a database that already holds data |
| `--expect <file>` | enforce a documented profile of counts |
| `--report <file>` | where the JSON report goes |

`--skip-media` writes no `media_files` rows at all rather than half of one: a
row written without processing would carry a `storage_key` pointing at an
object that was never uploaded. Re-running later without the flag fills the
table in — the migration is idempotent by primary key.

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
