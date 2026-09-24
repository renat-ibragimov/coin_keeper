# Admin section

The `/admin` area and everything behind it: visibility of scheduled jobs, the admin
Telegram bot, the watchdog, review of new catalog drafts, and user management. Only users
with `role = 'admin'` see it (`require_admin`, `app/api/deps.py`). Sections are cited from
code by name, e.g. `docs/admin.md, "Watchdog"`.

## Screen

`/admin` has three tabs, selected by `?section=`:

| Tab | `section` | Frontend | Backend |
|---|---|---|---|
| Фонові задачі | `jobs` (default) | `AdminPage.tsx`, `JobRunDialog.tsx`, `TelegramCard.tsx` | `GET /admin/jobs*`, `/admin/telegram*` |
| Користувачі | `users` | `UsersSection.tsx` | `GET /admin/users`, `PATCH /admin/users/{id}/role` |
| Пропозиції монет | `proposals` | `ProposalsSection.tsx`, `ProposalEditor.tsx`, `ProposalActions.tsx` | `/admin/proposals*` |

Endpoint contracts: `api.md`.

---

## Job runs

Scheduled jobs run in `coin-parser`, not here (`integrations.md`). Each run reports to
this API, which records it and notifies Telegram — one place, at the moment it happens,
with nothing polling.

### Reporting API

- `POST /internal/job-runs` opens a run (`status = 'running'`) before the work;
  `PATCH /internal/job-runs/{id}` closes it with the outcome.
- Authenticated by the shared secret in `X-Job-Token` (`JOB_REPORT_TOKEN`), compared in
  constant time. Unset secret → `503` (endpoint disabled); wrong token → `401`. The
  caller is a container on the same Docker network, not a user.
- On the `coin-parser` side (`collector/core/job_report.py`) every reporting failure is
  logged and swallowed: an unreachable API never changes the outcome of a run.

### `job_runs`

One row per run: `job`, `status` (`running | ok | partial | failed`), start and finish
times (`finished_at IS NULL` exactly while `running`), `stats` (the job's own counters,
JSONB, stored verbatim), a one-line `summary`, `details` (only when not `ok`) and
`exit_code`. Admins read it with `GET /admin/jobs` (filter by job; the response lists
known job names) and `GET /admin/jobs/{id}`.

### Reading the counters

A good run is one line; details appear only when something went wrong, with a few
examples rather than the full log. For `update-prices`:

- `no_quote` and `no_link` are normal — UA-Coins doesn't quote every coin every day.
  They're stated, never flagged.
- `errors` counts yearly pages that failed to download, not problem coins.
- `inserted = 0` is not a failure.
- The real signal is the status / exit code (`0` ok, `1` partial, `2` nothing done).
- `matched = inserted + corrected + dup`: recent days stay open to correction because
  UA-Coins may still serve yesterday's column in the morning.

The UI highlights a run stuck in `running` for more than 6 hours (`STALE_AFTER_MS`,
`frontend/src/features/admin/api.ts`) — longer than any real run, shorter than the gap
between two runs.

---

## Admin Telegram bot

