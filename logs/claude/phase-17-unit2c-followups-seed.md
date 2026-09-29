# PHASE 17 UNIT 2C: FOLLOW-UP GENERATOR + SEED_DEMO

Started: 2026-09-29
Ended: 2026-09-29

## Objective

Last of three PRs for Phase 17 unit 2: the repeat-service follow-up
engine and a `seed_demo` command that fills a development database with
realistic data, so unit 3's pages have real content.

## Files created / changed

- `apps/crm/followups.py` (new) — `due_follow_ups()` /
  `generate_follow_ups()` (a customer is due for a service when neither
  a completed job for it nor any contact touch has happened within the
  service's `followup_interval_months`), `add_months()` (month-end
  clamping), `record_completion()`.
- `apps/crm/management/commands/generate_followups.py` (new) —
  `--date` to simulate another day; Phase 19 schedules it daily.
- `apps/crm/views.py` — every completion path (create, edit form,
  one-click complete) goes through `_apply_task_completion()`: records
  `completed_by` and, on a transition *into* completed, calls
  `record_completion()`; reopening clears `completed_by`.
- `apps/crm/forms.py` — `TaskForm.clean_contact()`: clearing a
  follow-up's customer is a form error.
- `apps/core/management/commands/seed_demo.py` (new).
- Tests: `apps/crm/tests/test_followups.py` (15),
  `apps/core/tests/test_seed_demo.py` (6).

## Follow-up rules

- Due when `baseline + interval ≤ today`, where baseline = the later of
  the customer's last completed job for that service and their last
  Activity of any kind. Leads, inactive customers, and services without
  an interval (tree removal, "Other") never get follow-ups.
- **Idempotent twice over:** the partial unique constraint from unit 2a
  (one open follow-up per customer and service), and a follow-up created
  after the current baseline — open, completed, or *cancelled* —
  suppresses a new one until a newer job or touch. Cancelling therefore
  means "dismissed until something new happens", not "ask again
  tomorrow".
- **Completing one logs an Activity** (type follow-up), which moves the
  baseline — without that, the next run would recreate the task
  immediately. Re-saving an already-completed task doesn't log twice.
- Assigned to the contact's owner if active, else an Owner-group user,
  else a superuser; due date is the day it's generated. All aggregate
  queries, no per-contact queries.

## seed_demo

- 7 demo users (Owner, 2 Sales Reps, 4 Cleaners) with profiles; 60
  contacts (30% leads), properties, tags, 3 property-management
  companies; a year of completed jobs following each customer's usual
  services and their repeat intervals, with crews, hours, ratings, and
  invoices (mostly paid, some partial, some overdue); today's jobs with
  status by the clock; three weeks of scheduled work; quotes in every
  status with upcoming site visits; activities; follow-ups from the
  real generator; general tasks; 3 business plans with checklists;
  notes; 12 months of expenses; channel messages and 2 DMs with read
  markers leaving a few unread.
- **Every demo row belongs to a `demo_` user**; `--reset` deletes
  exactly those rows. Real users and records are never modified —
  follow-ups are generated for demo contacts only (`contact_ids`
  filter added to the generator for this). The one addition to real
  accounts: channel memberships, so the demo chat is readable.
- Refuses without `DEBUG` (unless `--force`) and refuses a second run
  without `--reset`. Deterministic (`--seed`). Password from
  `DEMO_USER_PASSWORD`, else generated with `secrets` and printed once.
  Phones in the reserved 555-01xx range, emails at example.com.

## Commands

$ `manage.py test` — 408 passed (388 + 20 new), later re-run for the
  seed tuning below.
$ `ruff` / `bandit` / `manage.py check` / `makemigrations --check` —
  clean after one bandit fix (below).
$ `seed_demo` against the **real dev database** (additive; the user's
  own contact and account were checked untouched afterward): 60
  contacts, 135 jobs, 29 quotes, 94 invoices, 46 messages. The first
  run yielded only 6 follow-ups, none overdue; tuned (see Errors) and
  re-run with `--reset`: 17 follow-ups (14 open, 5 overdue, 3
  completed), reset removed exactly the 7 demo users' data.

## Decisions

- The generator's due date is the day it runs, not the day the
  follow-up theoretically became due — on first install, years of
  history would otherwise surface as months-overdue tasks.
- Seeding's back-dated Activities use a queryset `update()`, which
  `Activity.save()`'s immutability guard allows by design
  (docs/DATABASE_DESIGN.md).

## Errors

- **Real bug found while writing tests:** `TaskForm` let a user clear a
  follow-up's customer; the DB check would then fail with a 500. Now a
  form error, regression-tested.
- **Self-review catch:** `seed_demo` first called the generator for
  *all* contacts, which would have created follow-ups on the user's own
  customers. Added the `contact_ids` filter.
- **bandit B311** on the seed's `random.Random` — a seeded PRNG for
  reproducible fake data, not security (the password uses `secrets`);
  annotated `# nosec B311` with the reason. CI's bandit fails on any
  finding, so this would have broken the build.
- **Thin demo:** dense recent seeded Activities (each a contact touch)
  reset most follow-up clocks, and the random completed/overdue roll
  missed all six. Made seeded history sparser and older, and the split
  deterministic.

## Git

Branch: `feature/follow-ups-and-seed`
Commit: pending
Merged to `main`: pending

## Next

Phase 17 unit 3 — every page (Dashboard, Financials, Calendar,
Contacts, Tasks hub, Profile, Messages) as functional skeletons on this
seeded data.
