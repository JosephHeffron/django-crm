# PHASE 17 UNIT 2A: FIELD-SERVICE DATA MODEL + LEAD/DEAL FOLD

Started: 2026-09-29
Ended: 2026-09-29

## Objective

First half of Phase 17 unit 2. Unit 2 was split into three PRs to stay
under Sourcery's 150,000-character review limit (it skipped unit 1's PR
#90 entirely): **2a** (this) — contact extensions, the `apps.jobs`
domain, the Lead/Deal fold, Pillow; **2b** — `apps.messaging` and the
per-role field-service permissions; **2c** — follow-up generator and
`seed_demo`. Open plan questions were answered with the stated defaults
(reps schedule from accepted quotes, Owner reschedules anything,
Cleaners update their own jobs and log hours, "Exterior CRM" branding).

## Files created / changed

- `apps/crm/models.py` — `Contact` gains `status` (lead/customer),
  `lead_source`, `preferred_contact_method`, `tags` (new `Tag` model),
  `legacy_lead_id`; new `Property` (one primary per contact), `Note`,
  `BusinessPlan`, `PlanChecklistItem`; `Task` gains `kind`
  (general/follow_up), `service_type` / `quote` / `job` links and
  `completed_by`, with a check (follow-ups need contact + service) and a
  partial unique constraint (one open follow-up per contact/service);
  `Activity` gains `text` / `visit` / `follow_up` types.
- `apps/jobs/` (new app) — `ServiceType`, `Quote` + `QuoteLineItem`,
  `Job` + `JobLineItem` + `JobAssignment` (crew), `Photo`, `Invoice` +
  `InvoiceLineItem` + `Payment`, `Expense`; `with_totals()` /
  `with_balances()` querysets; `access.py` row-level scoping
  (`jobs_for`, `contacts_for`, `quotes_for`, `invoices_for`); admin.
- Migrations: `crm/0006`, `jobs/0001`, `crm/0007` (Django split the
  crm ↔ jobs cycle; renamed from auto-generated names),
  `jobs/0002_seed_service_catalog` (the ten default services with
  follow-up intervals — reference data, so a migration rather than demo
  data), `jobs/0003_fold_leads_and_deals`,
  `users/0003_userprofile_photo`.
- `apps/users/models.py` — `UserProfile.photo` (random filename under
  `media/private/avatars/`).
- `apps/crm/admin.py` — new models registered; Lead/Deal admin made
  read-only (folded, dropped in Phase 18).
- `requirements.txt` — `Pillow==12.3.0`.
- `docs/DATABASE_DESIGN.md` — reconciled with what was built, plus a
  "Changes from the unit 1 design" list.
- Tests: `apps/jobs/tests/` — `_factories.py`, `test_models.py`
  (totals, balances, payment status, every DB constraint, upload
  naming), `test_access.py` (row-level scoping per role),
  `test_migrations.py` (fold forward/reverse on real data).

## Commands

$ `pip index versions Pillow` → 12.3.0; `pip-audit` clean; confirmed a
  native `manylinux_2_28_aarch64` wheel exists (the first check used an
  outdated `manylinux2014` tag and found nothing — newer wheels use the
  PEP 600 tags), so nothing compiles on the Pi.

$ `manage.py makemigrations` — first attempt failed at import:
  `TypeError: 'ForeignKey' object is not callable`. A model field named
  `property` shadows Python's `@property` decorator later in the same
  class body; renamed to `service_property`.

$ `manage.py migrate` (dev DB) — all applied; 10 services seeded.

$ **Reverse-migration verification on a throwaway database**
  (`crm_migration_check`, created on the local PostgreSQL server and
  dropped afterward; the real dev DB was never touched):
  1. Forward from empty — ok. Seeded a lead, a company-only won deal,
     and a task on the deal.
  2. Unapply only the fold, re-apply — ok.
  3. **Full reverse of the unit failed**: `ValueError: Cannot query
     "Quote object (1)": Must be "Quote" instance` inside `unfold()`.
     A known Django pitfall: in a multi-app backwards plan, some
     historical model classes are re-rendered and others aren't, so the
     deletion collector compares two different in-memory `Quote`
     classes. Fixed by not using the collector in reverse functions:
     clear known children explicitly, then delete parents by primary key
     (`DELETE … WHERE id = ANY(%s)`), letting PostgreSQL's FK constraints
     refuse anything still referenced. Applied the same pattern
     proactively to `jobs/0002` and (in 2b) `messaging/0002`.
  4. Re-ran from a fresh throwaway DB: forward → fold → full reverse
     (no leftover tables; folded contacts including the placeholder
     removed; original leads/deals intact; role permissions back to the
     unit 1 state) → re-forward — all ok.
  5. Created a job for a folded contact, then tried to reverse the fold:
     PostgreSQL refused with a FK violation and rolled back, nothing
     lost — the intended behavior.

$ `ruff check` / `ruff format --check` / `bandit` / `pip-audit` /
  `check` / `makemigrations --check` / `check --deploy` — clean.

## Tests

`python manage.py test` — 370 passed (333 before + 37 new).

## Decisions

- **Contact.status is lead/customer only** — deactivation already lives
  on `is_active`; an "inactive" status would be a second field able to
  disagree with it.
- **Document numbers derived from pk** (`Q-1001`, `J-1001`,
  `INV-1001`), not stored — no allocation race.
- **Invoice payment state derived**, only draft/sent/void stored.
- **Totals via `Subquery`, not JOIN**, so line-item and payment sums on
  one queryset can't multiply each other (tested with 2 lines × 2
  payments); scoping helpers use `pk__in` for the same reason.
- **Fold choices:** unqualified lead → inactive contact; lead company
  name links to an existing Company when one matches, else goes into
  notes; company-only deal → the company's first contact, else a
  placeholder contact named after the company; deal stage → quote
  status; tasks move from the deal to the quote; won deal makes its
  contact a customer; original creation dates preserved.
- **Uploaded files never keep the uploader's filename** (UUID/random
  names under `media/private/`) — filenames like `smith_house.jpg`
  leak customer details.

## Errors

- `@property` shadowed by a `property` field — renamed (above).
- Backwards-migration collector failure — fixed and regression-tested
  (above).
- A test for "reverse refuses when depended on" first passed for the
  wrong reason: Django's PostgreSQL FKs are `DEFERRABLE INITIALLY
  DEFERRED`, so inside a test's never-committed transaction the
  violation only surfaced at teardown. The test now runs `SET
  CONSTRAINTS ALL IMMEDIATE`, mirroring the commit-time check a real
  migration gets.

## Lessons learned

- Forward-only migration tests (what a fresh test DB gives you) miss
  entire classes of bugs; actually reversing a unit's migrations on
  real data found one here that no unit test would have.
- Deferred FK constraints change *when* integrity errors surface —
  tests of constraint behavior have to account for that.

## Git

Branch: `feature/field-service-models`
Commit: pending
Merged to `main`: pending

## Next

Phase 17 unit 2b — `apps.messaging` (channels, memberships, messages;
SMS-ready) and per-role permissions for the field-service models.
