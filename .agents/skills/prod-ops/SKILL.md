---
name: prod-ops
description: >
  Runbook for anything on the production server: SSH, logs, production SQL, one-off
  scripts, dumps, server .env. Use before running any command on the server or against
  the production database.
---

# prod-ops

Every server action needs the owner's explicit approval (AGENTS.md, "Permissions").
Propose the exact commands first; run them only after "ok". Read-only first, always.

## Access

- `ssh coinkeeper` — alias in the owner's `~/.ssh/config` (user `deploy`, port **2222**;
  port 22 doesn't answer). `scp -P 2222` — capital `P`.
- The stack lives in `~/coinkeeper` (compose project), frontend static in
  `/srv/coinkeeper/frontend`, the central Caddy in `/srv/caddy`.
- Sessions drop ("Broken pipe"): anything longer than a minute runs inside `tmux`.
- Never print or copy secrets from the server `.env`. The server `.env` is rewritten from
  the `SERVER_ENV` GitHub secret on every deploy — a change made only on the server is
  lost on the next push (`docs/infra.md`, "Secrets").

## Reading

```bash
cd ~/coinkeeper
docker compose ps
docker compose logs --since 1h api | tail -200          # never unbounded
docker compose exec -T api python -c "…"                # read-only probes only
```

Production SQL, read-only, always in this exact form:

```bash
docker compose exec -T postgres psql -U coinkeeper -d coinkeeper -P pager=off -c "SELECT …"
```

Start with `SELECT count(*)` before selecting rows; `LIMIT` everything.

## Writing (only after explicit approval of the exact command)

1. **Dump first** — before any data change, migration or large script run:
   ```bash
   docker compose exec -T postgres pg_dump -U coinkeeper -d coinkeeper -Fc -f /tmp/pre-<what>.dump
   docker compose cp postgres:/tmp/pre-<what>.dump ~/dumps/
   docker compose exec -T postgres pg_restore --list /tmp/pre-<what>.dump | head   # validate
   ```
   Never dump through `exec` stdout — binary output gets mangled.
2. **Scripts: `--dry-run` before `--apply`**, one mode at a time, never in parallel:
   `docker compose run --no-deps --rm api python scripts/<script>.py --dry-run`
   (`--no-deps`, or compose waits for / starts dependencies).
3. SQL writes: wrap in `BEGIN; … ; SELECT <check>; ROLLBACK;` first, show the result,
   then the same with `COMMIT` after approval.
4. **Verify after**: a `SELECT` for the final state (not the script's own report) and a
   look at the affected screens. Most real bugs were found on the storefront, not in
   reports.

## Never

- Edit the schema by hand — migrations only (`migration` skill).
- Delete shared-catalog rows — archive (AGENTS.md).
- Run `docker compose down -v`, `docker volume rm`, `docker system prune --volumes`.
- Leave a dump or CSV with personal data anywhere near the repository.
