# Infrastructure and deployment

How the system runs on the server and how code gets there. Local setup and the CI check
list: `development.md`. Open infrastructure work (backups, dev/prod split, hardening):
`backlog.md`, "Production hardening".

## Environments

There is one running environment today: `coins.renat-ibragimov.com` on a Hetzner server.
It serves the owner's real collection and is deployed on every push to `main`.

**Planned (not built):** split into dev (`coins.renat-ibragimov.com`) and prod
(`numismatics.bakost.club`), with the database and media duplicated at the split. The
principles already agreed:

- a country's catalog is built on dev and promoted to prod as a whole (records, photos,
  series), matching records across databases by `source_key`, never by `id`;
- users and their collections live only in prod and never sync back to dev;
- restricting dev to certain users (e.g. via Cloudflare) is an open question.

Undecided: one server with two stacks or a separate prod server; one Postgres with two
databases or two instances; how a promotion physically runs. Document here once decided.

## Topology

```
central Caddy (outside this repo) ── HTTPS, static frontend, /api → api, /media → minio
docker compose "coinkeeper":
  api         FastAPI (uvicorn, 2 workers); runs Alembic migrations on start
  postgres    PostgreSQL 16 (shared_buffers 512MB, work_mem 16MB)
  redis       Redis 7 — rate limits and short-lived keys
  minio       S3-compatible image storage
  minio-init  one-shot: creates the bucket, then exits
coin-parser (separate repository, cron on the same server)
  rates, UA-Coins prices, NBU catalog sync — writes to the same Postgres,
  reports runs to /api/v1/internal/job-runs (admin.md)
```

There is no queue or worker service: request-time background work uses FastAPI
`BackgroundTasks` (BR-4, BR-16), scheduled work runs in `coin-parser` on cron.

`docker-compose.yml` is the production topology: Postgres, Redis and MinIO publish **no
host ports**. It builds the image with `target: production` explicitly — without it
Docker builds the Dockerfile's last stage, the development one (dev dependencies,
running as root). The production image runs as an unprivileged `app` user.

`docker-compose.dev.yml` is for local development only (published ports, hot reload) and
is deliberately not named `docker-compose.override.yml`: the server checks out the same
repository, and an auto-loaded override would publish the database there
(`development.md`).

`minio-init` isn't pulled in by `up -d api`; on a fresh server run
`docker compose up minio-init` once.

## Configuration

Environment variables only. The server's `.env` is written by CI from the `SERVER_ENV`
secret (see "Deployment"); the repository has `.env.example` with placeholders. The
settings class is `backend/app/core/config.py`.

| Variables | Purpose |
|---|---|
| `DATABASE_URL`, `POSTGRES_USER/PASSWORD/DB` | app connection; container init |
| `REDIS_URL` | rate limits |
| `S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | image storage |
| `JWT_SECRET`, `COOKIE_SECURE`, `ALLOW_REGISTRATION` | auth (`auth.md`) |
| `DOMAIN`, `PUBLIC_BASE_URL`, `CORS_ORIGINS` | public origin, links in emails, CORS |
| `MAIL_BACKEND`, `SMTP_*` | mail, see "Mail" |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google sign-in; both empty hides the button |
| `ANTHROPIC_API_KEY` | background translation of personal names (BR-16); empty disables it |
| `JOB_REPORT_TOKEN` | `coin-parser` job reports (`admin.md`) |
| `TELEGRAM_BOT_*`, `TELEGRAM_WEBHOOK_SECRET` | private admin bot (`admin.md`) |
| `SUPPORT_TELEGRAM_*` | public support bot (`telegram-support.md`) |
| `LOG_LEVEL` | default `INFO` |

Notes:

- **`PUBLIC_BASE_URL`** builds the links in verification and reset emails. Never derive
  them from request headers — a forged `Host` would send the user to another domain.
- **`S3_PUBLIC_ENDPOINT`** (`https://<domain>/media`) is the browser-reachable host that
  presigned GET URLs are signed for; `S3_ENDPOINT` (`http://minio:9000`) only resolves
  inside the docker network. Leave it empty locally (`media.md`).
- **`ALLOW_REGISTRATION=true`** is the normal state; the flag is an emergency switch
  (flip it and restart, no deploy) against a bot wave.
- **`JOB_REPORT_TOKEN`** is shared with the `coin-parser` container, which reads the same
  `.env`. Empty disables job reporting entirely.
- **Telegram:** an empty bot token disables sending (messages go to the log, so a dev
  machine can never post to a real chat); an empty webhook secret makes the webhook
  answer `404`. The username builds the `t.me/<bot>?start=…` link behind "connect".

## Mail

