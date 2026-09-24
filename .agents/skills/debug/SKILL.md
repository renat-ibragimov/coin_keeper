---
name: debug
description: >
  Disciplined bug investigation: reproduce, prove the cause, fix minimally, lock it with a
  regression test. Use for any bug report or unexpected behavior.
---

# debug

No fix before the cause is proven. Guessing and patching symptoms is how the MVP got
its one-off repair migrations.

1. **Restate** the bug: expected vs actual, where (screen / endpoint / job), who (guest,
   user, admin), since when. Ask if any of it is unknown.
2. **Reproduce locally** — a failing pytest (backend) or Vitest (frontend) is the best
   reproduction. If it only shows on production, gather evidence read-only via the
   `prod-ops` skill (logs, `SELECT`s) — never experiment on production data.
3. **Hypotheses** — list candidates, then test each with the cheapest discriminating check
   (a log line, a query, a breakpoint-equivalent print in a test). Write down what each
   check showed.
4. **Root cause** — explain the mechanism in one paragraph, tracing the actual code path.
   If the cause is in `coin-parser` or data rather than this repo, say so and stop.
5. **Plan the fix** — smallest change at the cause, not at the symptom; if more than one
   file, a numbered plan and stop for approval (AGENTS.md).
6. **Fix + regression test** — the failing test from step 2 now passes; related tests
   pass; full check set before proposing a commit.
7. **Report** — cause, fix, test, and anything similar elsewhere worth checking (same
   pattern in other repositories/services).

Past traps worth checking early: request session committed after `BackgroundTasks` ran
(BR-4); visibility predicate missing in one listing but present in another; stale
frontend bundle (hard refresh); parser fixtures that didn't match the live page.
