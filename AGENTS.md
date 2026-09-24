# Bakost Numismatics — agent guide

Canonical instructions for every coding agent in this repository (Codex reads this file
natively; Claude Code reads it through `CLAUDE.md`). Keep tool-specific notes out of here.

## What this is

A web app for tracking a coin collection: a shared catalog of coin issues, personal
catalog positions, a personal collection with purchases and expenses, market prices and
completeness by any grouping. Public, open registration, interface in Ukrainian and
English. Product name **Bakost Numismatics**; `coinkeeper` is the technical identifier
(packages, containers, image names) until the repository is renamed.

**The MVP is complete.** Work from here is fixes, review, design polish and, later,
new features planned in `docs/backlog.md`. Don't add functionality nobody asked for.

Background jobs (NBU rates, NBU catalog sync, UA-Coins prices) do **not** live here —
they run on cron in the separate `coin-parser` repository and write to this database /
report to this API (`docs/integrations.md`, `docs/admin.md`).

## Stack

| Layer | Technology |
|---|---|
| API | FastAPI, Pydantic v2, Python 3.12+ |
| ORM / DB | SQLAlchemy 2.0 (async), Alembic, PostgreSQL 16 |
| Cache / rate limits | Redis |
| File storage | S3-compatible (MinIO) |
| Frontend | React 19, TypeScript, Vite, TanStack Query, i18next |
| Deploy | Docker Compose on Hetzner, Caddy, GitHub Actions → GHCR → SSH |

Don't introduce new infrastructure (queues, workers, new services) without discussion.

## Repository map

```
AGENTS.md            this file — rules for agents
CLAUDE.md            imports this file + Claude-only notes
docs/                specs; start at docs/README.md
  doc-map.toml       which document describes which code (drives the hook and CI)
tools/docs_check.py  docs consistency checks (commit-msg hook, CI)
.githooks/           git hooks; enable with `git config core.hooksPath .githooks`
.agents/skills/      skills shared by Codex and Claude (.claude/skills links here)
.claude/agents/      Claude Code subagents — thin wrappers over the skills
backend/app/
  api/v1/            routes — thin, no business logic, no visibility filters
  services/          business logic
  repositories/      all DB access; visibility filters live HERE
  models/            SQLAlchemy models
  schemas/           Pydantic request/response bodies
  core/              config, security, storage, mail, telegram, rate limits
  reference_data/    seeded dictionaries (materials, countries, edge types…)
backend/alembic/     migrations — the only way the schema changes
backend/scripts/     operator scripts (promote_admin, watchdog, photo backgrounds…)
backend/tests/       pytest against a real Postgres
frontend/src/
  app/               routing, layout, guards
  features/<area>/   one folder per screen area (catalog, collection, expenses, admin…)
  shared/            api client + generated OpenAPI types, i18n, ui kit, theme
```

## Commands

Local setup, test dependencies and gotchas: `docs/development.md`. Once per clone, enable
the docs hook: `git config core.hooksPath .githooks`. The checks CI runs, all of which
must pass before a push:

```bash
# backend/
uv run ruff format --check . && uv run ruff check . && uv run mypy app scripts && uv run pytest -q
# frontend/
npm run format:check && npm run lint -- --max-warnings=0 && npm run typecheck && npm test && npm run test:seo
# repository root
python3 tools/docs_check.py refs && python3 tools/docs_check.py table --check
```

## Architecture rules

### Three data layers

`catalog_items.created_by` decides a record's layer:

| Layer | Marker | Who writes |
|---|---|---|
| Shared catalog | `created_by IS NULL` | admin and system jobs only |
| Personal position | `created_by = <user>` | its author, full CRUD |
| Collection | `collection_items.owner_id` | the owner only |

- The shared catalog is **read-only for users**. Any attempt to change it → `403`.
  If a user needs their own record, that's a personal position.
- The visibility filter `created_by IS NULL OR created_by = :user_id` and every
  `owner_id` filter live in **repositories**, never in routes.
- New shared records from the NBU sync arrive as `status = 'draft'` and are published
  by an admin; drafts never reach the storefront, search or completeness.

### Archive, never delete (shared catalog)

Shared-catalog records are archived (`is_archived` + reason), not deleted — other users'
instances, purchases and expenses hang off them. This applies to system jobs too.
Physical deletion is a rare admin operation, only after archiving and only when nothing
references the record. Storefront, search and completeness count active records only.

### Price snapshot visibility

`market_price_snapshots.created_by`: `NULL` = the central daily job, visible to everyone;
`<user>` = that user's own entry, visible and counted only for them. Collection value =
shared snapshots + the user's own. Prices from external sources are validated **before**
they're written (`docs/integrations.md`); snapshots flagged `is_suspect` are excluded
from value.

### Image provenance

Every `media_files` row has a `source` that drives visibility (`docs/media.md`):

