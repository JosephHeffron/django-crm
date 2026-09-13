# PHASE 02: CRM DATABASE DESIGN

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Design the CRM's data model (Company, Contact, Lead, Deal, Task, Activity)
in `docs/DATABASE_DESIGN.md` before writing any models, per the roadmap
and the original brief's explicit instruction not to jump straight to
model code.

## Files created / changed

- `docs/DATABASE_DESIGN.md` — new. Entity descriptions, textual ERD,
  per-model field tables, constraints, indexing decisions, lifecycle
  behavior, decisions that intentionally avoid overengineering, and
  decisions flagged for review before implementation.

## Commands

$ python3 -c "... CheckConstraint(condition=Q(...) | Q(...))..."
Result: PASS — confirmed the "at least one of two nullable FKs" pattern
actually constructs under the installed Django 6.1.1 (which uses
`condition=`, not the older `check=` kwarg) before committing to it in
the design doc.

## Tests

Docs-only phase; no CRM model code or model tests exist yet, and this
change didn't touch the existing bootstrap code. `manage.py
check`/`test` unaffected (not re-run — no code changed).

## Decisions

- Followed the original entity-relationship diagram exactly (User→
  Activities/Tasks; Company→Contacts/Deals/Activities; Contact→
  Activities/Tasks/Deals; Lead→Activities; Deal→Activities/Tasks) rather
  than inventing additional relationships (e.g. no direct Task↔Company or
  Task↔Lead FK).
- No custom User/Profile model — CRM models reference
  `settings.AUTH_USER_MODEL` directly; roles come later via Django
  Groups/Permissions.
- "Notes" is an Activity type, not a fifth model.
- `owner`/`created_by`/`assigned_to` → User FKs use `PROTECT`.
- Activity's four relation FKs (company/contact/lead/deal) use `CASCADE`
  — an activity has no independent meaning once its subject is gone.
- Deal's `company`/`contact` FKs use `PROTECT` (not `SET_NULL`) because
  Deal also has an "at least one of company/contact" `CheckConstraint` —
  see Errors below, this was a real bug caught in review.
- Lifecycle invariants (Lead-conversion fields, Deal/Task timestamps,
  Activity immutability) are explicitly application-layer-only, not
  DB-enforced — documented as an accepted trade-off, not left implicit.

## Errors

- First draft of the design had `Deal.company`/`Deal.contact` as
  `SET_NULL` while also requiring (via `CheckConstraint`) that at least
  one of them be non-null. An automated review (`sourcery-ai` bot, PR #9)
  correctly caught that this combination means deleting a Deal's *only*
  related Company/Contact would null out its last remaining relation and
  violate the constraint, making the delete fail with an `IntegrityError`
  — directly contradicting the doc's own claim that Deals "survive"
  company/contact deletion. Fixed by changing both FKs to `PROTECT`, in
  commit 75ab62e.
- Same review also caught a direct self-contradiction: prose describing
  `CASCADE`'s rationale claimed "Company/Contact/Lead/Deal use `SET_NULL`
  for their own owner/creator," while the field tables on the same page
  specified `PROTECT`. This was a plain copy-paste inconsistency, not a
  design ambiguity. Fixed in the same commit.
- Three more review comments (Lead-conversion field consistency,
  Deal/Task timestamp consistency, Activity immutability) correctly
  observed that these invariants weren't DB-enforced. Resolved by making
  that trade-off explicit in the doc rather than changing the schema —
  a solo-maintainer app doesn't yet need DB triggers or extra
  constraints for invariants only the maintainer's own code writes to.

## Lessons learned

- An external automated reviewer (already installed on the GitHub
  account, not something this session added) caught two genuine defects
  in a documentation-only PR that self-review during writing had missed
  — worth treating its findings as seriously as a second engineer's, not
  dismissing them because the change was "just docs."
- Branch-protection required-status-check names must match the actual
  CI *job* names (`test`, `dependency-audit`), not the workflow *file*
  names (`ci`, `security`) — this tripped merges earlier in the
  governance phase and is worth remembering for any future workflow
  file.
- Verifying a constraint pattern actually constructs in the installed
  library version (rather than assuming API familiarity from training
  data) caught that Django 6.1 uses `condition=` rather than deprecated
  `check=` on `CheckConstraint` — cheap to check, expensive to get wrong
  in a later implementation phase.

## Git

Branch: `feature/database-design` (merged, deleted)
Commits: `762dae6` (initial design), `75ab62e` (fixes from review)
Merged to `main`: `66820dd` (squash merge, PR #9)

## Next

Phase 2 continues: implement the actual Django models from this design
(`apps/crm/models.py`), migrations, admin registration, and model tests —
per the roadmap, this is a distinct next step, not part of this same
change.
