---
name: architecture-audit
description: >
  Read-only deep audit of the whole codebase or one area for structural risks: data-layer
  leaks, database performance and correctness, transactions, concurrency, migrations,
  security, frontend state. Use when asked to audit, find weak spots or review the
  architecture.
---

# architecture-audit

Read-only. You change nothing; you produce a verified, prioritized findings report.
Read `AGENTS.md`, `docs/business-rules.md`, `docs/data-model.md` first — findings are
measured against them.

## Scope

Whole repo by default; if the owner names an area, only that area. For a whole-repo
audit, work dimension by dimension (below); where the tool supports parallel subagents,
give each dimension its own agent and merge.

## Dimensions and what to check

**1. Data layers and visibility** — every query over `catalog_items`,
`market_price_snapshots`, `media_files`, `collection_items`, `expenses`:
layer filter / `owner_id` present and applied in the repository, not the route; drafts
(`status`) and archived rows excluded where listings need it; storefront predicate used
consistently (BR-13, BR-13a); guest responses never carry prices or owned data; the
`ucoin` media rule.

**2. Database performance** — N+1 (queries inside loops, lazy loads); every hot
`WHERE`/`ORDER BY`/`JOIN` backed by an index in `data-model.md`/models; `COUNT(*)` over
large sets per request; unbounded result sets without pagination; aggregate queries that
could share one pass; `pg_trgm` installed but unused.

**3. Transactions and consistency** — multi-row writes in one transaction; commit order
vs `BackgroundTasks` (BR-4, BR-16); get-or-create races (unique constraint + retry, or
`ON CONFLICT`); service-layer deletes that the FKs don't enforce (BR-10); money math in
`Decimal` end to end, rounding in one place.

**4. Schema and migrations** — models vs migrations (`alembic check`), indexes declared
in both, reversible downgrades, `NO ACTION` vs cascade choices, nullable columns that
shouldn't be, unused columns.

**5. Security** — authz on every route (who can call it, whose data it touches), IDOR on
`/{id}` routes, rate limits on public and auth routes, `X-Forwarded-For` trust, secrets in
logs, upload validation, presigned URL lifetime, CORS, admin-only paths.

**6. Error handling and observability** — swallowed exceptions, silent early returns
without a log line, errors leaking internals, background tasks failing invisibly.

**7. Frontend** — TanStack Query keys (stale data across users/locales after sign-out),
optimistic updates without rollback, mutations that don't invalidate the queries they
affect, strings outside i18n, both themes, phone-width layout.

## Verify before reporting

For every candidate finding, try to disprove it: read the calling code, check for a guard
elsewhere, look for a test that covers it. Keep it only if it survives, and mark
**CONFIRMED** (you traced a concrete failing scenario) or **PLAUSIBLE** (likely, not
proven).

## Report

```
## Architecture audit — <scope>, <date>
### Critical / High / Medium / Low
- [CONFIRMED] <file:line> — <one-line problem>
  Scenario: <inputs/state → wrong result>
  Fix: <smallest change>
```

End with what you did **not** cover. Ask the owner which findings go to
`docs/backlog.md`; add them only after the answer.