| `MAIL_BACKEND` | Behavior | Where |
|---|---|---|
| `console` | the whole message, link included, is written to the log; nothing leaves the process | local, tests, CI |
| `smtp` | real delivery via `SMTP_*` | server |

Only the transport changes; registration and password reset run the same code in both
modes. Tests always run with `console`. `MAIL_BACKEND=smtp` without `SMTP_HOST` fails
at startup.

**Provider: Resend over SMTP** (`smtp.resend.com:587`, user `resend`, password = API
key, STARTTLS). No own mail server — deliverability from a single VPS is poor. Setup:

1. Add the sending domain in Resend; add its DNS records (SPF, DKIM) and DMARC; wait for
   `Verified`.
2. Create an API key with send permission; put it only in `SERVER_ENV`.
3. Set `MAIL_BACKEND=smtp` and `SMTP_FROM="Bakost Numismatics <noreply@<verified-domain>>"`
   — the address must belong to the verified domain.
4. Redeploy, register a test account, check the verification email; request a password
   reset and check that email too.

## Google sign-in

Create a **Web application** OAuth client in Google Cloud Console with the exact
redirect URI `https://<domain>/api/v1/auth/google/callback` (one client per
environment), scopes `openid email profile`. Put `GOOGLE_CLIENT_ID` and
`GOOGLE_CLIENT_SECRET` into that environment's `SERVER_ENV`; the secret never reaches
the frontend. While the consent screen is in Testing mode only test users can sign in —
switch it to Production before a public launch.

## Caddy

The server runs **one central Caddy** for several sites, outside this compose project.
Its block for this site is edited by hand on the server. The repository's `Caddyfile`
and the `caddy` compose service (profile `proxy`) are the reference configuration and a
way to run the full stack locally; changes to the reference must be copied to the
central Caddyfile manually.

Required site block (upstream names as on the server):

```
<domain> {
    handle /api/* {
        request_body {
            max_size 13MB
        }
        reverse_proxy <api upstream>
    }
    handle_path /media/* {
        reverse_proxy <minio upstream>
    }
    handle {
        root * /srv/coinkeeper/frontend
        @assets path /assets/* /brand/*
        header @assets Cache-Control "public, max-age=31536000, immutable"
        @entry path / /index.html /catalog /catalog/* /manifest.webmanifest
        header @entry Cache-Control "no-cache"
        try_files {path} {path}/index.html /index.html
        file_server
    }
    encode gzip zstd
    header {
        Strict-Transport-Security "max-age=31536000; includeSubDomains"
        X-Content-Type-Options nosniff
        Referrer-Policy no-referrer
    }
}
```

- **`handle` order matters:** without the `/api/*` and `/media/*` handlers the SPA
  fallback would answer API calls with `index.html`.
- **`try_files {path} {path}/index.html /index.html`** serves prerendered catalog pages
  first, then falls back to the SPA, so deep links like `/reset-password?token=…` work.
- **`max_size 13MB`** is one megabyte over the 12 MB an image upload may carry
  (`MAX_SOURCE_BYTES`), so oversized bodies stop at the edge. The API checks
  `Content-Length` itself too, in case a request bypasses Caddy.
- **`/media/*` uses `handle_path`**, which strips `/media` so MinIO sees its path-style
  `/<bucket>/<key>`. `Host` passes through unchanged — the presigned signature covers it.
- **Caching:** hashed `assets/*` are immutable; `index.html` and entry routes are
  `no-cache`, otherwise an old page would request deleted bundles after a deploy.
- **`Referrer-Policy no-referrer`** keeps tokens in email links out of `Referer`.
- The API takes the client IP (rate limits) from the first `X-Forwarded-For` entry.
  That's safe only because Caddy (without `trusted_proxies`) replaces any incoming
  `X-Forwarded-For` and the API has no host port. Putting another proxy in front
  (e.g. Cloudflare in proxied mode) requires revisiting `client_ip` in
  `app/api/deps.py`.

## Frontend delivery

The frontend is static: `vite build` → `frontend/dist`, served by Caddy from disk; no
Node process on the server. Fonts are self-hosted, no external CDNs. The client calls a
relative `/api/v1`, so one `dist` works behind any domain.

Delivery (job `deploy-frontend`, after the API deploy succeeded, so a new bundle never
meets an old schema):

1. download the `frontend-dist` artifact built and checked by `frontend-build`;
2. `frontend/scripts/prerender-catalog.mjs` reads the public catalog from the live API
   (`site-url` input) and adds crawlable HTML pages for the catalog and coins,
   `sitemap.xml` and `robots.txt` to `dist/`;
