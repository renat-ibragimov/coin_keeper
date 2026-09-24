---
name: migration
description: >
  Procedure for any database schema or data change through Alembic. Use whenever a task
  touches backend/app/models/ or needs a new migration.
---

# migration

A pushed migration runs on production when the api container starts
(`docs/infra.md`, "Deployment"). Treat every migration as a production operation.

## 1. Plan (stop for approval)

State: what changes in the schema, whether existing rows need a backfill, whether it's
reversible, whether the running old code survives the new schema during deploy (the API
restarts after the migration). Name the docs to update: `data-model.md` always, plus
`api.md` / `business-rules.md` when behavior changes.

## 2. Write

- `cd backend && uv run alembic revision -m "<short_english_name>"` — next number in
  sequence (`00NN_<name>.py`), English docstring saying **why**.
- Write it by hand. Autogenerate only as a cross-check.
- Money `Numeric(14, 2)`, dates `date`/`timestamptz`, enums as in `app/models/enums.py`.
- Update the model in the same change. Declare every index the migration creates in the
  model too — otherwise autogenerate later proposes dropping it.
- Data migrations: idempotent, batch large updates, never delete shared-catalog rows.
- `downgrade()` must work. If a true downgrade is impossible (data loss), say so in the
  docstring and get approval.

## 3. Verify locally

```bash
cd backend
uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
uv run alembic check 2>&1 | grep -c "Detected"   # models vs migrations
uv run pytest -q                         # tests run the real migrations
```

`alembic check` isn't clean yet — a known drift (`docs/backlog.md`, "Model/migration
drift"). Run it before and after your change: the count must not grow, and nothing in
the output may mention your tables or columns. Once the backlog item is closed, the rule
becomes "must be clean".

## 4. Before the push (owner)

- A production dump right before pushing (`prod-ops` skill, "Writing").
- Explicit approval for this specific push.
- After deploy: `deploy-watch` skill, then a `SELECT` confirming the new state.
