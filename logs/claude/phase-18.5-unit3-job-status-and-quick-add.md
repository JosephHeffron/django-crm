# Phase 18.5 unit 3 — job status from the schedule, and quick-add

Items 6 and 7 of the twelve.

## The rule this unit is really about

`completed_at`, not `status`, is what every count of finished work
reads: the dashboard, the monthly goal, Financials, a crew member's
week, the customer timeline. A job whose status says Completed with no
date reads correctly on screen and is counted **nowhere**, and nothing
anywhere says so.

Until now there was one way to change a status — the full edit form —
and it stamped the date on its way past. Marking a job done from the
schedule is a second way, so the rule moved into `apps/jobs/status.py`
and both call it.

What makes that stick is the shape of the tests. They assert the
month's figure and the crew member's figure, not the field, because a
field assertion passes on a job that has quietly stopped being counted.
`test_the_edit_form_and_the_schedule_agree` is there for whoever adds a
third path.

## What changed

- `apps/jobs/status.py` (new) — `stamp_completion`, moved verbatim from
  `views.py`, and `apply_status`, returning the `(object, error)` shape
  the time clock already uses. `QUICK_STATUSES` is the three offered as
  buttons; Cancelled is deliberately not among them.
- `apps/jobs/views.py` — `JobStatusView`, POST only, permission
  `jobs.change_job`, scoped through `jobs_for` so another crew's job is
  a 404 rather than a 403.
- `apps/jobs/calendar.py` — `Event` carries `job_id`, so the day view
  can tell a job from a site visit.
- `_status_actions.html` (new), on the day schedule and the job page.
- `apps/crm/forms.py` — `PropertyForm`. `apps/crm/views.py` —
  `PropertyCreateView` / `PropertyUpdateView`. New routes, new
  template, and an "Add address" link on the customer page.
- `apps/core/redirects.py` (new) — `safe_next` and `with_params`, now
  shared with the hand-rolled check that was already in `core/views.py`.
- Tests: 924 total, 46 new, in `apps/jobs/tests/test_job_status.py` and
  `apps/crm/tests/test_property_views.py`.

## Decisions

- **Crews may mark their own jobs.** `users/0004` granted them
  `jobs.change_job` with the words "Crews update their own jobs
  (status, hours)", and marking a job done on a phone at the kerb is
  the point of the feature. Row scoping does the rest.
- **Cancelling is not a quick action.** It has consequences for
  invoicing, so it stays on the edit form where there is room to say
  so.
- **"New" is a button label, not a renamed status.** `Job.Status`
  keeps "Scheduled"; renaming the choice would ripple through badges,
  reports, seeds and tests for a cosmetic gain and carries no
  migration to signal it.
- **Week and month chips stay plain links.** Each is a single `<a>`
  wrapping the whole chip, and a form cannot nest inside an anchor.
  The day view is where you act. Said so in the partial rather than
  restructuring the chip.
- **The primary-address constraint is resolved by the form.** Django
  checks constraints during form validation, before any view code
  runs, so demoting the previous main address in `form_valid` was too
  late: it showed "Constraint is violated" to someone ticking a box
  that is meant to move. The form does it in its own `save()`, in one
  transaction, and skips that one check only when the box is actually
  ticked. The database still enforces it.
- **Leaving the job form loses what was typed.** No server-rendered fix
  that isn't overengineering (stashing a half-filled form in the
  session to make a link work). The help text says so, and `?date=` is
  carried through so a job begun from a calendar day returns to it.

## Three mistakes of my own, all in the testing

Worth writing down, because two of them would have left a false record.

1. **A mutation check silently did not apply.** The most important one —
   removing the date stamp — used a `str.replace` whose pattern no
   longer matched after formatting. A replace that matches nothing is a
   no-op, so the suite ran against unmodified code, reported OK, and I
   nearly recorded that the guard was unnecessary. Mutations are now
   asserted to have changed the file before the suite runs. Redone
   properly, it fails four tests.
2. **A test with a fallback that supplied the answer.** The crew-week
   check had `if hasattr(crew, "assignments_in") else [self.job.pk]`,
   so when the function didn't exist it asserted that the expected
   value was in a list containing the expected value. It calls
   `crew.performance` now.
3. **The browser check clicked Log out, twice.** A bare
   `form button[type=submit]` matches the sidebar's logout form first.
   That destroyed the session and the run reported the address
   round trip as landing on the sign-in page — a real-looking failure
   with no bug behind it. Third time in this project for that selector;
   it is now scoped every time.

## Verification

$ `manage.py test` — 924 tests, OK (878 before).
$ `ruff` / `ruff format --check` / `makemigrations --check` — clean. No
  migrations: no schema change, and both permissions already existed.
$ Mutation-checked: removing the date stamp fails four tests, including
  the month's count and the crew figure; dropping `updated_at` from
  `update_fields` fails one; accepting any status string fails two;
  removing the address demotion fails two; following `next` without
  checking the host fails three.
$ Browser pass under production settings — 5 pages × 2 roles × 2
  widths, zero policy violations, no sideways scroll. Then the two
  behaviours, done for real: marking job 773 complete from the day
  schedule changed its badge, withdrew Complete, offered New, and
  returned to the schedule; and saving a new address from the job form
  landed back on `/jobs/new/?service_property=391` with that address
  selected. The verification address and the job's status were put
  back afterwards.

## Git

Branch: `feature/job-status-and-quick-add`
Commit: `2134bf8`. PR: #137. Merged to `main` as `c76bbe9`.

## Next

Unit 4 — map search and lookup, and demo addresses that geocode (items
10 and 11).

The map is not broken: the seeded addresses are invented, so
`119 Pine Ln, Cedar Hills, NY 14526` has no real-world referent and
OpenStreetMap is right to refuse it. Two things to build, and one to be
careful about. `MapView` reads no query parameters at all, so the
search is new. Dropping a pin by hand already works server-side and is
tested, but nothing in the interface submits it, even though ADR 0011
promises it and the page tells the user they can. And the reseed must
use real streets and towns with arbitrary house numbers, never a
verified address of a real household: seeding must also still run
without touching the network.
