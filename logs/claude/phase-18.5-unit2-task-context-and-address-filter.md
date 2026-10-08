# Phase 18.5 unit 2 — task context, and filtering by where people are

Items 4 and 8 of the twelve.

## What the reported problems turned out to be

- **"Auto-populate the customer's contact."** Adding a task from a
  customer's page already prefilled them, and had a test. What did not
  was the **Tasks hub** button — because the hub had no customer filter
  at all, so there was nothing for the button to carry. The button was
  not broken; the filter was missing.
- **"Include company addresses as a filter."** A Company has no address
  fields in the schema. Its geography is only reachable through its
  customers' service addresses, so a company matches when any of them
  has an address in that town.

## What changed

- `apps/crm/views.py` — `TaskListView` takes `?contact=`; the context
  carries `contact_id` so the header can pass it on. New
  `contacts_at()`, `address_filters()` and `towns_on_record()`, used by
  both list views. `TaskDetailView` gained `select_related` for the
  relations the page now shows. `TaskFormUserMixin.chosen_contact()`.
- `apps/crm/templates/crm/_hub_tabs.html` — the Add task link carries
  the customer when one is chosen. Shared by five pages, so it is
  conditional: only the Tasks list sets `contact_id`.
- `task_list.html`, `contact_list.html`, `company_list.html` — the new
  controls.
- `task_form.html`, `task_detail.html` — the customer's phone and email
  as `tel:` and `mailto:` links.
- Tests: 878 total, 33 new, including a new
  `apps/crm/tests/test_address_filter.py`.

## The trap, and the test that guards it

Filtering by joining `properties` multiplies rows: a customer with a
home and a rental in the same town matches twice. That corrupts the
rows shown **and** `paginator.count`, and on a short page it still
looks correct.

Both filters use a `pk__in` subquery, the discipline the tag filter and
`with_last_dates` already follow. Mutation-checked: swapping either for
a join fails four tests. The one that matters most asserts the number
the page **reports**, not the number of rows, because a row count alone
passes a wrong total.

## Decisions

- **A town and a postcode together mean one address matching both**,
  not either. A customer with a home in one town and a rental in
  another does not match a town from the first and a postcode from the
  second. Both readings are plausible; the code had already picked one
  and nothing said which, so there is now a test that does.
- **The customer's details on the form are server-rendered**, so
  changing the dropdown does not update them until the page is saved.
  Live updating needs JavaScript, and the page works without it — the
  same trade-off `JobForm` makes for its address list.
- **The task list's customer filter is a plain FK filter**, no subquery
  needed, because `Task.contact` is a direct foreign key. Noted in the
  code so the two filters' different shapes don't look inconsistent.

## No automated review this week

The reviewer reported its weekly budget spent — 250,000 diff characters
over seven days, resetting in about five days — so this unit got a
deliberate self-review instead. Two things came out of it:

- **A real defect.** `chosen_contact` read only the query string, so a
  create form that failed validation lost the customer's phone and
  email on the way back: pick a customer, leave the title blank, and
  the details vanished while the dropdown still held them. It now
  prefers what was submitted, then the saved record, then `?contact=`.
  Mutation-checked.
- **An undefined behaviour**, now written down: the town-and-postcode
  semantics above.

Also caught, before the self-review, in the course of mutation testing:
**one of my own tests passed for the wrong reason.** The check that the
Add task button carries the customer was matching the page's own
filter-preserving link `/tasks/?contact=<pk>`, so stripping the
parameter from the button left it green. It asserts the button's exact
href now. Worth recording as the third time in this phase that a test
had to be checked by breaking the code it guards.

The query-cost test compares two data sizes rather than pinning a
measured number, because a hardcoded count taken from a run of the code
passes whatever that code does.

## Verification

$ `manage.py test` — 878 tests, OK (845 before).
$ `ruff` / `ruff format --check` / `makemigrations --check` — clean. No
  migrations.
$ Browser pass under production settings — 10 pages × 2 roles × 2
  widths, zero policy violations, no sideways scroll. Measured rather
  than inferred: the Add task href carries `?contact=407` when narrowed
  and is plain when not; the phone link renders on a prefilled form;
  the task page has Customer, Phone and Email rows; customers in one
  town showed 10 rows against 10 reported, the two agreeing being the
  point.

## Git

Branch: `feature/task-context-and-address-filter`
Commits: `f0834c1` (the unit), `0d25930` (the self-review fixes).
PR: #135. Merged to `main` as `6dd09ef`.

## Next

Unit 3 — quick-add customer and address, and marking a job's status
from the schedule (items 6 and 7).

Two things to know before starting. There is **no address form anywhere
in the app**: no `PropertyForm`, no view, no URL, so addresses can only
be created through the Django admin — this unit builds the one the app
has been missing. And `_stamp_completion` is the **only** place
`completed_at` is set, while every count of finished work reads that
date rather than the status, so a new status path that skips it gives a
job that reads "Completed" on screen and is counted nowhere. One shared
helper, and a test asserting the month's completed count rather than
just the status.
