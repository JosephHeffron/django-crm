# PHASE 02: CRM MODELS IMPLEMENTATION

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Implement `apps/crm/models.py` (Company, Contact, Lead, Deal, Task,
Activity) from `docs/DATABASE_DESIGN.md`, with admin registration,
migrations, and model tests — the next concrete step after the design
phase, per the roadmap.

## Files created / changed

- `apps/crm/models.py` — six models, matching the design doc's fields,
  relationships, `on_delete` choices, and both `CheckConstraint`s.
- `apps/crm/admin.py` — all six registered; `ActivityAdmin` additionally
  disables change permission (added mid-phase, see Errors).
- `apps/crm/migrations/0001_initial.py`, `0002_deal_deal_probability_...py`.
- `apps/crm/tests/` (new package, replacing the stub `tests.py`) — 38
  tests across `test_{company,contact,lead,deal,task,activity}.py`.
- `.github/workflows/security.yml`, `Makefile` — excluded `tests/` and
  `migrations/` from Bandit's scan.
- `logs/system/2026-09-11-pg-hba-broaden-for-test-db.md` — retroactive
  entry for a PostgreSQL config change made mid-phase.

## Commands

$ python manage.py makemigrations crm
Result: PASS — generated 0001_initial cleanly, including both
CheckConstraints.

$ python manage.py migrate crm
Result: PASS against real local PostgreSQL.

$ python manage.py dbshell → \d+ crm_deal
Result: confirmed both CheckConstraints exist as real PostgreSQL CHECK
constraints, not just Django-side validation — checked rather than
assumed.

$ python manage.py test apps.crm
Result: initially FAILED — "permission denied to create database" (the
django_crm role lacked CREATEDB), then FAILED again with "Ident
authentication failed" (the existing pg_hba.conf rule from Phase 1 was
scoped to the `django_crm` database by name, and Django's test runner
uses a separate `test_django_crm` database it didn't match). Fixed by
granting CREATEDB and broadening the pg_hba.conf rule to `all` databases
for the `django_crm` role specifically (not opened for other roles).
Logged in logs/system/. PASS after the fix (34 tests, then 38 after the
probability-constraint addition).

$ ruff check . && ruff format --check .
Result: initially FAILED — one real line-length violation in
apps/crm/admin.py (fixed by wrapping the tuple), plus the generated
migration files needed `ruff format` run on them (cosmetic). PASS after.

$ bandit -r apps config
Result: initially FAILED — 8 low-severity B106 "hardcoded password"
findings, all in test fixture `User.objects.create_user(..., password="pw")`
calls. Not a real finding (dummy test-only credentials), so excluded
`tests/`/`migrations/` from Bandit's scan in both the Makefile and
security.yml rather than silencing with inline `#nosec` comments or
treating it as a true positive. PASS after.

$ pip-audit -r requirements.txt
Result: PASS, no known vulnerabilities.

## Tests

`python manage.py test` — 38 passed, 0 failures, run against real
PostgreSQL (not SQLite).

## Decisions

- Excluded `tests/`/`migrations/` from Bandit rather than adding
  per-line `#nosec` suppressions — the finding class (hardcoded
  passwords) is structurally never a real risk in either directory, so a
  path exclusion is clearer than repeated inline suppressions.
- Added `ActivityAdmin.has_change_permission` returning `False` — see
  Errors below, this was review-driven, not planned up front.

## Errors

- First test run failed because the `django_crm` PostgreSQL role lacked
  `CREATEDB`. Granted it (`ALTER ROLE django_crm CREATEDB`).
- Second test run failed with `Ident authentication failed` — the
  `pg_hba.conf` rule added in Phase 1 was scoped to the `django_crm`
  database by name, but Django's test runner connects to
  `test_django_crm`. Broadened the rule's database column from
  `django_crm` to `all` (still scoped to the `django_crm` role only).
- A stale `test_django_crm` database from the earlier failed attempts
  had to be dropped manually before a clean run would succeed.
- My own `test_activity_type_choices_are_enforced_in_admin_forms` test
  was itself buggy: the fake activity_type value I chose
  (`"not_a_real_type"`, 15 chars) exceeded the field's `max_length=10`,
  so PostgreSQL correctly rejected it for length — a different
  constraint than the one the test was meant to demonstrate (that
  choices aren't DB-enforced, only length is). Fixed by using a shorter
  fake value (`"bogus"`) and renaming the test to be accurate about what
  it actually shows.
- Automated review (`sourcery-ai`, PR #11) caught two real gaps after
  the initial implementation:
  1. `Deal.probability` was documented as 0-100 but nothing enforced the
     upper bound (`PositiveSmallIntegerField` only rejects negatives).
     Fixed with a second `CheckConstraint`
     (`deal_probability_between_0_and_100`), confirmed live in
     PostgreSQL, with 4 new tests.
  2. `Activity` is documented as immutable history, but the Django admin
     — currently the *only* way to edit any CRM record, since no custom
     views exist yet — allowed editing one after creation. Rather than
     leaving this purely as a documented future trade-off, disabled
     `has_change_permission` on `ActivityAdmin` to close the one
     concrete mutation path that exists today; the broader
     "no write path can violate this" guarantee is still the accepted
     application-layer trade-off recorded in
     `docs/DATABASE_DESIGN.md`.

## Lessons learned

- A `pg_hba.conf` rule scoped by database name breaks the moment
  Django's test runner needs a differently-named test database — for a
  single-role dev setup, scoping by role only (not role+database) avoids
  this class of surprise. Worth remembering before repeating the
  database-scoped pattern elsewhere.
- Writing a test to demonstrate "the DB doesn't enforce X" is easy to
  get subtly wrong by accidentally tripping a *different* constraint
  (here, field length) — worth double-checking that a "should be
  allowed" test actually exercises only the constraint under test.
- Automated review continues to catch things a single self-review pass
  missed, on both docs-only and code PRs — same lesson as Phase 2's
  design-doc review, now confirmed twice.

## Git

Branch: `feature/crm-models` (merged, deleted)
Commits: `93be876` (initial models/migrations/tests),
`d211310` (probability constraint + Activity admin lock, from review)
Merged to `main`: `a11444c` (squash merge, PR #11)

## Next

`docs/DATABASE_REVIEW.md` — a senior-reviewer pass on the implemented
schema against `docs/DATABASE_DESIGN.md`, per the roadmap, before moving
on to the CRM interface (Phase 3). Then: Companies/Contacts CRUD views.
