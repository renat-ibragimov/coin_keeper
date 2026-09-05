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

## Verifying media URLs on the server

`S3_ENDPOINT` (`http://minio:9000`) only resolves inside the docker network. On
the server, `S3_PUBLIC_ENDPOINT` must be set to the public media path
(`https://<domain>/media`, see `.env.example` and `docs/06-media-storage.md`) so
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

## Ukrainian pipeline (stage 4.5, part B)

The step that writes. It links our catalogue to the three sources, fills the
gaps, takes the official names, series and photographs from the National Bank
and records one price per coin. What each step does and why:
`../docs/05-integrations.md`, section 9.

`scripts/ukraine_pipeline.py` is the command line; the steps are in
`app/ukraine_pipeline/`. It reads the database through the same `DATABASE_URL`
as the API and uploads to the same MinIO, so it runs inside the api container.

**Nothing is written without `--apply`.** The default is a dry run: it fetches,
decides, reports, and changes nothing.

### 0. Back up the database first

Not optional. The pipeline rewrites the name of every Ukrainian coin, and
`--apply` has no undo.

```bash
# The dump is written inside the container and copied out: never through
# stdout of `docker compose exec`, which corrupts binary output.
docker compose exec -T db pg_dump -U coinkeeper -Fc -f /tmp/before-ukraine.dump coinkeeper
docker cp "$(docker compose ps -q db)":/tmp/before-ukraine.dump ./before-ukraine.dump

# A dump nobody checked is not a backup.
head -c 5 before-ukraine.dump          # must print PGDMP
pg_restore --list before-ukraine.dump | head
```

### 1. Dry run, whole pipeline

```bash
docker compose run --rm \
  -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py \
    --report /reports/ukraine.json \
    --cache-dir /reports/ukraine-cache \
    --review-out /reports/bridge-review.csv
```

Read the summary before anything else:

- `sources` — is `ua_coins` `live` or `wayback`? Live means the prices come
  from the site itself.
- `bridge` — `linked` / `toReview` / `withoutCandidates`. On the rehearsal
  against a copy of the production data: 797 / 160 / 103.
- `series.unmappedNames` — anything listed here needs a line in
  `app/ukraine_recon/series_map.json` before the real run.
- `gaps.created` — how many coins the issuer has and we do not (~237).
- `gaps.wouldDuplicate` — coins not created because one of our own unlinked
  records is already in that year and face value. Reviewed in step 3b.
- `repair-gaps.filled` — which columns records from an earlier run were missing.
- `merge.candidates` — pairs of our records that look like one coin.
- `titles.wikipediaDisagreements` — where Wikipedia tells a different story.

### 2. Link what is certain

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps bridge \
    --report /reports/ukraine-bridge.json --cache-dir /reports/ukraine-cache \
    --review-out /reports/bridge-review.csv
```

### 3. Review the rest by hand

`bridge-review.csv` has one row per candidate, ordered by score. Put `yes` in
the first column of the row that is the coin, leave the others empty. The
`claimedBy` column names the record that already took that coin — when it is
filled, the two records are a duplicate in our catalogue and only one of them
can win.

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps bridge \
    --apply-review /reports/bridge-review.csv \
    --report /reports/ukraine-bridge-2.json --cache-dir /reports/ukraine-cache
```

Only one row per item may say yes; two is an error, not a preference.

### 4. Series, gaps, repair

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps series,gaps,repair-gaps \
    --report /reports/ukraine-gaps.json --cache-dir /reports/ukraine-cache \
    --duplicates-out /reports/gaps-duplicates.csv
```

Series before gaps: gaps creates records under the NBU series names, and
renaming ours afterwards would collide with what it just made. The script
enforces the order; `--steps` only chooses which of them run.

`repair-gaps` goes back over the records an earlier run created and fills the
columns it left empty — the face value, the metal kind, the series. It writes
only into empty columns, so a correction someone made by hand stays.

### 4b. The coins gaps did not create

`gaps-duplicates.csv` holds the coins gaps refused to create because one of our
own unlinked records is already sitting in that year and face value. It is in
the same format as the bridge's review file: `yes` against the row that is the
same coin, and the bridge links **our** record to that card.

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps bridge \
    --apply-review /reports/gaps-duplicates.csv \
    --report /reports/ukraine-bridge-3.json --cache-dir /reports/ukraine-cache
```

