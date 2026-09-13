# PHASE 02: DATABASE SCHEMA REVIEW

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Senior-reviewer pass on the implemented schema (`apps/crm/models.py`)
against `docs/DATABASE_DESIGN.md`, per the roadmap and the original
brief's Prompt 2.3 ("Do not modify the schema unless I explicitly ask
you to after reviewing the report"). Review only — no schema changes.

## Files created / changed

- `docs/DATABASE_REVIEW.md` — new. HIGH/MEDIUM/LOW findings, comparison
  against the design doc, and a "what's solid" section.

## Commands

$ psql (via dbshell) → \d+ crm_deal, pg_constraint queries
Result: confirmed every FK in the schema (32 of them) is `NO ACTION`
(`confdeltype = 'a'`) at the raw PostgreSQL level, regardless of the
Django-declared `on_delete` — the ORM implements PROTECT/SET_NULL/CASCADE
in Python, not as native DB constraints.

$ DELETE FROM crm_company WHERE id = 1; (raw SQL, bypassing the ORM)
Result: FAILED with a foreign-key violation, on a Company whose linked
Activity should have CASCADE-deleted per the model definition — direct
empirical proof that on_delete guarantees only hold through the ORM.

$ (via manage.py shell) delete a Deal that a multi-tagged Activity also
  referenced via Company, leaving the Company untouched
Result: the Activity was destroyed entirely, even though it was still
tagged to a Company that still exists — direct empirical proof of the
Activity CASCADE finding, not a theoretical concern.

$ (via manage.py shell) Activity(activity_type="bogus", ...).full_clean()
  vs. .create(activity_type="bogus", ...)
Result: full_clean() correctly rejects it; .create() silently accepts
it — precisely confirms where the choice-enforcement gap actually sits
(admin/forms via full_clean, not .save()/.create(), not the DB).

$ (via manage.py shell) activity.subject = "..."; activity.save()
Result: succeeded with no error — confirms Activity immutability is not
enforced at the model layer, only by ActivityAdmin.has_change_permission
(which only blocks the admin UI specifically).

All scratch data (test Companies/Contacts/Deals/Activities/Users created
for these experiments) was deleted via the ORM afterward and verified
gone (`.count()` == 0 across every model) before committing.

## Tests

`python manage.py test` — 38 passed, unaffected (review touched no
application code).

## Decisions

- Did not change the schema based on this review — per the explicit
  instruction, findings are recorded for a future deliberate decision,
  not auto-applied.
- Recommended resolving the two HIGH findings (and finding #7) before
  Phase 4 (Activities/Tasks UI), not before Phase 3 (CRM interface) —
  Phase 3 doesn't touch Activity's CASCADE behavior or its mutation
  surface, so there's no reason to block it on this.

## Errors

- First draft's "switch to SET_NULL" alternative (for the Activity
  CASCADE finding) didn't account for the interaction with the existing
  `activity_has_related_object` CheckConstraint — automated review
  (`sourcery-ai`, PR #14) caught that SET_NULL-ing an Activity's last
  relation would violate that constraint and block the deletion, not
  quietly produce an orphaned row as the original wording implied.
  Fixed to state the dependency explicitly.
- First draft's "Comparison against the design doc" section claimed
  nothing contradicted the design doc, which glossed over a real,
  verifiable gap: Activity immutability is enforced only by the admin
  lock added in PR #11, not by the model layer. Automated review caught
  this too. Verified empirically (see Commands above) and added it as
  finding #7, then reworded the Comparison section to stop implying the
  matter was settled.

## Lessons learned

- Writing "X is fine because Y already documents the trade-off" is not
  the same as verifying Y's stated trade-off actually holds under test —
  worth treating every "already accepted" note in prior docs as a claim
  to spot-check, not a fact to inherit silently, especially in a review
  document whose whole purpose is catching exactly this kind of gap.
- Empirical verification (raw SQL delete, live shell experiments)
  surfaced two HIGH-severity findings that reading the model code alone
  would not have caught — `on_delete` behavior looks identical in
  `models.py` whether or not it's actually enforced by the database.
  Worth treating "does this behavior actually happen" as a question to
  test, not infer, whenever a schema review's stakes justify the time.

## Git

Branch: `feature/database-review` (merged, deleted)
Commits: `fc20808` (initial review), `5abc12e` (fixes from automated review)
Merged to `main`: `4d6f920` (squash merge, PR #14)

## Next

Two options, both consistent with the review's own recommendation:
1. Resolve the HIGH findings (#1, #2) and finding #7 now, before moving
   on — they all concern Activity's data integrity, which Phase 4
   (Activities/Tasks UI) will build directly on top of.
2. Proceed to Phase 3 (CRM interface: application shell, then
   Companies/Contacts CRUD) now, and resolve the Activity findings before
   Phase 4 specifically, as the review's own recommendation suggests.

Awaiting the user's direction on which to do next.
