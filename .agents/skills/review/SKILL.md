---
name: review
description: >
  Review a diff (working tree, staged changes, a commit range or a branch) against this
  project's rules before it's committed or merged. Use when asked to review changes.
---

# review

Read-only. Review the **whole** diff — never a truncated listing (a pair of endpoints
once slipped past review that way). Default target: `git diff HEAD` plus untracked files;
otherwise what the owner names (`git diff <range>`, `git show <sha>`).

## Checklist

**Correctness** — logic errors, edge cases (empty, zero, null, archived, draft, other
user's id, guest), off-by-one in pagination, `Decimal` vs float, timezone/date handling,
error paths.

**Project rules (AGENTS.md)**
- Shared catalog read-only for users (`403`); archive, never delete.
- Visibility / `owner_id` filters in repositories, not routes.
- Money `Numeric(14, 2)`; dates typed; schema changes only via migration (+ model index
  declarations).
- No user-facing strings in code — i18n in both `uk.json` and `en.json`.
- English everywhere in code, comments, commit message.
- Commit before `BackgroundTasks` (BR-4).

**Docs** — every mapped document updated (`docs/doc-map.toml`); citations use
`"Heading"` / `BR-N`; `python3 tools/docs_check.py refs` passes.

**Tests** — new behavior covered, including permissions and other users' data; tests
assert behavior, not implementation.

**Scope** — changes that don't trace to the task (AGENTS.md, "Surgical changes"),
drive-by refactors, dead code added.

**Frontend** — both themes, phone width, `CoinImage` for every coin photo (`docs/ui.md`,
"Coin images"), query invalidation after mutations.

## Report

Findings ranked by severity, each with `file:line`, the concrete problem, and the fix.
Say explicitly when there's nothing blocking. Don't fix anything unless asked.
