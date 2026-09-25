# Authentication and data ownership

Accounts, sessions, roles, and who may read or write what. Endpoint contracts:
`api.md`. Mail transport and env vars: `infra.md`.

---

## Accounts

Registration is **open** to anyone. The account lifecycle:

- register with an email → verification email;
- **email verification is mandatory**; the password is chosen when the link is used;
- sign in, sign out, refresh the session;
- change password; set a password (accounts created via Google have none);
- forgot / reset password by email link;
- sign in with Google and link Google to an existing account (below).

Mail goes through `MAIL_BACKEND`: `console` writes messages to the log (local work and
tests, no secrets needed), `smtp` sends them (`infra.md`). Emails are English only for
now (`backlog.md`).

`ALLOW_REGISTRATION` (default `true`) is an **emergency switch**, not a mode: if a wave of
bot sign-ups hits, registration closes with one env var and no deploy. Google sign-up
respects it too.

## Passwords

- Hashing: **argon2id** (`argon2-cffi`), `app/core/security.py`.
- At least 10 characters (`password_min_length`), at most 256. One validation for every
  path that sets a password — verification, reset, change, set — with no relaxed variant
  anywhere. Sign-in accepts up to 1024, which only bounds the work handed to argon2.
- Hashing and checking run off the event loop (~50 ms of CPU each), so a burst of
  sign-ins doesn't stall other requests.
- Sign-in without an account, or for an account without a password, still runs one
  check against a stand-in hash, so the answer time doesn't reveal which addresses
  exist.
- A hash made with older argon2 parameters is upgraded on the next successful sign-in.
- `password_hash` never leaves the database: not logged, not serialized, not returned.
- `password_hash` is `NULL` for an account without a password (Google-only). Password
  sign-in is impossible until the user sets one in settings.

**No real personal data in the repository.** Real emails and passwords never go into
git — docs, code, tests or example commands. Use placeholders (`<owner-email>`,
`<admin-email>`); real values live in the server `.env` and GitHub secrets.

## Sessions

| Token | Lifetime | Where it lives |
|---|---|---|
| access (JWT, HS256) | 15 min | frontend memory only; sent as `Authorization: Bearer` |
| refresh (opaque) | 30 days | httpOnly, Secure, SameSite=Lax cookie |

- The refresh token travels **only** in the cookie: `/auth/refresh` and `/auth/logout`
  have no body. It's never readable from JavaScript and never lands in logs.
- Refresh tokens are stored as **sha256** in `refresh_tokens` (with `user_agent`, `ip`,
  `expires_at`, `revoked_at`, `revoke_reason`) and can be revoked.
- **Families.** Every sign-in (password, email verification, Google) starts a family
  (`family_id`); rotation keeps it. A family is one device's session.
- **Rotation:** every refresh revokes the presented token (`rotated`) and issues its
  successor, derived from it with an HMAC keyed off `JWT_SECRET` — the same token
  always has the same successor. The token row is locked (`SELECT … FOR UPDATE`), so
  concurrent refreshes with one cookie run one after another and never fork a family.
- **Grace window** (`refresh_reuse_grace_seconds`, 30 s): a token rotated less than
  30 s ago that comes back gets its still-live successor again — a lost response on a
  phone, a reload mid-refresh, a second tab.
- **Reuse detection:** a `rotated` token presented after the window, or after its
  successor has itself rotated, means it leaked → **that family** is revoked (`reuse`),
  the event is written to `audit_log` (`session.refresh_reuse`), and the user's other
  devices stay signed in (RFC 9700, section 4.14.2). A token ended any other way
  (logout, password change) is just a `401`.
- **Sign-out** revokes the whole family of the presented token, and only it.
- **Access tokens belong to their sign-in.** The JWT carries `sid` (the family id), and
  every authorised request checks that the family still holds a live refresh token. So
  sign-out, a password change or a detected replay ends that sign-in's access tokens at
  once, not after their 15 minutes. A token without `sid` is refused; the client just
  refreshes. `exp`, `iat`, `sub` and `sid` are required claims.
