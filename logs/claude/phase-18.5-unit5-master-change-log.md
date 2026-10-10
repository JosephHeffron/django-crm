# Phase 18.5 unit 5 — the master change log

Item 9 of the twelve, and the largest unit.

## What already existed

An Owner-only log has sat at `/settings/activity/` since Phase 17.5,
with per-entry undo (`ActivityLogView`, `ActivityUndoView`,
`apps/crm/undo.py`). The work here was **coverage and filters**, not a
new page — worth knowing before reading the diff, because none of it
builds a log from scratch.

Four CRM models were recorded, from fifteen hand-rolled call sites in
`apps/crm/views.py`. The whole of `apps/jobs`, `apps/users`,
`apps/core` and `apps/messaging` recorded nothing. The live development
database held **five rows**.

## What changed

- `apps/crm/audit.py` (new) — `record`, `diff` and `log_for`, lifted
  out of `views.py` unchanged and aliased there, so none of the fifteen
  existing call sites moved and the extraction reads as a pure move.
  Plus `AuditedFormMixin`.
- Recorded now: Job, Quote, Invoice, Payment, Expense, ServiceType,
  Task and Property, on top of Company, Contact, Lead and Deal.
- `apps/crm/undo.py` — `UNDOABLE_MODELS`, an allow-list.
- `apps/core/views.py` — filters by person, record type, action and
  date range on `ActivityLogView`; `_logged_kinds()` offers only record
  types the table actually holds.
- `apps/core/navigation.py` — its own Owner-only sidebar entry, out of
  the gear menu. The URL is unchanged, so bookmarks still work.
- One migration: an index on `created_at`.
- Tests: 982 total, 35 new in `apps/core/tests/test_change_log.py`.

## Decisions

- **Explicit calls, not signals.** `docs/DATABASE_DESIGN.md` records
  that auditing only the app's own writes is "a deliberate scope limit,
  not an oversight". A `post_save` signal would be less code and would
  quietly widen that to seed runs, data migrations and
  management-command writes, filing them as somebody's edits. Keeping
  explicit calls is also why no ADR was needed: the decision stands,
  only its reach changed.
- **One index, not two.** The existing composite index leads with
  `content_type` and cannot serve "everything, newest first". A second
  index on `(user, -created_at)` for the person filter was considered
  and rejected: optimising a problem nobody has measured, at this size.
- **Activity stays out**, for the reason it always had: it is already
  an immutable append-only log of what happened.
- **Map pins stay out.** Coordinates written by the geocoder are
  machine output, and a log is only worth having if a person reads it.
- **Tasks are in**, reversing the documented reason that they were
  "lower-stakes, and their lifecycle is already visible on the record".
  That argument was about a per-record history page; it does not
  survive "who changed this?" being asked of the whole business.
- **The limit is stated on the page.** Changes made in the Django
  admin, in `manage.py shell` or by direct database writes still do not
  appear. Saying so beats implying completeness.

## Three defects of mine, each caught by a test

**1. The mixin silently did nothing** for jobs, estimates, invoices and
expenses. Those four form mixins define `form_valid` themselves and
return a redirect without calling `super()`, and a class's own method
always beats one it inherits — so declaring the mixin among their bases
never ran it. The job saved, the page redirected, and nothing was
recorded. It belongs on the concrete `CreateView`/`UpdateView`, which
define no `form_valid` of their own.

`test_the_audit_mixin_is_actually_reachable` now walks every view
declaring the mixin, inspects the method resolution order, and names
any class that shadows it without calling super. Mutation-checked
against the original wiring.

**2. Worse: the mixin treated a valid form as a completed save.** Those
same views also validate a line-item formset and re-render the page
when a line is wrong, leaving `self.object` unset. So a job submitted
with a bad quantity recorded a creation that never happened, and then
threw `AttributeError: 'NoneType' object has no attribute '_meta'` on
the way out — **a 500 on an ordinary typo in a price.** Three existing
tests caught it (`test_nothing_is_saved_when_a_line_is_wrong`, in
scheduling, estimates and finance), which is the only reason it did not
ship.

**3. Undo would have accepted the new records.** `undo.RESTORABLE`
includes `CharField`, so `Job.status` became undoable the moment jobs
reached the log — and undoing it writes the status while leaving
`completed_at` alone, which is exactly the silent miscounting
`apps/jobs/status.py` was built in unit 3 to prevent, arriving by
another door. A field-by-field deny-list would have held for today's
fields and failed the next time somebody added a text field to
`Invoice`, so it is an allow-list of models instead.

## Verification

$ `manage.py test` — 982 tests, OK (947 before).
$ `ruff` / `ruff format --check` — clean. One migration,
  `makemigrations --check` clean after it.
$ Mutation-checked: misplacing the mixin fails two tests, one of which
  names the shadowing class; removing the completed-save guard fails
  two; the undo allow-list is covered by four.
$ Browser pass under production settings — the log at two widths with
  five filter combinations each, zero policy violations, no sideways
  scroll. Then the behaviours, for real: a job status change appeared
  at the top reading "status: Scheduled → In progress"; undo refused it
  with a readable reason rather than a crash; the filters narrowed and
  kept their selection; the choices offered only `crm.company`,
  `crm.contact` and `jobs.job`, which is exactly what the table held;
  and a sales rep got 403.

  The verification change was reverted and its log rows removed, so the
  development database reads as it did.

## Git

Branch: `feature/master-change-log`
Commit: `37f4ecb`, with `main` merged in twice (not rebased — see the
unit 4 log for why). PR: #144, merged as `aa6accf`.

No automated review: the reviewer's weekly budget was spent on the seed
fix above, which earned it. Self-reviewed instead.

Note: #144's first CI run failed on `test_populates_every_area_with_
real_data`, which is **not** this unit. It is a time-of-day bug in the
demo seed, fixed separately in PR #145 and recorded in
`logs/claude/fix-seed-time-entries.md`.

## Next

Unit 6 — a Save button at the top of every form (item 12), the last of
the six.
