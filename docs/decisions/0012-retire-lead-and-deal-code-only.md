# 0012 — Retire the Lead and Deal code, keep their tables

## Context

ADR 0009 folded Lead into Contact and Deal into Quote
(`jobs/0003_fold_leads_and_deals`), and deliberately did not remove the
two models: "folding first and dropping in a later phase leaves a
verification window." Phase 18 unit 5 is that later phase.

The window has closed cleanly. Before starting, the development
database held 0 leads, 0 deals, 0 tasks pointing at a deal, 0
activities pointing at a lead or a deal, and 0 quotes carrying a legacy
deal id that no longer resolved. The two models had been read-only in
the admin since Phase 17 and their pages reachable only by typed URL.

`docs/ROADMAP.md` called the unit "removal of the retired Lead/Deal
models", while `CLAUDE.md`'s database-safety rules say never to DROP
TABLE in production. Those are not the same instruction, so the scope
of "removal" was the owner's call.

## Alternatives considered

- **Drop the models and the tables.** Rejected by the owner. It is the
  only irreversible option here, and the tables cost nothing to keep:
  two empty tables in a single-business database.
- **Drop the three dead pointer columns** (`crm_task.deal_id`,
  `crm_activity.lead_id`, `crm_activity.deal_id`) while keeping the
  tables. Drafted, implemented, and then abandoned — see Reason. This
  was the option that looked obviously right.
- **Leave the models in place and simply hide them.** Rejected: that is
  what Phase 17 already did, and it leaves two unused models, nine
  views, seven templates and an admin registration for anyone reading
  the code to understand and work around.

## Decision made

Remove every line of application code: the `Lead` and `Deal` models,
`Task.deal`, `Activity.lead`, `Activity.deal`, nine views, seven
templates, the forms, the admin registrations, the search branches, the
`undo` entries, and the lead/deal detail routes.

`crm/0011_retire_lead_and_deal` is **state-only** — `database_operations`
is empty and `sqlmigrate` prints a no-op. Django stops knowing about
any of it; PostgreSQL keeps all of it. `migrate crm 0010` undoes the
whole thing.

`/leads/` and `/deals/` redirect permanently to Customers and
Estimates, because both were in the menu for most of this project's
life. The detail and add URLs 404: there is no record to point at, so a
redirect would be a lie.

## Reason

The interesting half of this decision is the three pointer columns,
which were dropped in the first draft and are now kept.

They are empty, and three dead foreign keys on two busy tables are
clutter — a real argument, and the reason the first draft dropped them.
But `jobs/0003`'s fold reads `crm_task.deal_id` to re-point each task
at its new quote. Dropping that column:

1. breaks the Phase 17 rollback, which is the thing ADR 0009's
   verification window exists to preserve; and
2. breaks the nineteen tests that cover the fold, since they can only
   exercise it against the live schema.

It also surfaced a migration-ordering hazard that nothing in the graph
prevented. Nothing ordered `crm/0011` against `jobs/0003`, and Django's
topological sort happened to put the retirement **first** — so with the
drop in place, every build of a fresh database, the CI test database
included, failed in the fold with "column deal_id does not exist". The
drop is gone, but `crm/0011` now depends on `jobs/0003` anyway, so the
hazard cannot return if someone later fills in `database_operations`.

Three always-NULL columns are the cheaper of the two prices. Dropping
them stays available for a day when reversing Phase 17 is off the
table, with a confirmed backup, as a deliberate act rather than a side
effect of tidying up code.

## Consequences

- Nothing is destroyed by deploying this, and it is reversible with one
  command. That is the point.
- `docs/DATABASE_DESIGN.md` keeps the `Lead` and `Deal` field tables,
  moved under a "Retired entities" heading, because they now document
  tables that exist and that no code reads.
- `Contact.legacy_lead_id` and `Quote.legacy_deal_id` stay for as long
  as the tables do: they are the pointer from a current record back to
  the row it was folded from.
- `crm_lead` keeps foreign keys to `crm_company` and `crm_contact` that
  Django can no longer see. Harmless in practice — a foreign key only
  blocks a delete when a referencing row exists, `crm_lead` has none,
  and this app deactivates companies and contacts rather than deleting
  them — but worth knowing before writing raw SQL against either table.
  `on_delete` never held at the PostgreSQL level anyway
  (`docs/DATABASE_REVIEW.md` finding #1).
- The Phase 17 fold tests now build their models from the historical
  migration state instead of `apps.crm.models`, which is what the
  migration itself has always done.
- `LeadConvertView` is gone, and with it the only view in the app that
  required two permissions at once (`docs/PERMISSIONS.md`).
- The stale `auth_permission` rows for the two models are left alone.
  `remove_stale_contenttypes` would clear them, but it also offers to
  delete content types, and nothing reads them.

## Date

2026-10-11