- Password reset and password change revoke every family of the user.
- `session_started_at` (sign-in time, carried through rotation) and `persistent`
  ("remember me") are stored per token for session-lifetime rules; nothing reads them
  yet.
- The signing secret comes from the environment and must be at least 32 characters; the
  API refuses to start otherwise (a short HS256 secret can be brute-forced offline from
  any user's own token).

## One-time tokens: email verification and password reset

Table `auth_tokens` (`data-model.md`), stored as sha256 like refresh tokens; the raw
token exists only in the email.

| `kind` | Lifetime | Effect |
|---|---|---|
| `email_verify` | 24 h | sets the password, marks the email verified, activates the account, signs in |
| `password_reset` | 1 h | allows setting a new password |

- Single use: `used_at` is set; checking and marking happen under a row lock, so two
  concurrent requests can't both use it.
- Issuing a new token of a kind invalidates the user's earlier unused ones of that kind.
- At least 32 random bytes (`secrets.token_urlsafe`).
- The transaction holding the new token commits **before** the email is sent. If mail
  fails, the inactive account stays and the user can request a resend.
- Verification and reset emails go out **after the response** (`BackgroundTasks`), and a
  mail failure is logged, not raised. Otherwise the SMTP round trip — made only when the
  address has an account — or a `500` from a mail outage would give that away.
- `/auth/register`, `/auth/forgot-password` and `/auth/resend-verification` answer the
  same whether or not the address exists — in body, status and time — so the forms
  can't be used to probe for accounts.
- **No password before verification.** Registering again with an unverified address just
  sends a new link; only the mailbox owner chooses the password, when using it.
  Confirming an address **always** requires choosing a password — no Google identity
  stands in for it — and drops any Google identity the unconfirmed account carried: it
  was never proven to belong to this mailbox's owner.
- Registering again with an already verified address (including a Google-created one)
  also answers `202` but creates nothing and sends nothing. The register screen explains
  the options generically: sign in with Google and add a password in settings, or reset
  the password.

### Unverified and disabled accounts

An unverified account has `is_active = false` and `email_verified = false`. It can't
sign in, and any request with a token of such a user gets `403`
(`email-not-verified` / `account-disabled`, `app/api/deps.py`).

Unverified accounts are **not** cleaned up automatically — there's no purge job
(`backlog.md`).

## Guests

Without a token, the shared catalog, coin cards, series and reference data are readable
(`OptionalCurrentUser`). Guests get an allow-listed response
(`PublicCatalogListItem` / `PublicCatalogCard`) that **can't** carry prices or anything
private; filters and sorts that need an account (`owned`, `scope=own`, `archived`,
sorting by price/purchase) return `422`. Everything else requires sign-in.

## Rate limits

Fixed windows in Redis (`app/core/rate_limit.py`). Several scopes per endpoint are
normal; exceeding a limit returns `429` with `Retry-After`. A counter and its expiry are
set in one transaction, so no counter can outlive its window.

| Endpoint | Limit | Scope |
|---|---|---|
| `POST /auth/login` | 5 / 15 min per email, 20 / 15 min per IP | a success resets the email counter only — signing into one's own account must not buy more guesses at others from the same IP |
| `POST /auth/register` | 3 / h | IP and email |
| `POST /auth/refresh` | 600 / h | IP — a load backstop: tokens can't be guessed, and every page load of a remembered session refreshes |
| `POST /auth/forgot-password` | 3 / h | IP and email |
| `POST /auth/resend-verification` | 3 / h | IP and email |
| `POST /auth/reset-password` | 5 / h | IP |
| Google `start` / `link/start` | 10 / h | IP |
| Guest catalog listing / search / reference | 300 / 90 / 300 per min | IP (signed-in users are not limited) |

Accepted risk: five wrong passwords every 15 minutes keep one address out of password
sign-in (Google sign-in and password reset still work). Closing it needs a CAPTCHA or
similar, not a tighter limit.

### Registration honeypot

The register form has a hidden `website` field that people never see and autofill
doesn't fill. If it's filled, the request gets the same `202` as success and nothing is
created. It complements rate limiting, it doesn't replace it.

## Google sign-in and account linking

Google OpenID Connect, server-side authorization-code flow with PKCE, random `state` and
`nonce` (`app/services/google_auth.py`, `app/api/v1/google_auth.py`).

- `state` is one-use in Redis (10 min) **and** bound to the browser by an httpOnly
  SameSite=Lax cookie.
- The server verifies the ID token's signature, `aud`, `iss`, expiry, `nonce` and
  `email_verified`. The Google identity is `sub`, not the email.
- The client secret lives only on the server. Without `GOOGLE_CLIENT_ID` and
  `GOOGLE_CLIENT_SECRET`, Google sign-in is hidden and disabled.
- After success the app issues its own refresh cookie as usual.

`auth_identities` maps `(provider, subject) → user_id`, unique per pair, one Google
identity per user.

**Resolution rules:**

- A known `sub` signs into its linked account, even if the Google email changed.
- A new `sub` with a free email creates a user only for `@gmail.com` and Google Workspace
  (`hd` claim) addresses: Google controls those mailboxes, so its verification is
  accepted and the user is signed in immediately.
- **Any other address creates nothing** (`/login?google=email-unconfirmed`). Google
  checked it once, when the Google account was made, and doesn't vouch that the same
  person still owns the mailbox — a former employee or the previous owner of a
  re-registered domain may still hold that Google account. Creating a pending account
  with that Google already attached would hand them the real owner's account once the
  owner confirmed the address. Such a user registers by email and links Google from
  settings, where linking requires a live session.
- A new `sub` whose email is already taken **creates nothing and links nothing**
  (`/login?google=link-required`). The user signs in the usual way and starts linking
  from settings. Linking requires a live session, the Google flow in the same browser,
  and matching emails; the collection stays with the existing `user_id`.
- Merging two existing users is not supported.

**In the browser**, Google sign-in opens in a separate window so the original tab's
history stays clean. After the callback, the window notifies the original tab via
`BroadcastChannel` (a random id in `sessionStorage` ties the answer to this attempt); the
tab refreshes its session from the cookie and closes the window. If a window can't be
opened, the flow falls back to a same-tab redirect. With local Vite against the remote
API the callback lands on the server's domain, so the full window flow is testable only
on one origin.

## Frontend session behavior

- Sign-in, registration, password-reset request and "check your email" share one dialog
  over the public site; old URLs (including Google error ones) open that dialog. Email
  verification and reset-by-token stay separate screens (`ui.md`).
- "Remember me" sets a flag in `localStorage` that allows restoring the session across
  visits; without it the flag lives in `sessionStorage`, so a reload of the tab keeps the
  session. Tokens themselves stay in memory and the httpOnly cookie. Sign-out clears
  both flags. Anonymous requests never trigger a refresh.
- A definitive auth failure clears user state and the query cache; a transient
  network/server error during refresh does not sign the user out. Late refresh responses
  and private responses from an ended session never restore it.
- **Refresh coordination.** Concurrent 401s in a tab share one refresh. Across tabs,
  refreshes run one at a time under the Web Locks API (`ck-refresh`), so each tab sends
  the cookie the previous one set; browsers without it rely on the server's grace window.
  A refresh that fails with a network error or a 5xx is retried once after 1 s — inside
  the grace window if the server had already rotated the cookie.
- The Google sign-in popup never refreshes on its own start-up; only the opener does.
- A voluntary sign-out is broadcast on `BroadcastChannel('ck-auth')`; the viewer's other
  tabs close their session too.
- After a session expires, the user can sign in again and continue an unsaved purchase or
  expense form: drafts are kept in the tab's memory for the same account and cleared on
  voluntary sign-out or when a different account signs in. A reload discards them.

## Data ownership

The core decision is in `data-model.md`; here, what it means for access.

**Shared — readable by everyone:** `countries`, `currencies`, `denominations`,
`coin_series`, `materials`, `edge_types`, `quality_types`, `exchange_rates`,
`catalog_items` with `created_by IS NULL`, `catalog_variants`, `market_price_snapshots`
with `created_by IS NULL` (signed-in users only — guests get no prices), `media_files`
from public sources (`media.md`).

**Private — the owner only:** `collection_items`, `expenses`, `sales`,
`purchase_offers`, `collection_goals`, `ucoin_catalog_sources`, `user_settings`,
personal `storage_locations`, own `media_files`, and `catalog_items` /
`market_price_snapshots` with `created_by = <owner>`.

`catalog_items`, `market_price_snapshots` and `media_files` appear in both lists: a
row's layer is decided by its own fields, not its table. That's why the visibility filter
is mandatory in repositories.

### Write rules

| Action | Who |
|---|---|
| Create, edit, archive / unarchive a **shared** catalog record | admin only |
| Physically delete a shared record | admin, only if archived and unreferenced (`business-rules.md`, BR-10) |
| Create a **personal** position | any signed-in user (`created_by` = self) |
| Edit or delete a personal position | its author |
| Add a price snapshot to a shared record | the central job only (`created_by = NULL`) |
| Everything in private tables | the owner only |

A user trying to change a shared record gets **`403`** — they can see it, they just may
not edit it. Someone else's personal position (or collection item, or photo) is
**`404`** — for them it doesn't exist; existence of private records is never revealed.

### Archived records

An archived shared record leaves the storefront, not the database. With `archived=true`,
an admin sees all archived records; a regular user sees only those they own a
collection item of (`CatalogRepository._archive_condition`).

### How it's enforced

Filters live **in repositories**, never in routes — one forgotten
`WHERE owner_id = …` in a route would leak someone's collection:

```sql
-- private entities
WHERE owner_id = :user_id
-- catalog and price snapshots
WHERE created_by IS NULL OR created_by = :user_id
```

Repositories for private data take the user id in their constructor and apply the filter
to every query; bypassing it has to be deliberate. Row-level security in Postgres isn't
used; the schema doesn't preclude it.

## Roles

```
user   reads the shared catalog, manages own personal positions and collection
admin  plus: shared-catalog maintenance (archive, drafts review), users and roles,
       job runs, Telegram admin bot (admin.md)
```

**Granting admin:**

- **In the UI** (normal path): `/admin` → Users → role toggle,
  `PATCH /admin/users/{id}/role` (`admin.md`). Only verified, active users can be
  promoted; an admin can't demote themselves; the last admin can't be demoted. Every
  change is written to `audit_log`.
- **Bootstrap / recovery** — when there's no admin to click the button:
  ```bash
  docker compose run --no-deps api python scripts/promote_admin.py --email <admin-email>
  docker compose run --no-deps api python scripts/promote_admin.py --email <admin-email> --demote
  ```
  The user must already exist and be verified (exit codes: 1 not found, 2 not verified).
  The email is always an argument — never hardcoded. New admins register through the
  normal form first, which doubles as a check of the new-user path.

## Security baseline

- HTTPS everywhere with HSTS; certificates by Caddy (`infra.md`).
- CORS only for the frontend origin (`CORS_ORIGINS`), never `*`.
- No secrets in the repository; `.env.example` holds empty placeholders.
- A failed sign-in never reveals whether the email exists.
- All input is validated by Pydantic models, including string lengths.

## Not planned

| Feature | Status |
|---|---|
| Two-factor authentication | not planned |
| Checking passwords against breach lists | post-MVP |