A pair that is **not** one coin needs no answer here: link our record to its
real card in the ordinary review, and the next run of gaps will create the
missing coin because nothing unlinked stands in its slot any more.

### 4c. Duplicates already created

Records the first run of gaps created on top of ours are merged, not deleted
by hand.

```bash
# list the pairs
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --steps merge \
    --merge-out /reports/merge-review.csv \
    --report /reports/ukraine-merge.json --cache-dir /reports/ukraine-cache

# then, with yes against the pairs that are one coin
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps merge \
    --apply-merge /reports/merge-review.csv \
    --report /reports/ukraine-merge-2.json --cache-dir /reports/ukraine-cache
```

`sharedWords` and `nbuDescription` are what tell four coins of one name apart:
the leopard, the lion, the griffin and the man are in the card's prose, never
in its title. The survivor is the record made from the card; everything the old
record carried — the owners' coins and photographs, purchases, sales, offers,
price history, links — moves onto it, and the report prints the instances and
the money on both records before and on the survivor after. **They must add
up.** Run it without `--apply` first: a dry run prints exactly the same
arithmetic and moves nothing.

### 4d. Titles

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps titles \
    --report /reports/ukraine-names.json --cache-dir /reports/ukraine-cache
```

### 5. Photos, in portions

The NBU serves 1600 px PNGs of three to four megabytes each. Take them a few
hundred at a time; the cache means an interrupted run costs nothing to repeat,
and `alreadyStored` in the report says how far it got.

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps photos --limit 200 \
    --report /reports/ukraine-photos.json --cache-dir /reports/ukraine-cache
```

Repeat until `itemsLeft` is 0. `totalMegabytes` in the report is what actually
went into MinIO, and `itemsWithoutAnyImage` is what no source has a picture of.

### 6. Prices

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps prices \
    --report /reports/ukraine-prices.json --cache-dir /reports/ukraine-cache
```

`suspect` and `byRule` say what failed the price checks; those snapshots are
stored flagged, not dropped, and stay out of the collection value.

### Flags

- `--steps bridge,series,gaps,repair-gaps,merge,titles,photos,prices` — any
  subset, run in that order whatever order they are written in.
- `--limit N` — stop `photos` and `gaps` after N items.
- `--duplicates-out FILE` — where `gaps` writes the coins it did not create;
  `--apply-review` reads it back.
- `--merge-out FILE`, `--apply-merge FILE` — the duplicate pairs, and the
  reviewed answer.
- `--merge-b-out FILE`, `--apply-merge-b FILE` — `merge-b`'s own orphan/twin
  review CSV and its reviewed answer, a different shape of pair from
  `--merge-out` (that one is `gaps.py`'s own duplicates).
- `--ua-coins auto|live|wayback|skip` — `auto` tries the site and falls back to
  the Wayback Machine copy.
- `--since-year N` — only coins issued in or after that year, for a trial.
- `--pause SECONDS` (default 0.45), `--cache-dir DIR`.
- `--steps circ-reclassify,circ-bridge,circ-gaps,circ-titles,circ-mintage,circ-photos`
  — the circulation steps below, same rule: any subset, always in this order.
- `--circ-review-out FILE`, `--apply-circ-review FILE` — `circ-bridge`'s own
  review CSV and its reviewed answer, kept apart from `--review-out` /
  `--apply-review` so running both bridges together cannot have one overwrite
  the other's file.

Exit codes: `0` fine, `2` bad arguments, `3` the NBU could not be read,
`5` the run stopped on a condition it cannot continue past.

## Circulation coins (stage 4.5, part A, item 1)

Ukraine's ~197 unlinked circulation records — kopecks 1/2/5/10/25/50 and
hryvnias 1/2/5/10 — go through a separate group of steps in the same script:
`circ-reclassify, circ-bridge, circ-variants, circ-gaps, circ-titles,
circ-mintage, circ-photos`. They share the runner, the report and
`app/ukraine_pipeline/catalog.py` with the steps above, but read different
sources — the Wikipedia mintage table instead of the three commemorative
ones — and the bridge here needs no fuzzy score: a (face value, unit, year)
key is either held by one of our records or it is not. `circulation` is not
clean, though: the legacy import heuristic also left commemorative coins
already linked to the NBU numismatic catalogue in there (rule 11,
`../docs/04-business-rules.md`) — `circ-reclassify` moves those out first,
and the other five steps skip any that are still NBU-linked regardless. What
each step does and why: `../docs/05-integrations.md`, section 10.

Nothing is fetched unless the step needs it: `--steps circ-photos` alone
touches neither the commemorative catalogue nor the Wikipedia mintage table,
since `circ-titles` and `circ-photos` do not read the table at all.

### 1. Dry run

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py \
    --steps circ-reclassify,circ-bridge,circ-variants,circ-gaps,circ-titles,circ-mintage,circ-photos \
    --report /reports/circ.json --cache-dir /reports/ukraine-cache
```

