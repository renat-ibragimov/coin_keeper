# Backlog

Open work only. Each item: the problem, then what to do. When an item is done — or found
already done — delete it in the same commit; git keeps the history.

Deferred product features (not scheduled): `product.md`, "Out of scope".

---

## Production hardening

Mostly server state rather than repository code.

- [ ] **Backups.** Only manual `pg_dump` before risky migrations; no script, cron or CI
      step. Add scheduled Postgres + MinIO backups to off-server storage. Dump with
      `pg_dump -f` inside the container + `docker cp`, never through
      `docker compose exec` stdout; validate every dump (`PGDMP` signature +
      `pg_restore --list`).
- [ ] **Restore check.** No restore script or test. A backup counts once it has been
      restored and record counts compared.
- [ ] **Watchdog cron.** The entry is in `coin-parser/deploy/crontab`; confirm it's
      installed on the server (`crontab -l`), then close this item (`admin.md`, "Watchdog").
- [ ] **External uptime monitoring.** If the whole server is down, jobs and the watchdog go
      silent together; nothing outside the server notices.
- [ ] **Real email.** Set up the SMTP provider (Resend), SPF/DKIM/DMARC in Cloudflare,
      `MAIL_BACKEND=smtp` on the server (`infra.md`). Required before strangers sign up.
- [ ] **Ukrainian emails.** Verification and reset emails are English only
      (`backend/app/core/mail/messages.py`) while the interface defaults to Ukrainian.
      Send them in the user's locale.
- [ ] **Security checklist.** Done: Postgres/Redis/MinIO ports closed in prod compose,
      CORS limited to the frontend origin. Open: unattended security upgrades; verify
      firewall and key-only SSH; fail2ban on sshd; audit logs for secrets.
- [ ] **dev/prod split.** Prod `numismatics.bakost.club`, dev stays on
      `coins.renat-ibragimov.com`; duplicate the DB and media to both. First promotion:
      the Ukrainian catalog and the owner's collection. Later promotions move a whole
      country (records + photos + series) dev → prod, matched by `source_key`, not `id`;
      users and collections live only in prod (`infra.md`).
- [ ] **Repository move** to `bakost-numismatics`: rename the `coinkeeper` identifier
      (packages, containers, image, compose, CI secrets); decide public vs private.
- [ ] **Unverified-account cleanup.** Accounts that never verify their email are never
      removed; add a periodic purge (e.g. older than 30 days, `auth.md`).
- [ ] **Account deletion.** Neither the UI nor the API can delete an account — expected
      of a public service. Decide and build. Before it ships,
      `market_price_snapshots.created_by` must become `ON DELETE CASCADE`: today it is
      `SET NULL`, which would turn a deleted user's private prices into shared ones
      counted in everyone's value.
- [ ] **PWA service worker.** Manifest and icons ship; there's no offline cache. Close
      without it unless offline use is wanted.

## Security and sessions

Session rules are in `auth.md`.

- [ ] **"Remember me" off doesn't shorten the server session.** The refresh cookie is
      always persistent for 30 days; the flag only decides whether the SPA refreshes on
      start-up, so on a shared computer the next person can still call
      `POST /auth/refresh`. Send `remember` to `/login`, store it in
      `refresh_tokens.persistent` (the column exists), and without it use a session
      cookie (no Max-Age) with a short server TTL (12–24 h).
- [ ] **No absolute session lifetime, no session list.** Every rotation extends the
      session by 30 days, so a session used monthly never ends; there is no "my sessions"
      list and no "sign out everywhere". Cap the family by `session_started_at` (the
      column exists, e.g. 90 days); decide whether the UI gets a session list.
- [ ] **Refresh tokens are never cleaned up.** Every page load adds a row (hundreds per
      active user a month). Periodically delete rows expired or revoked long ago. Index
      `refresh_tokens.parent_id` first: its `ON DELETE SET NULL` otherwise scans the table
      for every deleted row.
- [ ] **A refresh answer lost for longer than the grace window** still ends that device's
      session (only that one): a phone that sent the refresh, lost the answer and stayed
      offline past 30 s comes back with a rotated token. Decide whether a rotated token
      whose successor was never used may be accepted later, or accept the behaviour.
- [ ] **Migration `0027` test covers only the data backfill** — not the CHECK, the
      indexes or the downgrade.
- [ ] **Setting a password needs no re-authentication.** `/auth/set-password` adds a
      password to a Google-only account with just a bearer token, so a hijacked session
      becomes permanent password access. Require a fresh Google sign-in (`auth_time`
      within minutes) or an email confirmation. Rate-limit `/auth/change-password` per
      user.
- [ ] **No security notification emails.** Nothing tells a user their password was
      changed, set or reset, or that Google was linked (the events are already in
      `audit_log`). Send one email per event, in the user's locale.
