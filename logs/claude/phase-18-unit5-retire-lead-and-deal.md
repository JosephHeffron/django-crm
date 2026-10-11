# PHASE 18 UNIT 5: RETIRE LEAD AND DEAL

Started: 2026-10-11
Ended: 2026-10-11

## Objective

Phase 17 folded every Lead into a Contact and every Deal into a Quote
(`jobs/0003_fold_leads_and_deals`, ADR 0009) and deliberately kept the
two models: "folding first and dropping in a later phase leaves a
verification window." This unit closes that window and removes the
code.

The window closed cleanly. Checked before starting: 0 leads, 0 deals,
0 tasks pointing at a deal, 0 activities pointing at a lead or a deal,
0 quotes carrying a legacy deal id that no longer resolved.

## The decision, and whose it was

`docs/ROADMAP.md` called the unit "removal of the retired Lead/Deal
models"; `CLAUDE.md`'s database-safety rules say never to DROP TABLE in
production. Those are not the same instruction, so the scope of
"removal" was the owner's call. They chose: **remove the code, keep the
tables.** ADR 0012 records it.

## Files created / changed

- `apps/crm/migrations/0011_retire_lead_and_deal.py` — **state-only.**
  `database_operations` is empty, `sqlmigrate` prints a no-op, and
  `migrate crm 0010` reverses the whole thing. Depends on
  `jobs/0003` (see Errors below).
- `apps/crm/models.py` — `Lead` and `Deal` gone, with `Task.deal`,
  `Activity.lead` and `Activity.deal`. `AuditLogEntry`'s docstring
  rewritten: it had still claimed only four CRM models are ever
  recorded, which Phase 18.5 unit 5 made false.
  `Contact.legacy_lead_id`'s comment no longer promises the field is
  dropped here — it stays for as long as `crm_lead` does.
- `apps/crm/views.py` — nine views removed, plus `_split_lead_name`
  and `_sync_deal_closed_at`. **One live 500 fixed** — see below.
- `apps/crm/urls.py` — nine routes replaced by two permanent redirects:
  `/leads/` → Customers, `/deals/` → Estimates. Both were in the menu
  for most of this project's life. Detail and add URLs now 404: there
  is no record to point at, so a redirect would be a lie.
- `apps/crm/forms.py`, `apps/crm/admin.py`, `apps/core/views.py`
  (`_search`), `apps/crm/undo.py` — all lead/deal references gone.
- Seven templates and four test files deleted; six templates cleaned.
- `apps/crm/tests/test_retired_lead_and_deal.py` (10) — new. Covers
  both halves of the decision, because each is easy to half-undo by
  accident: the code is gone and `undo` won't touch them; the tables
  and the three pointer columns are still in PostgreSQL; the migration
  runs no SQL (read off the migration, not its docstring); the fold is
  ordered before the retirement; the old list URLs redirect and the
  detail URLs 404.
- `apps/jobs/tests/test_migrations.py` — the nineteen Phase 17 fold
  tests now build `Lead` and `Deal` from the historical migration
  state, which is what the migration itself has always done (it only
  reaches models through `apps.get_model`). Their `TextChoices`
  classes are rebuilt from each field's own `choices`, so a test
  cannot name a value the column would reject. Foreign keys are passed
  as ids, because a historical model's FK insists on its own version of
  the related class while the factories use the live one.
- Docs: ADR 0012; `DATABASE_DESIGN.md` (Lead/Deal field tables moved
  under a new "Retired entities" heading — they now document tables
  that exist and that no code reads, worth keeping for anyone looking
  at the data directly); `PERMISSIONS.md`, `USER_GUIDE.md`,
  `ARCHITECTURE.md`, `DEVELOPER_GUIDE.md`.

## Errors, and what they cost

**Dropping the three empty pointer columns — drafted, implemented,
reversed.** `crm_task.deal_id`, `crm_activity.lead_id` and
`crm_activity.deal_id` hold nothing, and three dead foreign keys on two
busy tables are clutter. That is a real argument and it is why the
first draft dropped them. Two things made it wrong:

