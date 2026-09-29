# PHASE 17 UNIT 3C: FINANCIALS

Started: 2026-09-29
Ended: 2026-09-29

## Objective

Third PR of Phase 17 unit 3: the Owner's Financials page. The original
3c (Financials + Profile + Messages) was split so each PR stays under
Sourcery's 150k-character limit; Profile and Messages are unit 3d.

## Files created / changed

- `apps/jobs/reports.py` — rewritten around one set of definitions
  (module docstring): revenue = sent invoices by issue date; collected =
  payments by date received (not on voided invoices); outstanding =
  unpaid balance of sent invoices, aged as of today; net = revenue −
  expenses. Periods (`report_period`: day / week / month / year to date
  / custom up to five years, a bad custom range falls back to this
  month with a reason), `summary`, revenue by service and by sales rep
  ("Unassigned" when a job has none), expenses by category, aging
  buckets (not yet due, 1–30, 31–60, 61–90, 90+ days late) via
  conditional aggregation, oldest unpaid, and a trend (per day ≤ 31
  days, per week ≤ 184, else per month, empty buckets included). All
  database aggregates.
- `chart_bars()` — SVG geometry computed server-side (the CSP forbids
  inline styles; the template only copies numbers into attributes).
  Date labels sit in an HTML row under the chart because the stretched
  SVG would distort text.
- `apps/jobs/views.py` — `FinancialsView` (Owner only), `/financials/`.
- Nav: Financials (Owner only). Dashboard revenue and outstanding cards
  link to it.
- `apps/jobs/templates/jobs/financials.html`; CSS for the chart, share
  bars, aging list; `<progress>` now styled explicitly.
- Docs: `docs/USER_GUIDE.md` (Financials), `docs/PERMISSIONS.md`.
- Tests: `apps/jobs/tests/test_financials.py` — period presets and
  custom-range errors; exact totals, breakdowns, trend buckets and
  chart geometry against fixed fixtures; aging buckets; Owner-only
  access; every preset renders. Navigation test now derives the
  Owner-only set from `NAV_ITEMS`.

## Verification

$ `manage.py test` — 468 tests, OK (9 new in `test_financials.py`).
$ `ruff` / `ruff format --check` / `bandit` (CI flags) /
  `makemigrations --check` — clean.
$ Playwright on the seeded dev database: demo Owner 200 on six
  Financials variants (every preset, a 12-month custom range, an
  invalid range) plus the dashboard; Sales Rep and Cleaner 403; phone
  and desktop; no overflow, no console errors. Screenshots reviewed.
  Same pass under production settings: zero CSP violations.

## Errors

- Screenshot review found: the custom-range subtitle repeated the
  dates; chart date labels were squashed on phones (the SVG stretches
  to the card, distorting its text) — moved to an HTML row; a service
  bar with a pale tone rendered a dark, full-looking track (browsers
  pick the track color for `accent-color`) — progress bars now styled
  explicitly.
- Linked dashboard cards opened with `<a>` but still closed with
  `</div>` — fixed before any test ran.
- Oldest-unpaid links used `invoice.job.get_absolute_url` (one query
  per invoice) — now built from `job_id`.
- The seeded demo data shows a year-to-date loss (seeded expenses
  outweigh seeded invoices) — a demo-data matter, not a calculation
  one; totals are covered by exact-fixture tests.

## Git

Branch: `feature/financials`
Commit: pending
Merged to `main`: pending

## Next

Unit 3d — Profile with stats and Messages (channel membership per
role). That completes Phase 17.
