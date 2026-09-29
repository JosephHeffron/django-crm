# PHASE 17 UNIT 2B: MESSAGING MODEL + PER-ROLE FIELD-SERVICE PERMISSIONS

Started: 2026-09-29
Ended: 2026-09-29

## Objective

Second of three PRs for Phase 17 unit 2 (split for Sourcery's
150,000-character limit — see `logs/claude/phase-17-unit2a-data-model.md`).
This unit: the team-messaging data model, shaped so customer SMS can be
added later without a rewrite, and model permissions per role for all
the field-service models. Written alongside 2a, held back when the unit
was split, and re-applied on top of the merged 2a.

## Files created / changed

- `apps/messaging/` (new app) — `Channel` (public / direct, with
  `customer_sms` reserved and a DB check that an SMS channel names its
  contact), `ChannelMembership` (per-user read marker; unique per
  channel), `Message` (authored by a user *or* a contact — DB check
  requires one; `transport` / `direction` / `external_id` /
  `delivery_status` for a future SMS provider; optional references to a
  job, contact, or quote); admin.
- Migrations: `messaging/0001_initial`, `messaging/0002_default_channels`
  (`#general`, `#crew`, `#sales` — reference data; its reverse deletes
  by primary key like the 2a migrations, so a channel holding messages
  blocks the reverse instead of silently discarding them),
  `users/0004_field_service_permissions` (additive, reversible).
- `config/settings/base.py` — `apps.messaging` installed.
- `docs/PERMISSIONS.md` — "Field-service permissions" table.
- Tests: `apps/messaging/tests/test_models.py` (default channels,
  author constraint, SMS-channel constraint, one membership per user,
  and that an inbound customer SMS is already representable);
  `FieldServicePermissionSeedTests` in `apps/jobs/tests/test_migrations.py`;
  `apps/crm/tests/test_permissions.py`'s role-seed tests changed from
  "exactly the old Staff set" to "still includes it", since the groups
  now hold more.

## Permission design

| | Owner | Sales Rep | Cleaner |
|---|---|---|---|
| Service catalog | add/change | — | — |
| Quotes, jobs, lines, crew | full | add/change (+ delete lines/crew) | change job, change own assignment |
| Photos | full | add | add |
| Invoices, payments, expenses | full | — | — |
| Notes / plans / properties / tags | full | add/change | add note |
| Messages | full | add | add |

Model permissions say *what kind* of write is possible; *which rows* is
enforced in views through `apps/jobs/access.py` (a Cleaner changes only
jobs they're assigned to). Invoices, payments, expenses, and the
catalog are Owner-only at both layers.

## Commands

$ Restored the held-back files onto `feature/field-service-messaging`
  from `main`. Files touched by both halves (`test_permissions.py`,
  `test_migrations.py`) had changed on `main` since the backup (2a's
  review fixes), so only 2b's hunks were re-applied rather than copying
  old files over new ones; `docs/PERMISSIONS.md` hadn't changed and was
  copied as-is. Fixed a stale comment reference to a test file that
  doesn't exist.

$ `manage.py check`, `makemigrations --check`, `migrate` (dev DB) —
  clean; `showmigrations` confirms messaging and users/0004 applied.

$ **Throwaway-database round trip** for final-2a + 2b (created on the
  local PostgreSQL server, dropped afterward): forward from empty
  (group permissions Owner 61 / Sales Rep 38 / Cleaner 7; 3 channels);
  folded a lead and a deal; posted a `#sales` message referencing the
  folded quote → reversing the fold was **refused by PostgreSQL's FK**
  (the message is later work); after removing the message: full reverse
  of the unit and re-forward both clean.

$ `ruff check` / `ruff format --check` / `bandit` / `pip-audit` —
  clean.

## Tests

`python manage.py test` — 388 passed (378 + 10 new, one from the self-review).

## Decisions

- **One membership row per user per channel holds the read marker**
  (`last_read_message`); unread count = messages after it. No per-
  message receipts — the team is small and polling (Phase 21) only
  needs a count.
- **SMS readiness is structural, not feature code:** nothing sends or
  receives texts yet, but a customer-authored inbound message on an SMS
  channel is already representable and tested.
- **Money and the catalog stay Owner-only** at the model-permission
  layer too, not just hidden in the UI.

## Review (PR #94) — self-review, Sourcery unavailable

Sourcery didn't review this PR: its free tier also has a **weekly
budget of 250,000 diff characters**, which unit 2's first PRs used up
(it resets ~6.5 days later). A deliberate self-review found two issues:

1. `Channel.contact` was `SET_NULL` while a DB check requires SMS
   channels to have a contact — deleting such a contact would have
   failed on the check constraint with a confusing error. Now
   `PROTECT`, which says what actually happens; regression-tested. (An
   ORM-level change only, so the unmerged migration was edited in place
   with no schema difference.)
2. `docs/PERMISSIONS.md` described view-level row rules ("own
   membership", "a Cleaner can change only jobs they're assigned to")
   as if enforced today; only the scoping helpers exist yet. Reworded to
   say which phase builds the views that must use them.

## Errors

None in the code. One process note: the unit split meant re-applying
held-back changes onto a `main` that had moved; diffing each shared file
against its backup first avoided overwriting 2a's merged review fixes.

## Lessons learned

- When a split leaves work parked while its base keeps changing, diff
  every shared file against the parked copy before restoring — a plain
  copy would have silently reverted merged fixes.

## Git

Branch: `feature/field-service-messaging`
Commit: `ab4528c` (implementation), `aa8e4dd` (self-review fixes — SMS
channel contact PROTECT, permission-doc wording)
Merged to `main`: `1be6dac` (PR #94 — CI green; Sourcery's weekly budget
exhausted so self-reviewed; its static scan re-raised the same SQLAlchemy
false positive as #92, explained and resolved)

## Next

Phase 17 unit 2c — follow-up generator (`apps/crm/followups.py` +
`generate_followups` command) and `seed_demo`.
