# PHASE 17 UNIT 3B: CONTACTS AND THE TASKS HUB

Started: 2026-09-29
Ended: 2026-09-29

## Objective

Second of three PRs for Phase 17 unit 3: Contacts rebuilt around
leads/customers and service history, and the Tasks hub (tasks,
follow-ups, quotes, business plans, notes). 3c: Financials, Profile,
Messages.

## Files created / changed

- `apps/crm/timeline.py` (new) — `contact_timeline()` merges
  activities, started jobs, quotes, notes, and messages referencing the
  contact (each source capped, then merged — exact top 50);
  `upcoming_jobs()`; `with_last_dates()` (last completed job / last
  Activity as subqueries).
- `apps/crm/hub.py` (new) — the Tasks hub tab bar with counts
  (follow-ups due, open quotes).
- `apps/crm/views.py` — `ContactListView` (stage tabs, tag filter,
  phone search, last job/contact columns, sort incl. "longest since
  contact"), `ContactDetailView` (stats, properties, upcoming jobs,
  tasks, timeline; legacy deals only if any), `FollowUpListView`
  (open/done/dismissed, only mine, mark done in place),
  `PlanListView` / `PlanDetailView` (checklist progress),
  `NoteListView` (general/contact/job, search); `TaskListView` gains
  the tab bar and a kind filter. `ContactUpdateView` audits tag changes
  by name, and `_diff_changed_fields` skips no-op changes.
- `apps/jobs/views.py` — `QuoteListView` (open by default, status
  filter, only mine; unknown status → open). `Quote.OPEN_STATUSES`
  added and used by the dashboard and calendar too.
- `apps/crm/forms.py` — `ContactForm` gains stage, lead source,
  preferred contact method, tags. Stage is optional: omitted, it keeps
  the contact's current stage (older posts keep working).
- `apps/core/views.py` + `search.html` — search matches contact phone
  and job/quote numbers (`J-1502`, `q1067`, `Q 1067`).
- Dashboard "Follow-ups due" card → the Follow-ups tab (carried from
  the 3a review).
- Templates: contact list/detail/form, task list, follow-up, quote,
  plan, plan detail, and note lists, `_hub_tabs.html`,
  `partials/_pagination.html` (Django's `{% querystring %}`, keeps
  every filter). CSS: tables that become cards on phones
  (`.stack-mobile`, labels from `data-label`), plan cards, checklist.
- Docs: `docs/USER_GUIDE.md` (Contacts, Tasks hub, search),
  `docs/PERMISSIONS.md` (page rows; message privacy on the timeline).
- Tests: `apps/crm/tests/test_contact_pages.py`, `test_tasks_hub.py`,
  search tests for phone and document numbers.

## Decisions

- **Timeline privacy:** messages appear only from channels the viewer
  can read (public or member) — a DM between two others never shows
  on a contact page. Tested both ways.
- **Hub as separate pages** sharing a tab bar, not one view with a
  `?tab=` switch: each keeps its own filters and pagination simply.
- **Service addresses** stay admin-only until the Phase 18 quote
  builder, where they're needed.
- Plans and notes are read-only here; editing lands in Phase 19.

## Verification

$ `manage.py test` — 457 tests, OK (22 net new test methods across
  contact pages, the hub, and search).
$ `ruff` / `ruff format --check` / `bandit` (CI flags) /
  `makemigrations --check` — clean.
$ Playwright on the seeded dev database: demo Owner and Sales Rep get
  200 and the Cleaner 403 on all 12 routes (contacts list and filters,
  a contact, its edit form, all five hub tabs, a plan, search by job
  number) at 390×844 and 1280×800; no horizontal overflow, no console
  errors. Screenshots reviewed. Same pass under production settings:
  zero CSP violations.

## Errors

- Five contact tests failed after adding stage to `ContactForm`
  (their posts omit it) — made it optional with a keep-current
  fallback rather than change what older posts mean.
- That surfaced a no-op audit entry (`status: customer → customer`) —
  the audit diff now skips unchanged values.
- Tags in the audit log would have read "crm.Tag.None" — recorded by
  name, captured before the save.
- Screenshot review: two "History" headings on a contact page — the
  new card is now "Timeline".
- Quote list with an unknown status showed every quote while the
  dropdown said "Open" — both now fall back to open.

## Review

Sourcery skipped PR #100 (weekly budget exhausted), so a self-review of
the full diff. Two defects, fixed in a follow-up commit on the PR, each
with a regression test that fails on the old code:

- A contact's tasks were ordered by status *alphabetically*
  (cancelled, completed, pending) — open tasks came last. Now pending
  first, then by due date.
- The audit diff's new no-op filter compared `str()` values, so moving
  a contact between two companies with the same name would not have
  been recorded. It compares the values themselves now.

Also checked: timeline privacy for the Owner (not a member of others'
DMs, so doesn't see them — consistent), the follow-up "Mark done"
`next` redirect (validated by `TaskCompleteView`), negative document
numbers in search (match nothing), and query counts on the list pages
(tags prefetched, dates as subqueries).

## Git

Branch: `feature/pages-contacts-tasks`
Commit: pending
Merged to `main`: pending

## Next

Unit 3c — Financials (Owner), Profile with stats, Messages (with
channel membership per role).