3. `rsync` to the deploy user's staging directory `~/frontend-dist/`;
4. on the server: `rsync -a --delete --delay-updates ~/frontend-dist/ /srv/coinkeeper/frontend/`.

**Why rsync into the same directory:** the central Caddy bind-mounts
`/srv/coinkeeper/frontend` read-only and holds its inode — replacing the directory with
`mv` would leave Caddy serving the old one. `--delay-updates` renames all changed files
in one final pass, `--delete` removes old hashed bundles. The directory must be owned by
the deploy user (one-time `chown -R deploy:deploy /srv/coinkeeper/frontend` as root);
the job fails with a clear message if it isn't writable.

Emergency path without GitHub: `npm run build`, then
`rsync -a --delete --delay-updates frontend/dist/ deploy@<host>:/srv/coinkeeper/frontend/`.

## Deployment

GitHub Actions deploys every push to `main`. Pull requests run the checks and build and
push an image (tagged with the PR's SHA, and `latest`), but never deploy.

```
.github/workflows/deploy.yml        project file: triggers and parameters only
.github/workflows/build-deploy.yml  reusable workflow (workflow_call): all the logic
```

The reusable workflow is generic (FastAPI + Postgres + Compose on an own server) so it
can move to its own repository and be pinned by tag once a second project uses it.

| Job | What it does |
|---|---|
| `check` | backend: ruff format, ruff check, mypy, pytest against Postgres + Redis service containers |
| `frontend-build` | Prettier, ESLint (`--max-warnings=0`), typecheck, Vitest, prerender test, build → `frontend-dist` artifact |
| `build` | only if both checks passed: Docker image (`target: production`) → GHCR, tagged with the commit SHA and `latest` |
| `deploy` | writes `SERVER_ENV` + `API_IMAGE=<image>:<sha>` to the server `.env`, `docker compose pull api && up -d api`, prunes images, then polls `/api/v1/health` inside the container for up to 150 s |
| `deploy-frontend` | see "Frontend delivery" |

- **Only the `api` service is redeployed.** Postgres, Redis and MinIO are changed by hand.
- **Migrations run when the `api` container starts** (`alembic upgrade head && uvicorn …`),
  before it accepts traffic — never as a separate pipeline step, so the schema never
  moves ahead of the code. **A pushed migration changes the production database:** take
  a dump first. There's no automatic downgrade; every migration must be reversible or
  safe.
- **Rollback:** point `API_IMAGE` at a previous SHA tag and `docker compose up -d api` —
  no rebuild.

### Secrets

In GitHub repository secrets, never in code or logs:

| Secret | Purpose |
|---|---|
| `DEPLOY_SSH_KEY` | the deploy user's private key, separate from any personal key |
| `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH` | where and as whom to deploy; directory with `docker-compose.yml` |
| `SSH_KNOWN_HOSTS` | pinned host key — without it the host check is off and a deploy could be redirected |
| `SERVER_ENV` | the complete server `.env` |

**`SERVER_ENV` is the single source of truth for the server `.env`.** Every deploy
overwrites the file, so a change made directly on the server is lost on the next push —
always change the secret. The deploy user may only manage its own directory and run
`docker compose`; it has no root.

### Emergency manual deploy

If GitHub or the pipeline is down, on the server:

```
docker compose pull api && docker compose up -d api     # image already in GHCR
docker compose build api && docker compose up -d api    # build on the server
```

Anything deployed by hand must go through the pipeline again once it works, or the
server drifts from `main`.

## Logging and health

- JSON logs to stdout (`app/core/logging.py`), read with `docker compose logs`.
- `GET /api/v1/health` reports database, Redis and object storage separately; the
  container healthcheck and the deploy smoke check use it.
- Rejected prices, external-source calls and failed jobs are logged (in `coin-parser`
  for scheduled jobs); job runs are visible in `/admin` (`admin.md`).

No Sentry, Prometheus or Grafana — add them when real load appears.

## Backups

**Not implemented** (`backlog.md`, "Production hardening"). Today there are only manual
`pg_dump`s before risky migrations. The target:

- Postgres: daily `pg_dump -Fc`, keeping 7 daily, 4 weekly, 6 monthly;
- MinIO: `rclone` sync to external storage (Hetzner Storage Box or Backblaze B2);
- never only on the same server;
- a monthly restore into a separate database with record counts compared — a backup
  that was never restored doesn't count.

## Server security

Repository side (done): Postgres, Redis and MinIO have no host ports in production;
`CORS_ORIGINS` lists the frontend origin only (no `*`); the image runs as non-root.

Server side (to verify, not visible from the repository): SSH by key only, password
login off; firewall open only for 80, 443 and SSH; unattended security upgrades (not
configured); regular base-image updates.
