# PHASE 17.5 STEP 5: SCHEDULING AND ESTIMATES

Started: 2026-10-05
Ended: 2026-10-05

## Objective

Scheduling and Estimates to the reference design (ADR 0010), with the
day indicators the design shows — and the forms that make both pages
real: booking and moving a job, and writing an estimate. This is also
where the dashboard's "New job" button becomes a working button, which
step 4 deliberately left out.

## Files created / changed

- `apps/jobs/forms.py` — `JobForm` (customer, address, service, start
  and end, status, crew, sold by, notes) and `QuoteForm` (customer,
  address, status, site visit, expiry, notes), plus one shared
  `line_formset()` so a job and an estimate edit their work the same
  way. Supporting pieces:
  - `ServiceSelect` puts each service's default price on its own
    `<option>`, so the page script can fill a blank price with no
    second request and no inline script (the CSP forbids one).
  - `PeopleChoiceField` / `PeopleMultipleChoiceField` show names, not
    usernames; `PropertyChoiceField` prefixes an address with its
    customer, because the list holds everyone's addresses.
  - The address is checked against the chosen customer in `clean()` —
    narrowing the list in the markup would need JavaScript, and this
    page works without it, so a mismatched address is refused rather
    than filed at the wrong house.
  - Line rows offer the services you still sell, plus whichever one the
    line already names, so retiring a service doesn't make old jobs
    uneditable.
- `apps/jobs/views.py` — `JobCreateView` / `JobUpdateView` and
  `QuoteCreateView` / `QuoteUpdateView` (Owner and Sales Rep; a Cleaner
  sees the schedule but doesn't set it). The job, its crew, and its
  lines are saved in one transaction. Editing is scoped like the detail
  page: out of scope is a 404, not a 403. `_stamp_status()` records when
  an estimate went out and when it was won, and never moves either date
  on a later edit — the expiry is counted from the day the customer
  first saw it.
- `apps/jobs/calendar.py` — `day_indicators()`: one dot per booking
  (capped at six, then "+n"), and counts of jobs, finished jobs, and
  site visits. A month cell only fits two events, so without this a
  busy day and a very busy day looked identical.
- Templates — `calendar.html` restyled as **Scheduling** (segmented view
  switcher, date chip, crew filter, "New job"), `_indicators.html`,
  `_day_summary.html`, `job_form.html`, `quote_form.html`,
  `_line_row.html`; `quote_list.html` is now an **Estimates** page with
  its own heading and actions rather than wearing the Tasks hub's
  "Tasks" heading, keeping the hub tabs through a new
  `crm/_hub_tabnav.html`; Edit buttons on the job and estimate pages.
- `static/js/lines.js` — add a row, and fill a blank price from the
  chosen service. Without it the form still works: one blank row is
  always offered and empty rows are ignored.
- `apps/core/navigation.py` — "New job" and "New estimate" in the Create
  menu and the dashboard's quick actions, so the dashboard hero's first
  button is now New job.
- Docs: USER_GUIDE (Scheduling, booking a job, Estimates), PERMISSIONS
  (two new rows).
- Tests: `test_scheduling.py` (24) and `test_estimates.py` (19) —
  access by role, booking, crew assignment, line ordering and totals,
  an end before the start, an address belonging to someone else,
  prefilling from a day or a customer, nothing saved when a line is
  wrong, moving a job, dropping a crew member without losing anyone
  else's hours, the indicators, estimate status dates, and the list
  page.

## Decisions

- **An accepted estimate still doesn't turn into a job in one click.**
  That conversion, with its own side effects, is Phase 18's. Step 5
  gives both halves honestly: write the estimate, then book the job.
- **No drag-to-reschedule.** Also Phase 18, and it needs a keyboard
  alternative. Moving a job is Edit, which works everywhere.

## Verification

$ `manage.py test` — 633 tests, OK (586 before, 47 new).
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean. No migrations: this step adds no
  fields.
$ Playwright under production settings, 34 checks, zero CSP violations:
  the month view with its dots, the segmented switcher and date chip;
  booking a job end to end (crew ticked, price filled in from the
  service, a second line added with the button) and landing on the job;
  moving it to another day and finding it there; an end before the
  start refused; the Estimates page and writing one that lands as Sent;
  a Sales Rep allowed and a Cleaner refused both forms; all three pages
  on a phone in light and dark without overflow. The jobs and estimates
  the check created were deleted afterwards.

## Errors

- The crew checkboxes, "Sold by", and the address list showed usernames
  and bare addresses (`demo_casey`, `12 Oak Ave`) — fixed with labelled
  choice fields, and a test for it.
- Day dots took `--accent`, which the service tone classes don't set, so
  every dot was blue; they use `--tone-accent` now, the same color as
  the chips below them.
- Line rows offered retired services (the formset's queryset wasn't
  narrowed like the job's own service field).
- A blank line row submitted with its quantity cleared fails validation
  rather than being ignored, because an empty quantity differs from the
  field's default of 1. The page never renders it that way, so this is
  only a trap for a hand-built POST; the test now posts what the page
  actually sends.
- Check-script faults, not app faults: "New job" also matches the hidden
  Create-menu entry, and `form button[type=submit]` matched the top
  bar's theme toggle before the form's own button.

## Self-review (PR #116)

Sourcery raised nothing and there were no review threads, so the diff
was read by hand. One real defect, confirmed by a probe before fixing:

1. **A job marked Completed counted nowhere.** Every count of finished
   work — the dashboard card, the monthly goal, Financials, a cleaner's
   week — is by `completed_at`, not by status. Nothing set it, because
   until this step there was no way to set a job's status from the app
   at all: a probe marked a job done and `summary()` still reported zero
   jobs completed that month. `_stamp_completion()` now records the
   date from the status, and clears it again if the job is re-opened.
   Four tests, including one that asserts the reports see it.
2. The same thinking applied to estimates: `accepted_at` now follows
   the status, so one accepted and later declined no longer shows a day
   it was won. `sent_at` still doesn't move — it's genuinely historical,
   and the expiry counts from it.

Re-verified in the browser under production settings: booking a job as
Completed and watching the dashboard's count go from 0 to 1, then
accepting an estimate and declining it and watching the won date go
away. The job and estimate were deleted from the dev database
afterwards.

## Git

Branch: `feature/restyle-scheduling` (PR #116)
Commits: `9a20133` (the step), self-review fix to follow
Merged to `main`: pending

## Next

Step 6 — Finance: Invoices, Payments, Expenses, Profit.