- `nbu`, `ua_coins`, `manual` — public catalog photos;
- `user_upload` — the owner's private photos;
- `ucoin` — only whoever imported it; others see a placeholder. We don't own rights to
  uCoin images, and copying them to our storage doesn't change `source`.

### Data rules

- Money is `Numeric(14, 2)`, never `float`. Dates are `date` / `timestamptz`, never text.
- Every schema change goes through an Alembic migration. Migrations apply automatically
  when the API container starts — **a pushed migration changes the production database**.
- No scheduled crawling of uCoin (Cloudflare, someone else's data).

## Coding behavior

### Think before coding
Before implementing anything:
- State assumptions explicitly. If uncertain, ask — do not guess and proceed.
- If multiple interpretations exist, present them. Do not pick silently.
- If something is unclear, stop. Name what is confusing. Ask for clarification.
- If a simpler approach exists, say so and push back.

### Simplicity first
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that was not requested.
- If 200 lines could be 50, rewrite it.

### Surgical changes
- Do not "improve" adjacent code, comments, or formatting.
- Do not refactor things that are not broken.
- Match existing style, even if you would do it differently.
- If you notice unrelated dead code, mention it — do not delete it.
- Every changed line must trace directly to the user's request.

### Goal-driven execution
For any task that changes more than 2 files or contains more than one logical unit of
change — before writing any code:
1. Read all affected files.
2. Output a numbered step-by-step plan where each step is one logical unit of change
   (one validator, one method, one migration, one screen).
3. Stop and wait for explicit approval before implementing step 1.
4. After completing each step, stop again and wait for approval before proceeding to the
   next step.

For simple isolated changes (single file, clear scope) — proceed directly without a plan.

## Permissions

You may freely use read-only operations (grep, cat, find, ls, read, `git log/diff/show`,
running tests and linters) without asking for approval.

You must ALWAYS stop and wait for explicit approval before:
- modifying any existing file;
- creating any new file;
- running any command that writes to disk outside the scratch/test areas;
- running any command that affects a database or Redis;
- committing or pushing — every time; approval for one commit doesn't cover the next;
- anything on the server (`ssh`, `scp`, production SQL) — see the `prod-ops` skill.

## Skills and roles

Procedures live in `.agents/skills/<name>/SKILL.md`, shared by every tool; read the
matching one before starting that kind of work. In Claude Code the three roles also
exist as subagents (`.claude/agents/`) with their own context and read-only tools.

| Skill | Use for | Claude subagent |
|---|---|---|
| `architecture-audit` | read-only audit: data layers, DB performance, transactions, security | `architect` |
| `review` | reviewing a diff against project rules before commit/merge | `reviewer` |
| `debug` | bug → reproduction → proven cause → minimal fix + regression test | `debugger` |
| `migration` | any schema or data change through Alembic | |
| `add-endpoint` | a route, response field, filter or feature across layers | |
| `prod-ops` | anything on the server or against the production database | |
| `deploy-watch` | following a push through CI and deploy, health check | |
| `sync-docs` | auditing docs against code changed since each doc's last update | |

## Language rules

- **Everything in the repository is English**: identifiers, comments, docstrings, logs,
  error text (`detail`), commit messages, branch names, migration names, tests, docs.
  No Russian anywhere, not even in throwaway scripts.
- **Exception — data:** coin, country and series names keep their original language.
- **Interface:** Ukrainian and English only (`'uk' | 'en'`, default `'uk'`). Every
  user-facing string lives in `frontend/src/shared/i18n/{uk,en}.json` — never inline
  in components, validators, or API responses the frontend shows verbatim.

## Working agreement

- **Read the relevant spec before changing code** — `docs/README.md` maps code areas to
  documents.
- **Docs live with the code — updated before the commit, not after.** Before committing,
  map your changed files through `docs/doc-map.toml` (table in `docs/README.md`) and
  update every affected document in the same commit. The `commit-msg` hook blocks a
  commit that skips one; if behavior, API, schema, UI and infra truly didn't change,
  add the trailer `Docs: not needed (<why>)` — never use it to postpone a doc update.
  Docs describe the **current state**, in English — no changelogs, stage numbers or
  "was / now" notes; history is what git is for.
- **Cite docs precisely.** `docs/<file>.md, "Section heading"` or
  `docs/business-rules.md, BR-N` — never section numbers. Renaming a heading means
  updating its citations; `python3 tools/docs_check.py refs` finds broken ones.
- **Audit on request** with the `sync-docs` skill (`.agents/skills/sync-docs/SKILL.md`):
  it compares code changed since each document's last update against the document.
- **Tests in multi-task sessions.** Run the tests for the current task as you go, and
  the full suite plus the docs checks once at the end.
- **The repository is public.** Never commit `.env`, dumps, `*.db`, keys, or real
  collection photos. Check `git status` before every commit.
- **`docs/current_ref/` is scratch.** The owner drops screenshots there for one
  conversation. Never link to anything in it — from code, tests, docs or commit messages.
  If a screenshot led to a decision, describe the decision in words in the right doc.
