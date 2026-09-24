# Decisions

Why the system is the way it is, and what the owner still has to decide. Each decision is
a short statement plus the reason; the details live in the linked document. When a
decision changes, rewrite its entry (git keeps the old one). Work items belong in
`backlog.md`, not here.

## Settled

**Three data layers; the shared catalog is read-only for users.** Other people's
collections hang off shared records, so no user may change them; whatever a user needs
beyond the shared catalog becomes a personal position (`business-rules.md`, BR-2).

**Archive, never delete, shared records.** Deleting would destroy other users'
instances, purchases and price history (BR-10).

**Personal positions are created only inside a purchase.** Users record coins they
bought, not catalog entries; one transaction means no orphan positions (BR-2, BR-4).

**Scheduled jobs live in `coin-parser` on cron, not in this repo.** They are scrapers
with their own dependencies and failure modes; keeping them out of the API keeps the API
image small and its deploys independent. No job queue here — `BackgroundTasks` covers
the two short in-request jobs (`integrations.md`, "Who does what").

**UAH is the only currency sums are computed in.** USD/EUR are conversions of finished
UAH numbers at the purchase-date rate, never a second computation path (BR-6).

**Three name slots — original, Ukrainian, English; no Russian slot.** The original is
what the issuer called the coin; Russian is an original only for Soviet coins (BR-12).

**`catalog_confirmed` gates only the catalog screen.** A country counts as "catalog" once
its catalog has been verified against an official source; the user's own collection
screens show everything they own regardless (BR-13a).

**All media in our own storage; provenance drives visibility.** A copy doesn't change who
holds the rights: `ucoin` images stay private to the importer (`media.md`,
"Provenance and rights").

**Web only.** No desktop, offline mode or local database; mobile apps, if ever, go on
top of the same API (`product.md`, "Out of scope").

**Open registration with mandatory email verification** (`auth.md`, "Accounts").

**Docs describe the current state and are enforced before the commit.**
`docs/doc-map.toml` + the `commit-msg` hook + CI (`README.md`, "How docs are kept in
step").

## Open questions (owner)

- **Owned records of inactive countries in shared listings** (BR-13, point 3) — keep,
  mark them in the UI, or narrow the scope.
- **Hidden catalog filters** "Обсяг" and "Показати архівні" — expose in the UI or drop.
- **Admins see drafts in the storefront and search** — intended, or show them only in
  `/admin/proposals`.
- **UI copy outside i18n** (landing, legal pages) — move to the JSON files or accept as
  an exception in `AGENTS.md`.
- **Account deletion** — a public service is expected to offer it; scope and flow.
- **Photo deletion** — immediate and unaudited today; add confirmation/audit or keep.
- **ua-coins photo rights** — public with attribution today; settle before promotion.
- **dev/prod split** — one server or two, one Postgres or two, and whether dev is closed
  to outsiders (`infra.md`, "Environments").
- **New repository** — public or private.