1. `jobs/0003`'s fold reads `crm_task.deal_id` (line 138) to re-point
   each task at its new quote. Dropping the column breaks the Phase 17
   rollback — the thing ADR 0009's verification window exists to
   preserve — and the nineteen tests that cover it, which can only
   exercise the fold against the live schema.
2. **It broke every build of a fresh database, and nothing would have
   told me except a clean build.** Nothing in the migration graph
   ordered `crm/0011` against `jobs/0003`, and Django's topological
   sort put the retirement *first*: `fold at 32, retire at 30`. With
   the drop in place the fold failed with "column deal_id does not
   exist" on any database built from scratch, the CI test database
   included. The dev database never showed it, because there
   `crm/0011` was simply the next migration to apply.

Three always-NULL columns are the cheaper price. The drop is gone,
`crm/0011` depends on `jobs/0003` anyway so the hazard cannot return,
and `MigrationOrderTests` asserts the ordering.

**A live 500 nobody reported.**
`ActivityCreateView.get_success_url` built the tuple
`(activity.company, activity.contact, activity.lead, activity.deal)`.
Python evaluates a tuple in full before the loop over it starts, so
this was not "only breaks when company and contact are both empty" —
it was every single logged activity, 500 on the redirect after a
successful save. Two sibling helpers in the same view had already been
cleaned; this one was missed. Mutation-checked: restoring the old line
fails three tests.

**`| tail` hid a test result.** The first full-suite run reported exit
code 0, which meant nothing: in a pipeline the exit status is `tail`'s,
not the test runner's, and `tail -15` had cut the summary off because
a test that runs `seed_demo` printed after it. Re-ran writing the whole
output to a file and grepping for the summary: 1000 tests, OK.

**Static files 404'd through the browser pass.** `runserver` with
`DEBUG=False` serves nothing from `static/`, so the first run reported
dozens of MIME-type console errors that were the harness, not the app.
`--insecure` fixed it. Worth remembering: a browser check that
reports problems it caused itself is as misleading as one that reports
none.

## Commands

```
python manage.py sqlmigrate crm 0011          # no-op, confirmed
python manage.py migrate crm                   # applied
python manage.py migrate crm 0010              # reversed, confirmed
python manage.py test                          # 1000 tests, OK (670s)
ruff check . && ruff format --check .           # clean
python manage.py makemigrations --check         # No changes detected
```

Browser pass under production settings (`csp_test_settings`,
`runserver --insecure`): 11 pages at 1280px and 390px, **0 CSP
violations, 0 console errors, no horizontal overflow**; both redirects
land; logging an activity works end to end through the redirect that
had been broken.

## What is deliberately still there

- `crm_lead` and `crm_deal`, with their rows, indexes and constraints.
- `crm_task.deal_id`, `crm_activity.lead_id`, `crm_activity.deal_id`.
- `Contact.legacy_lead_id` and `Quote.legacy_deal_id`, the pointers
  from a current record back to the row it was folded from.
- `crm_lead`'s own foreign keys to `crm_company` and `crm_contact`,
  now invisible to Django. Harmless — a foreign key only blocks a
  delete when a referencing row exists, `crm_lead` has none, and this
  app deactivates companies and contacts rather than deleting them —
  but it is a constraint no longer visible in the models, so worth
  knowing before writing raw SQL against either table. `on_delete`
  never held at the PostgreSQL level anyway (`DATABASE_REVIEW.md`
  finding #1).
- The stale `auth_permission` rows for the two models.
  `remove_stale_contenttypes` would clear them, but it also offers to
  delete content types, and nothing reads them.

## Remaining work

Phase 18 close-out: roadmap (units 2–5 — units 2, 3 and 4 merged in
earlier sessions as #148, #149 and #150 without roadmap entries or
phase logs), `PROJECT_STATE.md`, `CHANGELOG.md`, and phase logs for
units 2, 3 and 4.

## Commit

`a957914` — PR #151.