Read `circ-gaps.skippedNoType` — a (denomination, year) the mintage table
names but the type map (`app/ukraine_pipeline/circ_types.py`) has no range
for is not created, and is worth a look before `--apply`.

### 2. Reclassify NBU-linked records

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-reclassify \
    --report /reports/circ-reclassify.json --cache-dir /reports/ukraine-cache
```

Read `circ-reclassify.officialWithoutNbuLink` before moving on: a non-empty
list is a `circulation` record with an official title but no NBU catalogue
link at all — worth a person's look, not an automatic move. Run this before
anything else touches `circulation`: the other circ-* steps skip NBU-linked
records regardless, but reclassifying first means the run below never even
counts them as candidates.

### 3. Link what is certain

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-bridge \
    --circ-review-out /reports/circ-bridge-review.csv \
    --report /reports/circ-bridge.json --cache-dir /reports/ukraine-cache
```

`circ-bridge-review.csv` holds one row per record that shares a (denomination,
year) with another of ours — two quality variants of the same coin imported
from uCoin, most likely. Put `yes` in the first column of the one that stays;
apply the same way `bridge-review.csv` is applied:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-bridge \
    --apply-circ-review /reports/circ-bridge-review.csv \
    --report /reports/circ-bridge-2.json --cache-dir /reports/ukraine-cache
```

### 3b. Variants — the duplicates circ-bridge's review left unresolved

`circ-bridge-review.csv` rows left unresolved on purpose (the standing
`catalog_variants` gap, not a bridge decision — `../docs/05-integrations.md`,
section 10) become variants of whichever record circ-bridge just linked to
Wikipedia. Run after circ-bridge (and after applying its review, so the base
of each slot is already linked):

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-variants \
    --circ-variants-review-out /reports/circ-variants-review.csv \
    --report /reports/circ-variants.json --cache-dir /reports/ukraine-cache
```

Named automatically from the duplicate's own stored title ("вдавлений
тризуб") or material text (magnetic/non-magnetic steel); the rest need a
person to fill in `variantName` in `circ-variants-review.csv`, then:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-variants \
    --apply-circ-variants-review /reports/circ-variants-review.csv \
    --report /reports/circ-variants-2.json --cache-dir /reports/ukraine-cache
```

Read `personalInstancesOnVariant` — not blocking, just worth a look: a
duplicate carrying someone's own coin is archived like any other, the
instance itself untouched. This step also assigns `subtype` (the 2018
hryvnia changeover, and any denomination like it) from a record's own
`weight_grams`/`diameter_mm` before naming anything — two records that come
out with the *same* subtype are a real duplicate and proceed as above; two
with different subtypes are legitimate distinct designs and neither is
archived. Read `subtypesAssigned` once, then run circ-mintage's refresh
below — it is what actually clears `circ-mintage.ambiguous` for those
records.

### 4. Gaps, titles, mintage

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply \
    --steps circ-gaps,circ-titles,circ-mintage \
    --report /reports/circ-gaps.json --cache-dir /reports/ukraine-cache
```

