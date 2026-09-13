# PRE-PHASE-4: RESOLVE DEFERRED PHASE 2 REVIEW FINDINGS

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Resolve `docs/DATABASE_REVIEW.md`'s two HIGH findings and MEDIUM
finding #7 — deferred by explicit user choice at the start of Phase 3,
to be revisited before Phase 4 (Activities, Tasks, audit history)
since Phase 4's Activity Timeline work is exactly what findings #2 and
#7 are about.

## Files created / changed

- `CLAUDE.md` — added an `on_delete`-is-ORM-only warning to the
  Database Safety section (finding #1).
- `apps/crm/models.py` — `Activity`'s four relation FKs changed
  `CASCADE` → `SET_NULL`; removed the `activity_has_related_object`
  `CheckConstraint`; added an `Activity.save()` override rejecting
  updates to existing rows.
- `apps/crm/migrations/0003_remove_activity_activity_has_related_object_and_more.py`.
- `apps/crm/admin.py` — updated `ActivityAdmin.has_change_permission`'s
  comment to reflect the new model-level guard existing alongside it.
- `docs/DATABASE_DESIGN.md` — Activity's field table and "Implementation
  notes" section updated to describe `SET_NULL` instead of `CASCADE`,
  the removed constraint, and immutability now being fully resolved.
- `docs/DATABASE_REVIEW.md` — added a "Status: RESOLVED" note to each
  of findings #1, #2, #7 describing the actual fix, plus an update to
  the closing Recommendation section.
- `apps/crm/tests/test_activity.py` — 4 existing tests updated (the
  removed-constraint test, the CASCADE test), 3 new tests (multi-tag
  survival, zero-relation degradation, immutability guard).
- `apps/crm/tests/test_task.py` — one stale comment fixed (referenced
  Activity's now-removed "at least one relation" DB rule).

## Commands

$ python manage.py makemigrations crm
Result: PASS — generated the constraint-removal + FK-behavior-change
migration in one step, as expected for changes to the same model.

$ python manage.py migrate crm
Result: PASS against real PostgreSQL.

$ (dbshell) SELECT conname, confdeltype FROM pg_constraint WHERE
  conrelid = 'crm_activity'::regclass
Result: confirmed `activity_has_related_object` is gone. Also
re-confirmed finding #1's own claim still holds after the change: all
Activity FK `confdeltype` values are still `'a'` (`NO ACTION`) — SET_NULL
is exactly as ORM-only as CASCADE and PROTECT were, not a special case.

$ (manage.py shell) reproduced finding #2's exact original scenario:
  Activity tagged to both a Company and a Deal, delete the Deal only
Result: PASS — company and activity both still exist, `activity.deal`
is now `None`, `activity.company` unchanged. This is the actual bug
fix, verified against the same reproduction that originally found it,
not a new/different test.

$ (manage.py shell) created an Activity with only a company relation,
  then deleted that company
Result: PASS — activity survives with all four relations now `None`,
confirming the "degrade to zero relations rather than being destroyed"
design choice actually happens.

$ (manage.py shell) reproduced finding #7's exact original scenario:
  `activity.subject = "Edited"; activity.save()`
Result: PASS — raises `ValueError` (previously succeeded silently);
DB value confirmed unchanged via `refresh_from_db()`.

$ python manage.py test
Result: PASS — 161 tests (4 updated, 3 new; up from 158 at the end of
Phase 3).

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after one formatting fix (the generated migration file);
no real findings.

## Tests

`python manage.py test` — 161 passed, 0 failures.

## Decisions

- Finding #2: chose `SET_NULL` (option b from the review) over
  restricting Activity to exactly one relation (option a). Multi-tagging
  an Activity to more than one CRM object is real product value for a
  future Activity Timeline (the same call showing up on both a
  Company's and a Deal's timeline), so the fix preserves that
  capability rather than removing it to make `CASCADE` "correct again."
- "At least one relation" for Activity moved from a DB `CheckConstraint`
  to an application/form-layer rule that will only apply at *creation*
  time (Phase 4's Activity create view) — deliberately a weaker
  guarantee than Deal's equivalent constraint (which holds forever),
  because Activity needs to be allowed to degrade toward zero relations
  as things it references get deleted, and Deal does not have that
  requirement.
- Finding #7's fix (`Activity.save()` raising on update) is scoped to
  `.save()` specifically, not a blanket lockdown of `.update()`/
  `.bulk_update()` — documented as an accepted, narrower residual gap
  rather than solved, since closing it fully would mean overriding
  `QuerySet`/`Manager` behavior for one model, disproportionate to the
  actual risk (no bulk-write code exists anywhere in this project yet).

## Errors

None this phase — the fixes matched the review's own analysis closely
enough that no rework was needed after the initial implementation, and
this PR's automated review found no further issues.

## Lessons learned

- Resolving deferred findings by reproducing each one's *original*
  failing reproduction (not a fresh, differently-shaped test) is a
  stronger form of verification than writing new tests from scratch —
  it directly proves the specific thing that was broken is now fixed,
  rather than proving something adjacent works.
- Confirming that two fixes landing in the same model (`SET_NULL` for
  deletion behavior, a `save()` guard for update behavior) don't
  interact badly is worth doing explicitly rather than assuming — here
  it required knowing that Django's deletion `Collector` uses bulk
  `QuerySet.update()` for `SET_NULL`, not per-instance `.save()`, which
  isn't obvious without checking.

## Git

Branch: `fix/activity-cascade-and-immutability` (merged, deleted)
Commit: `237fc8b`
Merged to `main`: `1ac9da0` (squash merge, PR #27)

## Next

Phase 4 — Activities, Tasks, audit history. The Activity model's schema
is now in the state Phase 4's Activity Timeline feature can safely be
built on top of, per this phase's own stated goal.
