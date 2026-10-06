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

$ `manage.py test` — 751 tests, OK (724 before, 27 new). No migrations.
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

## Review (PR #124)

Sourcery's budget was back and it reviewed properly: nine findings, of
which eight were real. All fixed, each with a test:

1. **(High) A custom range didn't reach the download.** The link carried
   only `range=custom`, dropping the dates, so Download CSV silently
   fell back to this month and exported different figures from the
   table above it.
2. **"Where customers come from" counted leads as customers.** It
   grouped every contact created in the period; a referral that never
   bought isn't where a customer came from.
3. **A report about a past period dropped people who had left.**
   Payroll lists who's on the books now, which is right for payroll and
   wrong for history. `people_who_worked()` adds anyone who clocked time
   in the period.
4. **An empty period downloaded as zero bytes.** The header is written
   from the first row, and there wasn't one. "No sales in March" is an
   answer; an empty file isn't.
5. **Shares and totals could disagree**, being two queries with a gap
   between them. Shares are now derived from the rows themselves, so
   they add to 100 by construction — which also fixed the same latent
   gap on the Profit page.
6. **Two follow-up columns were both labelled "Done"**, and the CSV keys
   on the label, so the percentage overwrote the count and the file lost
   a column. A test now asserts every report's labels are distinct.
7. **A test used "200 days ago" for a year-to-date check**, which lands
   in the previous year for half the year — it would have started
   failing in January.
8. **A test read a download's status and threw the body away**, so a
   zero-byte file passed it. It now checks every column heading is
   there.

Declined, with a reason: **totals in the CSV**. A spreadsheet sums a
column in one click, and a totals row inside the data breaks sorting and
filtering for everyone who opens it. The file is data; the page is the
summary.

## Git

Branch: `feature/restyle-reports` (PR #124)
Commits: `ef16c6a` (the step), review fixes to follow
Merged to `main`: pending

## Next

Step 10 — Settings: Account, Company Management with member access, the
activity log with undo, the Customize hub, and What's New.
