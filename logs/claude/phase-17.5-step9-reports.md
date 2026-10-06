# PHASE 17.5 STEP 9: REPORTS

Started: 2026-10-06
Ended: 2026-10-06

## Objective

The Reports page the restyle calls for (ADR 0010): a short catalogue of
questions the business actually asks, each answered over a period you
choose, as a table you can read and a file you can keep.

## Files created / changed

- `apps/jobs/reporting.py` — the catalogue. A report declares its
  columns and what each one holds (text, money, a count, a percentage,
  hours); the page renders from that and the CSV exports the same
  values, so a download and the screen can't drift apart. Eleven
  reports: revenue by service and by rep, profit over time, expenses by
  category, crew hours and pay, jobs by status and by service, new
  customers, where customers come from, estimate outcomes, follow-ups.
  The money ones reuse `apps/jobs/reports.py`, so a report and the
  Profit page can never disagree about what a month earned.
- `apps/jobs/views.py` — `ReportListView`, `ReportDetailView`,
  `ReportCsvView`. A money report asked for by a Sales Rep is a **404,
  not a 403**, so the catalogue doesn't leak what else exists.
- `apps/jobs/crew.py` — `payroll_people()`, so the crew-hours report and
  Payroll draw the same people.
- `apps/core/templatetags/crm_format.py` — a `lookup` filter, so a
  template can render rows against columns it was handed rather than
  ones written into the page.
- Templates: `report_list.html` (hub cards) and `report_detail.html`
  (period buttons, a custom range, the table with totals, a download).
- `apps/core/navigation.py` — Reports in the sidebar for sales roles.
- Docs: USER_GUIDE (what's there and who sees what), PERMISSIONS.
- Tests: `apps/jobs/tests/test_reports_page.py` (22) — every report in
  the catalogue opening and downloading, a rep's shorter catalogue and
  the 404 on a money report, a cleaner refused, the figures for six
  reports, totals covering money and counts but not percentages, the
  period following the buttons, and the file matching the page.

## Decisions

- **A money report is a 404 for a Sales Rep**, not a 403. The catalogue
  already tells them how many they aren't seeing; the URLs shouldn't
  confirm which.
- **Reports reuse the Profit definitions** rather than recomputing. Two
  places that count revenue differently is a bug waiting to be found by
  a customer.

## Verification

$ `manage.py test` — 746 tests, OK (724 before, 22 new). No migrations.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright under production settings, 19 checks, zero CSP violations:
  the catalogue; every report in it opening; a report with rows, period
  buttons and a totals row; the CSV carrying the same columns and no
  stray decimal places; a rep seeing 6 of 11 and told why, and a money
  report not found; a cleaner refused with no Reports link; phone light
  and dark.

## Errors

- The CSV exported `300.0000` where the page showed `300.00`: money is a
  sum of sums and arrives with more places than it's worth, and the page
  quantizes through its filters while the file didn't. The file now
  quantizes the same way — the same defect as step 6's payment prefill,
  in a different place.

## Git

Branch: `feature/restyle-reports`
Commit: pending
Merged to `main`: pending

## Next

Step 10 — Settings: Account, Company Management with member access, the
activity log with undo, the Customize hub, and What's New.
