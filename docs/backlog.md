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
      of a public service. Decide and build.
- [ ] **PWA service worker.** Manifest and icons ship; there's no offline cache. Close
      without it unless offline use is wanted.

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
- [ ] **Central Caddy is outside the repo** (`/srv/caddy`). Document its compose file,
      mounts and site config in `infra.md`.
- [ ] **Logo sources in the bundle.** `frontend/public/brand/logo-*.src.png` (~3 MB) ship
      with every build. Move them out of `public/`.
- [ ] **One git identity.** Align `git config user.email` on every machine — history
      has two authors.
- [ ] **Closing dev to outsiders** (e.g. Cloudflare Access) — open question, not
      designed.

## Frontend

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

- [ ] **Model/migration drift.** `ix_auth_identities_user_id` (0024) and
      `ix_support_messages_ticket_id` (0023) exist in the database but not in the models;
      autogenerate would propose dropping them. Declare them in the models.
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