The backend is the only sender of admin notifications (job runs, new users, watchdog
alarms); `coin-parser` only reports runs to the API. Code: `app/core/telegram/`
(transport over the Bot API, a console backend when no token is configured — nothing
reaches a chat locally or in tests), `app/services/telegram.py`,
`app/api/v1/telegram.py`. Config: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`,
`TELEGRAM_WEBHOOK_SECRET` (`infra.md`). The public support bot is a separate bot
(`telegram-support.md`).

Notifications go out as a background task after the response, so a job never waits on
Telegram. Chat ids are read inside the request, before the session closes.

### Linking a chat

No chat ids in config. An admin presses "Підключити Telegram" on `/admin` →
`POST /admin/telegram/link` returns a one-time code and a link
`t.me/<bot>?start=<code>` → the admin presses Start → the webhook receives
`/start <code>`, checks it and stores the chat id for that admin in
`telegram_recipients`. The card polls until the link lands. `DELETE /admin/telegram`
unlinks and also voids unused codes.

- Codes reuse `auth_tokens` (hash, expiry, `used_at`) with kind `telegram_link`;
  lifetime 15 minutes (`telegram_link_ttl_minutes`).
- A code is locked in a transaction when used, so one link can't be consumed twice.
- The link is a secret: anyone holding it can attach their chat.

### Access rules

Anyone can find a bot by name and write to it; the bot talks only to its own admins.

- The webhook checks `X-Telegram-Bot-Api-Secret-Token` before parsing anything: wrong
  secret → `403`, secret not configured → `404`, as if the route didn't exist.
- The reply is always `200` otherwise — a non-200 makes Telegram retry for hours.
- Only private chats are served. Groups, channels, messages from bots and unknown
  commands are ignored silently (no refusal message that would confirm the bot is
  alive).
- Only `/start <code>` and `/last` (the latest run) are acted on.
- Linking, `/last` and broadcast recipients all require a **current** admin: account
  active, email verified, role still `admin`. Losing the role or the account stops
  delivery.
- In BotFather: groups and inline mode off, privacy mode on.

### Message language

Bot messages are Ukrainian and live in `app/core/telegram/messages.py`, not in the
frontend localization files: the bot is not part of the app's interface and has no
locale. This is the one place where user-facing text sits in code (the Ruff exception is
in `backend/pyproject.toml`).

---

## Watchdog

`backend/scripts/watchdog.py` catches a job that **didn't run at all**, which the job
itself can't report. For each known job it reads the latest run in `job_runs` (any
status, including a hung `running`) and compares its age with `EXPECTED_INTERVALS`:

| Job | Schedule | Alarm after |
|---|---|---|
| `update-prices` | daily 07:10 UTC | 26 h |
| `update-rates` | every 5 h at `:25` | 7 h |
| `nbu-catalog-sync` | daily 10:40 UTC | 26 h |

Anything overdue or never run → one Telegram message listing all of them
(`watchdog_message`); all fresh → silence. The intervals must follow
`coin-parser/deploy/crontab`.

It's a cron entry, not a queued task: the script ships in the `api` image and cron runs
`docker compose exec -T api python scripts/watchdog.py` every 6 hours (the line lives in
`coin-parser/deploy/crontab`). There is no ARQ worker in the project, and the watchdog
wouldn't move to one if there were.

**Limitation:** if the whole server is down, both the jobs and the watchdog are silent.
External uptime monitoring is not set up.

---

## Draft review

New shared records from the NBU sync arrive as drafts; an admin decides.

- A draft is an ordinary `catalog_items` row with `status = 'draft'` — not a separate
  queue table. Editing it is the normal card editing path, its photos are already in
  MinIO, and publishing flips one field.
- Drafts are invisible to non-admins: storefront, search, completeness; a direct card
  returns `404`. The filter lives with `storefront_visible()` (`business-rules.md`,
  BR-2).
- `GET /admin/proposals`, `GET /admin/proposals/{id}` — the queue and one draft.
- `PUT` / `DELETE /admin/proposals/{id}/photos/{role}` — replace or remove the parser's
  obverse/reverse (JPEG/PNG/WebP up to 12 MB; stored with `source = 'manual'`).
- `POST /admin/proposals/{id}/approve` — `draft → active`.
- `POST /admin/proposals/{id}/reject` with a reason — `status = 'rejected'` plus archiving
  with that reason. Rejected drafts are never deleted.
- Both actions are written to `audit_log`; acting on a non-draft returns `409`.

The Telegram message for an `nbu-catalog-sync` run with new drafts links to
`/admin?section=proposals`.

---

## Users

- `GET /admin/users` — email, display name, role, active, email verified, registration
  date, number of coins, plus a summary.
- `PATCH /admin/users/{id}/role` — grant or revoke `admin`. Guards
  (`services/admin_users.py`): an admin can't demote themselves, and the last admin
  can't be demoted. Role changes go to `audit_log`.
- The first admin is bootstrapped over SSH with `backend/scripts/promote_admin.py`
  (`auth.md`).
- **New-user notice:** "🆕 Новий користувач: <email>" is sent when an account becomes
  real, not on `POST /auth/register` — so unfinished or bot-filled sign-ups don't wake
  the chat. Triggers: `AuthService.verify_email`, and new-user creation in the Google
  callback when Google vouches for the email (`auth.md`).

---

## Not in scope

- Editing already published shared records from `/admin` (with `edited_fields`, audit
  and all locales) — deferred (`backlog.md`). Admins can call `PATCH /catalog/{id}`
  directly; see `integrations.md`, "Loader rules", for why such edits can be lost.
- Running a job on demand from the admin UI or the bot.
- Impersonation, merging duplicates, promoting a personal position to shared
  (`backlog.md`).
- Toggling country visibility (`is_active`, `catalog_confirmed`) — done by SQL.
- Physical deletion of shared records — API only, no UI (`business-rules.md`, BR-10).