- [ ] **No Content-Security-Policy.** Caddy sends HSTS, `nosniff` and `no-referrer`, but
      no CSP, `frame-ancestors`/`X-Frame-Options` or `Permissions-Policy`. CSP is the real
      XSS defence here: any same-origin script can call `/auth/refresh` and read an access
      token. Roll out as `Content-Security-Policy-Report-Only` first, walk every screen
      (fonts, MinIO images, Google sign-in), then enforce; add `frame-ancestors 'none'`.
- [ ] **Password sign-in can be locked for an address.** Five wrong passwords every
      15 minutes keep one address out of password sign-in (Google and reset still work).
      Accepted for now; the real fix is a CAPTCHA after repeated failures.
- [ ] **CPU-heavy uploads are not rate-limited.** `PUT /collection/{id}/photos/{side}`
      and `PUT /auth/me/avatar` decode, remove the background and encode three WebP
      sizes; an account can loop 12 MB uploads and saturate the CPU. Add a per-user limit
      (e.g. 30 per 10 min) through `rate_limit.hit()`.

## Backend

- [ ] **Blocking storage calls on the event loop.** `core/storage.py` `put_object` /
      `delete_objects` are synchronous boto3 calls made from async code (collection
      photos, catalog photos, avatars); one upload writes three variants and stalls the
      worker. Wrap them in `anyio.to_thread.run_sync`, as `process_image` already is.
- [ ] **Expense foreign keys have no index.** Only `(owner_id, expense_date)` is indexed;
      the supporting-expense subqueries on catalog and collection lists, and every
      `ON DELETE SET NULL` from `collection_items` / `catalog_items`, scan `expenses` by
      `catalog_item_id` / `collection_item_id`. Same for `collection_items.catalog_item_id`
      alone. One migration with the three indexes.
- [ ] **Deleting a purchase leaves its photos in storage.** The `media_files` rows
      cascade, the MinIO objects of the user's private photos stay forever, while
      `media.md` says deletion removes them. Collect the keys before the delete and
      remove them after the commit.
- [ ] **Photo replacement deletes objects before the commit.** `_retire` removes the old
      MinIO objects while the transaction could still fail. Delete after the commit.
- [ ] **Money inputs have no scale bound.** A price of `0.005` is stored as `0.01` while
      the expense `0.005 × quantity` rounds separately, so purchase and expense disagree;
      `1e13` overflows `Numeric(14,2)` into a `500`. Add
      `Field(ge=0, max_digits=14, decimal_places=2)` to price and amount fields (and bound
      weight / diameter).
- [ ] **Explicit `null` in PATCH bodies gives `500`.** `"price": null` on a purchase,
      `"amount": null` on an expense, `"titleOriginal": null` on a catalog item reach an
      assert or a NOT NULL at flush. Reject `None` for non-nullable fields in validators.
- [ ] **Races without unique constraints.** Two first uploads of the same photo side
      insert two `media_files` rows, and every later PUT/DELETE then fails with
      `MultipleResultsFound`; two first uses of a new storage-location name create
      duplicates. Partial unique indexes (or a row lock on the parent).
- [ ] **A price with no exchange rate counts as 0 UAH.** `price × coalesce(rate, 0)` in
      `repositories/catalog.py` turns a non-UAH snapshot without a rate into a priced
      0 UAH coin, against BR-6 ("null, never filled"). Drop the `coalesce`.
- [ ] **Guest catalog ignores `metalKind`.** `repositories/public_catalog.py` drops
      `filters.metal_kinds`, so a guest gets unfiltered results with no error.
- [ ] **Small N+1 queries.** Two rate queries per purchase on the coin card
      (`services/catalog.py`), one `get_card` per proposal in `api/v1/admin.py`, three
      queries per series in `services/series.py`.
- [ ] **Completeness `collected_series` branch is a per-row subplan.** The correlated
      `EXISTS` inside `storefront_visible` runs once per shared row of an inactive
      country; cheap while the catalog is mostly Ukraine, costly once other countries
      are imported. Rewrite it as an uncorrelated
      `series_id IN (SELECT … FROM the user's collection)`.
- [ ] **Background translations hold a DB connection during the model call.** The
      storage-location and coin-title tasks open a session, then call Anthropic with the
      client's default 600 s timeout and retries, so an outage drains the pool; they can
      also overwrite an edit made meanwhile. Read, release the connection, call with a
      short timeout, then re-read and apply only if the source text is unchanged.
- [ ] **Search can't use its indexes.** The GIN full-text match is OR-ed with an
      unindexed `ILIKE '%…%'`, so the query is a sequential scan; `pg_trgm` is installed
      but has no trigram index. Fine at today's catalog size.