`circ-mintage.ambiguous` is worth reading once: it is only ever the 2018
hryvnia changeover, and only for a record with no `subtype` set to say which
of the two 2018 figures is its own.

### Refresh mintage after the multi-mint sum fix

`circ-mintage` used to leave an already-filled `mintage_actual` alone and
only report a disagreement (`circ-mintage.discrepancies`); the 2026-09-05 fix
(`../docs/05-integrations.md`, section 10) changed what the table's own
number *is* for 1992 — the only year split across two mint-name sections —
by summing both mints' entries instead of taking whichever one
`parse_mintage_table` happened to return last. Any record `mintage_actual`
was filled against the old code is now a discrepancy, not a match, and a
plain re-run of step 4 above would only report it, not fix it.
`--circ-refresh-mintage` recomputes and overwrites `mintage_actual` on every
non-NBU-linked circulation record instead:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-mintage \
    --circ-refresh-mintage \
    --report /reports/circ-mintage-refresh.json --cache-dir /reports/ukraine-cache
```

`--dry-run` first prints `circ-mintage.refreshed` and its `old → new`
examples without writing anything. Records `circ-mintage.ambiguous` still
skips (the 2018 hryvnia changeover, no `subtype` set) are untouched either
way.

### 5. Photos, in portions

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-photos --limit 5 \
    --report /reports/circ-photos.json --cache-dir /reports/ukraine-cache
```

`--limit` here counts *types*, not records — there are twelve since the 1
hryvnia split below, so one run with no limit is normally enough; `typesLeft`
says whether to repeat it.

### 6. Refresh photos after a type-map split

Idempotency ("both sides already stored — leave it") means a type-map change
does not fix already-stored photos on its own: after the 1 hryvnia
1992/2004 split (`../docs/05-integrations.md`, section 10), every 2004-2017
record was still holding the pre-split card's (wrong) photo, and a plain
re-run would have skipped every one of them as already done.
`--circ-refresh-types` deletes a named type's stored `nbu` photos first, so
the normal pass re-fetches instead of skipping:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps circ-photos \
    --circ-refresh-types hryvnia_1_2004 \
    --report /reports/circ-photos-refresh.json --cache-dir /reports/ukraine-cache
```

The key is the type a record groups under *today*, by the current type map —
not whatever type it was originally photographed under. `--dry-run` first
prints `refreshedItems` without deleting anything.

`hryvnia_1_2004` has no National Bank card at all (`typesWithoutCard`) and,
as of 2026-09-05, no confirmed ua-coins.info id either — see
`../docs/05-integrations.md`, section 10, for what was checked and why it
stayed unconfirmed. Once a real id is found, set
`app.ukraine_pipeline.circ_types.BY_KEY["hryvnia_1_2004"].ua_coins_id` and
run `--circ-refresh-types hryvnia_1_2004` again; the step already knows how
to fetch from ua-coins.info instead of the National Bank when a type carries
that id and no card.

### 7. Jubilee bridge — six specific records, one search each

Six jubilee 1-hryvnia records (2004, 2005, 2010, 2012, 2015, 2016), moved to
`commemorative` by hand outside circ-reclassify and never NBU-linked at all
(`../docs/05-integrations.md`, section 10). Not part of `circ-*` — a
standalone step, found by shape, not by id:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --steps jubilee-bridge \
    --jubilee-review-out /reports/jubilee-review.csv \
    --report /reports/jubilee.json --cache-dir /reports/ukraine-cache
```

Every candidate goes to the CSV regardless of score — there is no
auto-apply here, unlike `bridge`/`circ-bridge`. Read `noCandidates` first:
live reconnaissance found no 1-hryvnia NBU card for any of the six themes at
all (section 10), so an empty result is expected until a person broadens the
search. Put `yes` against the right row, then:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps jubilee-bridge \
    --apply-jubilee-review /reports/jubilee-review.csv \
    --report /reports/jubilee-2.json --cache-dir /reports/ukraine-cache
