---
name: add-endpoint
description: >
  Layer-by-layer checklist for adding or changing an API endpoint or a feature that
  crosses backend and frontend. Use when a task adds a route, a field in a response, a
  filter, or a screen that needs new data.
---

# add-endpoint

Plan first (AGENTS.md, "Goal-driven execution"): one step per layer below, stop for
approval between steps. Read the relevant docs before step 1: `api.md`,
`business-rules.md`, `data-model.md`, `ui.md`.

1. **Schema change?** → `migration` skill first, as its own step.
2. **Repository** (`backend/app/repositories/`): all SQL here. Apply the layer
   visibility filter (`created_by IS NULL OR created_by = :user`), `owner_id` scoping,
   `NOT is_archived` / `status = 'active'` where listings need it, and the storefront
   predicate (`storefront_visible()`, BR-13/BR-13a) for catalog-wide lists. Check the
   query against existing indexes (`data-model.md`); no N+1 — batch-load related rows.
3. **Service** (`backend/app/services/`): business rules, transactions. Explicit
   `session.commit()` before scheduling `BackgroundTasks` (BR-4). Shared-catalog writes →
   `403` for non-admins.
4. **Schema** (`backend/app/schemas/`): camelCase via `CamelModel`, money as `Money`,
   no user-facing text in responses — error `detail` is an English slug the frontend
   maps through i18n.
5. **Route** (`backend/app/api/v1/`): thin — parse, call the service, map errors. Guest
   access only if explicitly intended (`api.md`, "Guest access and rate limits").
6. **Tests** (`backend/tests/`): happy path, other user's data invisible, guest/regular/
   admin permissions, archived and draft records, validation errors.
7. **Docs**: `api.md` (+ `business-rules.md` with a new `BR-N` if it's a new rule).
8. **Frontend types**: after deploy `npm run gen:api`, or edit
   `src/shared/api/generated/openapi.ts` consistently with the backend docstrings.
9. **Frontend**: API call in `features/<area>/api.ts` via TanStack Query; every string in
   both `shared/i18n/uk.json` and `en.json`; both themes; phone width first.
10. **Docs**: `ui.md` for screen changes; `product.md` if users gain a capability.
11. **Checks**: full CI set (AGENTS.md, "Commands"); commit only with approval.