- [ ] **Expense chart range is unbounded.** `dateFrom=0001-01-01&dateTo=9999-12-31`
      builds ~120k month buckets. Cap the span.
- [ ] **Presigned URLs change on every request.** SigV4 dates make every catalog image URL
      unique, so browsers re-download images on each refetch, and a card left open for an
      hour shows expired links. Serve public sources (`nbu`, `manual`, `ua_coins`)
      through a public prefix, or round the signing time.

## Infrastructure

- [ ] **PR builds overwrite `latest` in GHCR.** The `build` job pushes `<sha>` and
      `latest` on pull requests too. Deploys pin the SHA, but compose's default image
      and a manual `docker compose pull` would take a PR image. Push `latest` from
      `main` only.
- [ ] **Cache headers.** Long immutable `Cache-Control` for `assets/*` and `/media/*`,
      `no-cache` for `index.html` in the central Caddy — users have been served a stale
      bundle.
- [ ] **Deploy resilience.** Retry `docker compose pull` in the deploy step (GHCR
      flaps); an emergency "build on server" workflow for when GHCR is down.
- [ ] **SSH.** CI uses port 22, people use 2222; if 22 closes, change `DEPLOY_PORT`. Add
      every working key to `authorized_keys` of `root` and `deploy`.
- [ ] **`git pull` on the server asks for credentials.** Check `git remote -v` and the
      credential helper.
- [ ] **Read-only DB user** for ad-hoc queries instead of the app's own role.
- [ ] **API logs don't survive a deploy.** Container logs go with the container, so an
      incident can't be investigated after the next push (the refresh-reuse logouts had
      to be reconstructed from the database). Keep logs on the host or ship them out.
- [ ] **The app uses MinIO's root credentials**, and Caddy exposes the whole S3 API under
      `/media/*`. Give the app a scoped MinIO user limited to its bucket; expose only
      object reads.
- [ ] **`/api/v1/internal/job-runs` is reachable from the internet** (token-guarded),
      though its caller sits on the same Docker network. Block it in Caddy.
- [ ] **The health check is costly and open:** public, no rate limit, and it builds a new
      boto3 client on every call. Reuse the client; limit or restrict the endpoint.
- [ ] **Central Caddy is outside the repo** (`/srv/caddy`). Document its compose file,
      mounts and site config in `infra.md`.
- [ ] **Logo sources in the bundle.** `frontend/public/brand/logo-*.src.png` (~3 MB) ship
      with every build. Move them out of `public/`.
- [ ] **One git identity.** Align `git config user.email` on every machine — history
      has two authors.
- [ ] **Closing dev to outsiders** (e.g. Cloudflare Access) — open question, not
      designed.

## Frontend

- [ ] **Personal positions can't be edited or deleted in the UI.** The API supports it
      (`PATCH`/`DELETE /catalog/{id}` for the author); no screen calls it.
- [ ] **UI copy outside i18n.** The landing page (`features/landing/copy.ts`) and legal
      pages (`app/legal/copy.ts`) keep text in TS objects, against the rule that every
      user-facing string lives in `shared/i18n/{uk,en}.json`. Move it, or make the
      exception explicit in `AGENTS.md`.
- [ ] **Admins see drafts in the storefront.** Non-admin reads require `status =
      'active'`, so admins get drafts mixed into `GET /catalog` and search, not only in
      `/admin/proposals`. Confirm it's intended or filter them out.
- [ ] **Stale screens after money changes.** A purchase, edit or delete doesn't
      invalidate the `completeness` queries (`COLLECTION_DEPENDENT_KEYS` in
      `features/collection/model.ts`), and expense edits don't invalidate `catalog` /
      `collection`, whose supporting-expense sums change. Add the keys.
- [ ] **`aria-label="Loading"` is inline** in `shared/ui/Spinner.tsx`; move it to i18n.
- [ ] **Hidden filters still live.** "Обсяг" (scope) and "Показати архівні" have no UI,
      but `useCatalogFilters` still reads them from the URL and sends them to the API.
      Either remove them fully or bring them back into the filter drawer.
- [ ] **Summary tiles on narrow phones.** On ≤ 400 px the dashboard and collection tiles
      sit in two cramped columns (long hints wrap to 3–4 lines). Options: one column,
      compact tile without the hint, horizontal strip.
- [ ] **Unprocessed photos in the light theme** can show white rectangles or a sepia
      tint on catalog tiles (`multiply`/`isolation` blend chain). Fix when reported.
- [ ] **Catalog polish.** Default sort "commemorative by year desc, circulation below";
      a "typical photo" badge when a coin shows its type's photo from another year.