```

This only writes `price_source_links`; it does not touch `source_key`. Once
a record is linked, re-run the part B steps below on it — `titles`,
`photos`, `repair-gaps` — the same way any newly-linked record is picked up,
since they all read links back from the database rather than from this run's
own state.

### 8. merge-b — the legacy Excel remainder that already has a twin

A 2026-09-05 diagnosis of the same part-B remainder found 136 shared
Ukrainian records with no National Bank link at all, not the ~103 the
earlier estimate assumed — and that 118 of the 136 are not gaps, they are
duplicates: the legacy Excel migration imported them under a Russian uCoin
heading next to a record `gaps.py` (part B) already created for the same
coin from the National Bank's own card. Needs no network at all — everything
it compares is already in our own database:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --steps merge-b \
    --merge-b-out /reports/merge-b.csv \
    --report /reports/merge-b.json --cache-dir /reports/ukraine-cache
```

One row per orphan, `suggestedTwinId` filled in when a candidate in its own
(year, denomination) slot clearly leads the runner-up (`suggestedAction:
merge`); a close call is `manual`, an empty slot is `no-twin` (the six
jubilee 1-hryvnia records from step 7 above, and other one-off records with
no National Bank card at all, land here). `../docs/05-integrations.md`,
section 10, explains why `bridge`/`inventory-b`'s own open-search threshold
never surfaced these pairs on its own. Only `merge` rows marked `yes` are
applied, straight through `merge.apply_merges` (the same function `merge`'s
own step already uses for the duplicates `gaps.py` makes):

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps merge-b \
    --apply-merge-b /reports/merge-b.csv \
    --report /reports/merge-b-2.json --cache-dir /reports/ukraine-cache
```

`manual`/`no-twin` rows are for a person to look at by hand; nothing here
acts on them. Re-running the same reviewed file changes nothing — the
orphan is gone after the first pass.

### 9. Inventory of what part B's bridge left unlinked

A survey CSV of the remaining unlinked commemorative/collector records —
run `merge-b` first (step 8): every pair it merges is one fewer row here.
Nothing is applied except `link` rows:

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --steps inventory-b \
    --inventory-out /reports/inventory.csv \
    --report /reports/inventory.json --cache-dir /reports/ukraine-cache
```

`suggestedAction` per row: `link` (a fuzzy NBU candidate cleared the
threshold — `nbuId` is already filled in with the best one), `archive` (the
title says this is a yearly set — `collection_group` has no enum value for
one, so this is a suggestion with a reason, not an automatic change),
`manual` (everything else, an admin operation outside this pipeline). Only
`link` rows marked `yes` are applied, through the same mechanism
jubilee-bridge uses (the CSV columns are deliberately the same shape):

```bash
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps inventory-b \
    --apply-inventory-review /reports/inventory.csv \
    --report /reports/inventory-2.json --cache-dir /reports/ukraine-cache
```

`archive`/`manual` rows are for a person to act on by hand; nothing here
does it for them.

### Full battle-run order

One list, in the order to actually run these in against the owner's
database — steps already covered above by number, plus the reviews between
them:

1. `circ-reclassify` (step 2)
2. `circ-bridge`, then its review (step 3)
3. `circ-variants`, then its review (step 3b)
4. `circ-gaps, circ-titles, circ-mintage` (step 4)
5. `circ-mintage --circ-refresh-mintage` (step 4, "Refresh mintage") — required after circ-variants assigns any `subtype`, to actually clear `circ-mintage.ambiguous`
6. `circ-photos` (step 5)
7. `circ-photos --circ-refresh-types hryvnia_1_2004` (step 6) — once a real `ua_coins_id` is set (step 6 above)
8. `jubilee-bridge`, then its review (step 7)
9. Part B's `titles, photos, repair-gaps` re-run on whatever jubilee-bridge just linked (step 7's own note)
10. `merge-b`, then its review (step 8) — before inventory-b (step 9), so its merges shrink that survey
11. `inventory-b`, then its review for `link` rows (step 9)

