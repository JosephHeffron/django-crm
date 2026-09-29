# PHASE 17 UNIT 3A: DASHBOARD, CALENDAR, JOB/QUOTE PAGES, SERVICES

Started: 2026-09-29
Ended: 2026-09-29

## Objective

First of three PRs for Phase 17 unit 3 (every page as a functional
skeleton on the seeded data): the role-aware Dashboard, the Calendar,
job and quote detail pages, and the Owner's service catalog. 3b:
Contacts and the Tasks hub. 3c: Financials, Profile, Messages.

## Files created / changed

- `apps/jobs/views.py`, `urls.py`, `forms.py` (new) — `CalendarView`
  (all roles), `JobDetailView` (all roles, `jobs_for()` → 404 outside
  scope), `QuoteDetailView` (sales roles), `ServiceListView` /
  `ServiceUpdateView` (Owner; the edit also requires
  `jobs.change_servicetype`).
- `apps/jobs/calendar.py` (new) — day/week/month ranges (weeks start
  Monday; month = whole weeks) and events: jobs via `jobs_for()`,
  cancelled excluded; site visits (draft/sent quotes) for sales roles;
  crew filter for sales roles only.
- `apps/jobs/reports.py` (new) — `invoiced_revenue()` (sent invoices
  by issue date) and `outstanding()`; unit 3c's Financials builds on it.
- `apps/messaging/services.py` (new) — `unread_count()`.
- `apps/core/views.py` — `DashboardView` rewritten per role (Owner:
  revenue today/week, outstanding, all open quotes and follow-ups;
  Sales Rep: own quotes/follow-ups/visits, no money; Cleaner: own jobs
  today and coming up, jobs done and hours this week). Lead/Deal
  figures removed.
- `apps/core/navigation.py` — Calendar (all roles, bottom bar),
  Services (Owner); Leads and Deals out of the menu (URLs still work
  until Phase 18).
- `apps/core/templatetags/crm_format.py` (new) — `money`,
  `payment_status`, `status_label`.
- `apps/jobs/models.py` — `get_absolute_url()` on Job and Quote (no
  schema change).
- `apps/crm/followups.py` — completion Activity subject shortened to
  "Checked in about <service>" (the timeline already shows the type and
  contact; the old text repeated both).
- Templates: `core/index.html`; `jobs/calendar.html`,
  `job_detail.html`, `quote_detail.html`, `service_list.html`,
  `service_form.html`, partials `_event.html`, `_job_item.html`,
  `_status_badge.html`. CSS: agenda lists, calendar week/month grids,
  tone swatches — all class-based (CSP: no inline styles).
- Docs: `docs/PERMISSIONS.md` (roles table, page-access table,
  `ServiceUpdateView` row), `docs/USER_GUIDE.md` (Dashboard, Calendar
  and jobs, Services; Leads/Deals note).
- Tests: `apps/jobs/tests/test_calendar.py`, `test_views.py`,
  `apps/messaging/tests/test_services.py`, `apps/core/tests/test_format.py`;
  `test_dashboard.py` rewritten; navigation and permission tests
  updated for the new menu and dashboard.

## Decisions

- Revenue = sent invoices by issue date (drafts aren't billed, voids
  never owed). Recorded in `apps/jobs/reports.py` so Financials uses
  the same definition.
- Calendar events are listed in time order rather than sized by
  duration — sizing needs inline styles, which the CSP forbids.
- Month view on phones shows a per-day count instead of chips; one tap
  opens the day.
- Cleaners see a job's work but no prices, and the customer's name
  without a link to the (sales-only) contact page.

## Verification

$ `manage.py test` — 435 run; 2 older permission tests still asserted
  the old dashboard's text ("Pipeline by stage", "Your schedule") —
  updated to the new sections. Final run: 435 tests, OK.
$ `ruff check` / `ruff format --check` / `bandit` (CI flags) /
  `makemigrations --check` — clean.
$ `seed_demo --reset` on the dev database (picks up unit 2c's
  message-linking fix), then a Playwright pass (scratchpad venv, not a
  project dependency): demo Owner, Sales Rep, and Cleaner × 390×844 and
  1280×800 × 10 routes — expected status for every route (Cleaner: 404
  on another crew's job, 403 on quotes and services), no horizontal
  overflow, no console errors, no "$" on a Cleaner's job pages.
  Screenshots reviewed; two layout fixes came out of it (below).
$ The same pass under production settings (strict CSP) — zero
  violations, all checks passed.

## Errors

- Screenshot review: side-by-side dashboard cards were offset (the
  stacked-card margin applied inside the grid) and phone agenda rows
  were cramped by a third column for the status badge — fixed (badge
  moves under the time on phones).
- `pkill -f "runserver …"` matched its own shell and killed the
  command; stopped the servers by PID instead.
- The parallel test runner crashed on an unpicklable failure traceback;
  the serial run showed the two outdated assertions above.

## Review

Sourcery skipped PR #98 (weekly budget exhausted), so a self-review of
the full diff: role scoping (every query through `apps/jobs/access.py`;
crew filter ignored for cleaners; out-of-scope job → 404), cleaner
privacy (no prices, invoices, quote link, or sales rep), query counts
(crew prefetched; money figures are single aggregates), escaping, and
date windows (half-open, DST-safe). No defects. Two small items carried
to later units:

- The "Follow-ups due" card links to the pending task list, which also
  holds general tasks — 3b points it at the Tasks hub's follow-ups tab.
- `seed_demo` adds cleaners to #sales, so their unread count includes
  sales chatter — 3c decides channel membership per role.

## Git

Branch: `feature/pages-dashboard-calendar`
Commit: `9ffc3e7`
Merged to `main`: PR #98, merge commit `5a0c16a`

## Next

Unit 3b — Contacts (lead/customer status, last job / last contact,
properties, timeline) and the Tasks hub (follow-ups, quotes, business
plans, notes).