- [ ] **Missing-coin thumbnails** in the overview's series list need a per-series
      request; the row leaves room for them (`DashboardPage.tsx`).
- [ ] **Cost to complete a group.** Show the summed current price of the missing coins
      plus an "unpriced" count on the completeness detail screen. The catalog summary
      already computes both (`CatalogSummaryOut.missingBudgetUah`, `unpricedMissing`);
      the completeness API doesn't.
- [ ] **Coin sharing previews.** Prerendered catalog pages carry OG tags, but
      `og:image` is always the logo. Use the coin's photo.
- [ ] **Design pass.** A general visual review of all screens.

## Data and sources

- [ ] **Admin edits of shared records get overwritten.** Nothing in this app writes
      `catalog_items.edited_fields`, and the `coin-parser` loader rewrites source-owned
      columns (titles and their `*_source` → `official`) on the next load of the series.
      An admin `PATCH /catalog/{id}` is lost then. Fix: record edited fields on admin
      PATCH, or make the loader respect `*_source = 'manual'` (`integrations.md`,
      "Loader rules").

- [ ] **Model/migration drift.** `uv run alembic check` reports ~175 differences: every
      id/FK is `BIGINT` in the database but `Integer` in the models (126 type changes, 46
      identity defaults), and three indexes exist only in migrations
      (`catalog_items_search_idx`, `ix_auth_identities_user_id`,
      `ix_support_messages_ticket_id`). Harmless at runtime, but autogenerate is unusable
      and `alembic check` can't guard new migrations. Declare `BigInteger` and the indexes
      in the models until `alembic check` is clean. Also: the two CHECKs on `sales` carry
      a double prefix in the database (`ck_sales_ck_sales_quantity_positive`,
      `ck_sales_ck_sales_sale_price_non_negative`); rename them in a migration.
- [ ] **Unused columns.** `user_settings.display_currency` is always `UAH`, nothing
      writes `catalog_items.edited_fields`. Drop them or put them to use.

Most catalog-building work now lives in `coin-parser`; items here are about data already
in this database.

- [ ] **Souvenir packaging, rest.** One card with a "has a packaged variant" badge,
      detail with both prices, completeness counted by the plain coin (BR-15). NBU set
      coins (Енеїда ×9, державні символи ×6, козацькі клейноди ×4) need a link to the
      set card, not `packaging_of_id`.
- [ ] **Opaque RGBA photos aren't cut.** `process_image` only removes backgrounds for
      `RGB` input; a PNG with alpha = 255 skips it. Use `classify` from
      `app/services/media_background.py` as the guard.
- [ ] **Background-removal leftovers.** ~171 dark coins touching the frame edge (lower
      the dark-branch border threshold), ~102 non-uniform and ~53 fragment/odd-shape
      images need manual work; keep a list of bad source images to replace.
- [ ] **~320 US photos without size variants** (`legacy-N.webp` keys, `data-model.md`,
      "Data origins"). Regenerate variants when the US catalog is taken up.
- [ ] **~505 orphan photos from the previous app** carry a `catalog_item_id` in the file
      name; match them to entries.
- [ ] **US and USSR names are still Russian** (`original_lang` claims `en` for the US).
      Translate them, plus countries and series without a CLDR name.
- [ ] **Possible duplicates.** Active entries sharing `title_original` + `issue_year`
      (e.g. "Український борщ" ×2): merge or confirm they're distinct issues.
- [ ] **1 hryvnia 2004–2017 has no photo:** NBU has no card for that design; find the
      coin's UA-Coins page id and use it.
- [ ] **Active countries.** Three countries (ids 1–3) are `is_active` in production, not
      only Ukraine. Make sure the country filter chips follow `is_active` rather than
      assuming Ukraine.
- [ ] **Better photos later.** For ~659 NBU cards we store the 600 px UA-Coins image; if
      NBU publishes full-size photos, re-fetching needs a "replace from a better source"
      option (`coin-parser`).
- [ ] **Circulating commemoratives have no series** on their roll cards ("Області
      України", "Ми сильні. Ми разом"…): series are assigned by hand until the
      circulation section is parsed on its own (`coin-parser`).

## Product ideas

Not decided; listed so they aren't lost. The deferred-feature list is in `product.md`.

- [ ] **Impersonation with audit log** for supporting users, instead of signing in with
      someone's password.
- [ ] **Personal albums:** free grouping of one's own items ("from dad", "in capsules"),
      no completeness math.
- [ ] **Country and series skeletons** from open official lists (Poland, Czechia, euro
      €2, US, Canada, UK…): series without coins, marked "contents not loaded" and
      excluded from completeness; users pick them for personal positions.
- [ ] **Default sort by country `sort_order`, then year** in catalog and collection
      (today it's the country name in the reader's locale).