### Rehearsal against a live source, 2026-09-04

Run against an empty local database (no legacy data seeded), live network:
the Wikipedia table parsed to 350 cells, `circ-gaps` created 168 records and
skipped one with reason (1 kopiika 2019, a coin the table's own legend marks
"issued unofficially" and the type map has no range for), `circ-titles` and
`circ-mintage` found nothing left to do on records `circ-gaps` had just
written correctly, `circ-photos` stored 336 files (168 records × 2 sides)
across all eleven types (before the 1 hryvnia split) with zero failures.

### Real run against the owner's database, 2026-09-04

191 records ended up with a name, mintage and photo. Manual steps along the
way:

- `circ-bridge-review.csv`: 18 rows resolved `yes` (uCoin mint-quality
  variants sharing a face value and year); 21 rows left unresolved on
  purpose — that is the standing `catalog_variants` gap, not something the
  bridge's own CSV review is meant to settle;
- six jubilee 1 hryvnia records (id 1330-1335) were moved to
  `commemorative` by hand, direct SQL, bypassing `circ-reclassify`: they
  carry no NBU catalogue link at all, so `is_nbu_linked` cannot and will
  not see them — the legacy `groupFor` heuristic routed them into
  `circulation` on face value alone, with nothing automation can key off.

The 1 hryvnia 1992/2004 split landed after this run, so its 2004-2017
records still hold the pre-split photo until a `--circ-refresh-types
hryvnia_1_2004` pass (step 6 above; `hryvnia_1_2004` because that is the key
those years group under on the current map, not `hryvnia_1_1992`, which they
happened to be stored under before the split existed).

## LLM translation of the remainder (stage 4.5, part C)

`--steps translate-c`. Everything the steps above could name from an
issuer's own card is already `official`; what merge-b and inventory-b leave
— legacy Excel records with a Russian uCoin heading and no National Bank
card at all, the six jubilee 1-hryvnia records, and stray `title_en` gaps on
records already linked — gets a name from a model instead, marked `llm`.
Full details, the selection rule, and what `title_original` correction does
to a Russian original: `../docs/05-integrations.md`, section 11.

The only step in this pipeline that calls out to anything other than the
National Bank / ua-coins.info / Wikipedia, and the only one that spends
money per run — `ANTHROPIC_API_KEY` must be set in `.env` for `--apply` or
`--translate-out`; a plain `--dry-run` never reaches the API at all, it only
reports the selection and the batch plan.

```bash
# dry run with a real CSV to review — the one case a dry run still calls
# the model; the Russian original a record is replacing survives only here
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py \
    --steps translate-c --translate-out /reports/translate-c.csv \
    --report /reports/translate-c.json --cache-dir /reports/ukraine-cache

# after reviewing the CSV
docker compose run --rm -v "$PWD/migration-reports:/reports" \
  api python scripts/ukraine_pipeline.py --apply --steps translate-c \
    --report /reports/translate-c-2.json --cache-dir /reports/ukraine-cache
```

There is no `--apply-review` for this step: unlike `bridge`/`merge`, the CSV
carries no `decision` column to read back — `--apply` recomputes the same
batches itself, and `*_source = 'llm'` already marks every written row as
worth a second look later.

Admin title editing (`titleUk`/`titleEn`/`titleOriginal` on a shared record)
is the existing `PATCH /catalog/{id}` — see `../docs/03-api-contract.md`,
"Правка названий": it now always stamps `*_source = 'manual'` and rejects an
empty string. No new endpoint, no new screen — the admin-mode edit form on
the record page is a backlog item (`../docs/BACKLOG.md`), the API contract
is already there.

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
app/reference_data/ countries, denomination units, materials — data and parsers
app/legacy_migration/ the one-off import of the desktop database
app/ukraine_recon/ read-only parsers for the three Ukrainian sources (part A)
app/ukraine_pipeline/ the steps that write from them (part B)
app/db/            engine and session
alembic/           migrations
scripts/           operational scripts
```
