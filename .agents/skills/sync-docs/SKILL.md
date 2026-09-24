---
name: sync-docs
description: >
  Audit docs/ against code changes since each document was last updated and
  propose patches. Use when asked to sync, audit or check the docs, before a release,
  or after a series of commits that used the "Docs: not needed" trailer.
---

# sync-docs

The commit-msg hook catches a missing document per commit; this skill catches what slipped
through anyway — a wrong "Docs: not needed", a doc edited but not fully, drift that built
up over many small commits. Rules for docs: `docs/README.md`.

## Step 1 — Mechanical checks

Run `python3 tools/docs_check.py refs` and `python3 tools/docs_check.py table --check`.
Report any failures first; they're unambiguous.

## Step 2 — Code changed since each document

For every rule in `docs/doc-map.toml` that has `paths`:

1. `last=$(git log -1 --format=%H -- <doc>)` — the last commit that touched the document.
2. `git log --format='%h %s' $last..HEAD -- <paths>` — code commits since then.
3. Also list commits with a `Docs: not needed` trailer in that range:
   `git log --format='%h %s' --grep='^Docs: not needed' -i $last..HEAD -- <paths>`.

No commits → "no changes" for that document; say so explicitly, don't skip it.

## Step 3 — Compare

For each document with changes, read the diffs (`git diff $last..HEAD -- <paths>`) and the
document, and list what is now missing, stale or wrong: new or removed endpoints, fields,
columns, screens, rules, limits, error codes, config keys. A pure refactor with no
behavior change is noted as such, with no doc change proposed.

## Step 4 — Report before editing

```
== sync-docs ==
api.md (last touched abc1234, 2026-10-02)
  Code commits since: def5678 Add sort by mintage; 9a0b1c2 Rename seller field
  Proposed:
  - "Catalog filters": add `sort=mintage`
  - "Buying a coin": `seller` → `sellerName`
data-model.md — no changes
== end ==
Apply? Confirm per document or "all".
```

## Step 5 — Apply after confirmation

Patch only the affected sections, current state only, English, headings kept stable (code
cites them). If a heading must change, update every citation in the same change and rerun
`tools/docs_check.py refs`. Commit docs as their own commit with a message naming the
commits they catch up with.

## Rules

- Never edit a document without the owner's confirmation.
- Never rewrite a document wholesale; surgical patches only.
- The code is the source of truth. If code and doc disagree and the code looks wrong,
  report it as a possible bug instead of documenting the bug.
