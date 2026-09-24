# Documentation

Specs for Bakost Numismatics. Every document describes the **current state** of the
system, in English. History lives in git, not here. Rules for agents and contributors:
`../AGENTS.md`.

## Map

| Document | What it covers | Read before |
|---|---|---|
| [product.md](product.md) | What the app does, in plain language | explaining the project to anyone |
| [scope.md](scope.md) | What's in, what's deliberately out | planning any feature |
| [data-model.md](data-model.md) | PostgreSQL schema, constraints, data origins | models, migrations |
| [api.md](api.md) | REST endpoints and their contracts | routes, Pydantic schemas, frontend API calls |
| [business-rules.md](business-rules.md) | Completeness, currencies, cost, visibility, deduplication | services, repositories |
| [auth.md](auth.md) | Registration, email, JWT, Google OAuth, ownership | anything touching users or access |
| [media.md](media.md) | Image storage, sizes, provenance and rights | image upload or display |
| [integrations.md](integrations.md) | NBU, UA-Coins, uCoin; price validation; `coin-parser` | anything fed by external data |
| [ui.md](ui.md) | Screens, navigation, visual rules | frontend work |
| [admin.md](admin.md) | `/admin`, job runs, admin Telegram bot, watchdog | admin features, job reporting |
| [telegram-support.md](telegram-support.md) | Public support bot | support bot changes |
| [infra.md](infra.md) | Servers, Compose, Caddy, CI/CD, mail, backups | deploy or server changes |
| [development.md](development.md) | Local setup, tests, CI checks | your first change |
| [backlog.md](backlog.md) | Open issues and deferred work | picking the next task |

## Which document to update

A change that alters behavior updates the matching document **in the same commit**.

| You changed | Update |
|---|---|
| `backend/app/models/`, `backend/alembic/` | `data-model.md` |
| `backend/app/api/v1/`, `backend/app/schemas/` | `api.md` |
| `backend/app/services/`, `backend/app/repositories/` (rules, visibility, calculations) | `business-rules.md` |
| `api/v1/auth.py`, `api/v1/google_auth.py`, `services/auth.py`, `core/security.py` | `auth.md` |
| `core/storage.py`, `core/images.py`, `core/media_keys.py`, `services/*photos*.py`, `repositories/media.py` | `media.md` |
| price validation, rates, anything `coin-parser` writes or reports | `integrations.md` |
| `frontend/src/features/`, `frontend/src/app/`, navigation, theme | `ui.md` |
| `api/v1/admin.py`, `api/v1/jobs.py`, `core/telegram/`, `scripts/watchdog.py` | `admin.md` |
| `api/v1/support.py`, `core/support_telegram.py`, `services/support.py` | `telegram-support.md` |
| `docker-compose*.yml`, `Caddyfile`, `.github/workflows/`, `.env.example`, `core/config.py` | `infra.md` |
| dev tooling, test setup, CI check list | `development.md` |
| user-visible capability added or removed | `product.md`, `scope.md` |
| a backlog item done (or found done) | remove it from `backlog.md` |

## Writing docs

- Current state only. No "stage N", "was / now", "decided on <date>" — if a decision's
  reasoning matters, state the reasoning, not the date.
- Code comments reference docs as `docs/<file>.md`, optionally with a section name.
  Prefer section **names** over numbers — numbers shift when a document is edited.
- UI copy lives in `frontend/src/shared/i18n/`, not in docs. Quote a string in a doc only
  when the rule is about that string.
- Never link to `docs/current_ref/` (scratch screenshots for one conversation).
