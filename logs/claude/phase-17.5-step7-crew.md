# PHASE 17.5 STEP 7: CREW

Started: 2026-10-05
Ended: 2026-10-05

## Objective

The Crew side of the reference design (ADR 0010): a time clock, the
crew's week, payroll, and performance — with the two things the design
needs that the CRM had no record of, pay rates and working days.

## Files created / changed

- `apps/jobs/models.py` + migration `jobs/0004_timeentry` —
  `TimeEntry`: user (PROTECT), job? (SET_NULL), started_at, ended_at?
  (null while running), notes. Constraints: it ends after it starts, and
  a partial unique on user where `ended_at` is null, so **one clock runs
  per person** — clocking in twice is a mistake, not two jobs at once.
  `hours` is None while running, because an unfinished stretch has no
  length yet.
- `apps/users/models.py` + migration
  `users/0007_userprofile_hourly_rate_userprofile_working_days` —
  `hourly_rate?` and `working_days` (weekday digits, Monday 0, so
  "01234" is a weekday crew; text rather than seven booleans, so
  changing a day is editing a string, not a migration), with
  `works_on()`, which doesn't claim someone *doesn't* work a day when no
  days are set.
- `apps/jobs/crew.py` — `clock_in()` / `clock_out()` (returning an error
  rather than raising: clocking in twice is an ordinary phone mistake),
  `entries_for()`, `hours_in_period()` (one database aggregate over the
  spans, not a loop), `payroll()`, `payroll_total()`, `performance()`.
  **Clocking out of a job tops up that person's assignment hours**, so a
  job's hours and the clock can't tell two different stories; clocking
  onto a job you weren't assigned to assigns you, because you did the
  work.
- `apps/jobs/views.py` — `TimeClockView` (every role; you only ever see
  your own), `AssignmentsView` (Owner and Sales Reps), `PayrollView` and
  `PerformanceView` (Owner).
- `apps/users/` — `CrewPayForm`; `TeamMemberView` takes a POST so the
  Owner sets someone's rate and working days from their page; the team
  list shows both.
- Templates: `time_clock.html`, `assignments.html`, `payroll.html`,
  `performance.html`, plus the pay section on a teammate's profile.
- `apps/core/navigation.py` — the Crew group becomes Time clock,
  Assignments, Team, Payroll, Performance, filtered by role; the
  dashboard's quick actions gain the clock.
- `seed_demo` — crew get a rate and weekday hours, and the last
  fortnight's completed jobs get clocked time, so Payroll and the clock
  open on a real week rather than an empty one. `--reset` clears the
  entries with their user.
- Docs: USER_GUIDE (Time clock, Assignments, Payroll, Performance, pay),
  PERMISSIONS (six new rows), DATABASE_DESIGN (TimeEntry, the profile
  fields).
- Tests: `apps/jobs/tests/test_crew.py` (27) — the clock for every role
  and nobody else's time, hours landing on the job and adding to what's
  there, time with no job still recorded, an end before the start,
  payroll arithmetic, a missing rate listed and flagged, time outside
  the period and a running clock not paid, only the Owner setting a
  rate, the crew's week, unassigned jobs, a job on someone's day off,
  and performance figures.

## Decisions

- **Payroll pays for clocked time.** Hours typed onto a job aren't paid
  unless they were clocked; the page says so. Two sources of truth for
  pay would be one too many.
- **A missing rate is reported, never guessed.** The person is listed
  with their hours and a warning naming them, because quietly paying
  them nothing is worse than saying the rate is missing.
- **Everyone has a clock**, not just cleaners — the Owner and Sales Reps
  do paid work too, and Payroll covers them.

## Verification

$ `manage.py test` — 693 tests, OK (666 before, 27 new).
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean. Both migrations reverse cleanly.
$ Playwright under production settings, 36 checks, zero CSP violations:
  a cleaner clocking in on a phone against a real job and clocking out
  again, with the week's entries listed and no overflow; the crew's week
  with a card each; Payroll listing people and saying it pays for
  clocked time; Performance; the Owner setting a rate and working days
  and getting them back; a Sales Rep planning the week but refused
  payroll, performance and the team list; a Cleaner refused all three;
  the clock, assignments and payroll in dark mode. Every time entry, the
  assignment it created, and the rates set during the check were removed
  afterwards.

## Errors

- A test asserted a rate was absent after a refused POST when its own
  setup had already set one; it now asserts the rate is *unchanged*.
- The check script read a table header case-sensitively, which CSS
  uppercases.
- **The check set a pay rate on the real superuser account**, because it
  clicked the first row of the team list and that account sorts first.
  Reverted, and the script now picks a demo account explicitly. Worth
  remembering for any check that writes through a list page.

## Git

Branch: `feature/restyle-crew`
Commit: pending
Merged to `main`: pending

## Next

Step 8 — Map on OpenStreetMap (ADR 0011), with Leaflet vendored and
Nominatim for geocoding.
