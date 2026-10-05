# PHASE 17.5 STEP 4: DASHBOARD

Started: 2026-10-05
Ended: 2026-10-05

## Objective

The dashboard to the reference layout (ADR 0010): a greeting, a setup
checklist, overview cards with a revenue chart, today's jobs, quick
actions, and monthly goals — with the two models the design needs
(notifications and goals) built for real rather than faked.

## Files created / changed

- `apps/core/models.py` + migration `core/0002_goal_notification` —
  `Notification`: recipient (CASCADE), kind, title, body, `url` (a
  RegexValidator keeps it a path on this site, because it's rendered
  into an href), `event` (optional de-duplication key; partial unique on
  (recipient, event)), created_at, read_at (null = unread; index on
  (recipient, read_at)). `Goal`: metric (revenue / jobs / customers,
  unique), target (≥ 0), updated_at — the target in force, not a history.
- `apps/core/notifications.py` — `notify()` (the only way one is
  written; no signals, as with the audit log), `bell()`, `mark_read()`,
  `mark_all_read()`. A recipient of None is skipped, long text is
  trimmed to fit, and a duplicate `event` returns None instead of
  raising.
- `apps/core/goals.py` — this month against each target. Revenue reuses
  `apps/jobs/reports.invoiced_revenue`, so the dashboard and Financials
  can't disagree; over-achievement caps the bar at 100% and `is_met`
  says it was passed; a zero target never divides by zero.
- `apps/core/onboarding.py` — the checklist, every step answered from
  the database rather than stored as a flag, so a step un-ticks itself
  if the data goes away.
- `apps/core/views.py` — `DashboardView` rewritten (greeting, cards per
  role, checklist, goals, quick actions; revenue never reaches a
  non-Owner), plus `GoalsView` (Owner), `NotificationListView`,
  `NotificationReadView`, `NotificationReadAllView`,
  `OnboardingDismissView`. `_safe_next()` only ever returns to a path on
  this site.
- `apps/jobs/reports.py` — `sparkline()` (mini-chart geometry; returns
  None when every bucket is empty, so the card shows nothing rather than
  a row of zero-height bars) and `change()` (percent against an earlier
  figure, None when there's nothing to compare).
- Producers wired to the events that exist today: a task assigned to
  someone other than the person assigning it (`apps/crm/views.py`), and
  a follow-up the generator raises (`apps/crm/followups.py`, keyed so the
  daily run can't announce the same task twice). Team messages
  deliberately don't notify — the Inbox already counts them.
- `apps/core/navigation.py` — `QUICK_ACTIONS` (role-filtered, every tile
  a page that exists), "Monthly goals" in the gear menu, `first_name`
  for the greeting.
- Templates: `core/index.html` rewritten, `core/goals.html`,
  `core/notifications.html`, `core/_progress_bar.html` (an SVG bar — the
  CSP forbids turning a percentage into an inline width), the bell in
  `partials/_topbar.html`, `compact` on `partials/_empty_state.html`,
  and the new pieces added to the style guide.
- `static/css/base.css` — dashboard hero, overview card change/mini
  chart, progress bars, checklist, goals, action tiles, bell menu,
  notification rows, and `.grid-2.is-top`.
- `seed_demo` — goals pitched above what the month actually did, and
  notifications through the same `notify()` the app uses. `--reset`
  clears goals explicitly, since they belong to no user and wouldn't go
  with the demo accounts.
- Docs: USER_GUIDE (dashboard, checklist, goals, notifications),
  PERMISSIONS (three new rows), DATABASE_DESIGN (both models).
- Tests: `test_notifications.py` (22), `test_goals.py` (14),
  `test_onboarding.py` (9), plus 9 in `test_dashboard.py` and 2 seed
  assertions.

## Decisions

- **"Add New Job" isn't on this page yet.** The reference's main button
  creates a job, and nothing in the app creates one — that arrives with
  Scheduling in step 5. Rather than ship a dead button, the hero shows
  the two create actions the role actually has. Pulling job creation
  forward would have meant building most of step 5 here.
- **No "invite your team" or "schedule your first job" checklist step**,
  for the same reason: a box nobody can tick is worse than no box.
  Reviewing service prices isn't a step either, for the opposite reason
  — every install is seeded with a catalog and prices (jobs migration
  0002), so it would arrive already ticked. The checklist mentions it as
  a note instead.
- **The bell's list is rendered server-side**, so it opens without
  JavaScript (`<details>`). That costs one indexed query with a small
  LIMIT on every page; the alternative was a round trip to open it.

## Verification

$ `manage.py test` — 586 tests, OK (530 before, 56 new).
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright under production settings, 34 checks, zero CSP violations
  and no unexpected console errors: the greeting; four cards; the
  revenue mini chart; the goals card with its bars; the checklist with a
  step already ticked; every dashboard link and tile resolving; the bell
  listing and its unread badge clearing on "mark all read"; saving a
  goal and getting a whole number back; the checklist staying hidden
  once dismissed; a Sales Rep and a Cleaner seeing no revenue, no goals
  and no checklist but their own four cards and a bell, and both refused
  the goals page; phone light and dark without overflow.

## Errors

- Existing dashboard tests read `revenue_today` / `revenue_week`, which
  the month-first layout dropped. Rather than lose the figures, they're
  kept and shown on the revenue card's second line.
- The first checklist draft used "check your services and prices", which
  a seeded catalog makes permanently done — replaced (see Decisions).
- `TaskUpdateView` compared a User with the previous assignee's **id**,
  so it would have re-announced on every edit; it compares ids now.
- The checklist's empty "Your tasks" card stretched to the height of
  "Recent activity" beside it — `.grid-2.is-top`.
- The check script dismissed the checklist and then depended on it, and
  reused one browser context for every role, so the owner's session
  leaked into the "log in as a rep" step. Both fixed, plus a reset step
  so the check can be re-run.
- **A restart is needed after a template change under production
  settings** — Django's cached template loader held the old dashboard,
  which made a CSS fix look like it hadn't worked.
- The dev database's demo data stops at 2026-09-29, so the current month
  has no revenue and the chart and goal bars had nothing to draw. A
  single dated invoice was added for the check and removed afterwards,
  along with the check's goals and notifications; the owner's checklist
  flag was reset.

## Self-review (PR #114)

Sourcery's budget again allowed only a reviewer's guide (no findings),
so the diff was read by hand. Two defects found, both probed before
fixing and both now covered by regression tests:

1. **A notification's stored link was followed verbatim.** The field
   carries a validator saying it must be a path on this site, but
   `Model.objects.create()` doesn't run validators, so nothing actually
   enforced it — a probe stored `https://evil.example.com/` and the
   "open" button redirected straight there. Nothing writes such a link
   today (every producer uses `get_absolute_url()`), so this was a
   defence that existed only on paper. Now `notify()` drops anything
   that isn't a plain site path, and the redirect checks again, since
   that's the one place a bad value would do damage.
2. **The "next" check was hand-rolled** (`startswith("/")` and not
   `"//"`) where this codebase already uses Django's
   `url_has_allowed_host_and_scheme` for exactly this, in
   `TaskCompleteView`. The hand-rolled version let `/\evil.example.com`
   through; Django percent-encodes the backslash on the way out, so it
   stayed on this site and was not exploitable — but matching the
   existing helper removes the question entirely.

Also tidied: `add_months(month_first, 0)` was a no-op in the
previous-month comparison.

Re-verified after the fixes: 586 tests; and in the browser under
production settings, the dashboard, goals, and notifications pages in
**dark mode** at desktop width (the first run had only checked dark on a
phone) — correct dark surfaces and text, no overflow, the bell menu
opening, zero CSP violations. The check's goals and notifications were
removed from the dev database afterwards.

## Git

Branch: `feature/restyle-dashboard`
Commits: `bb6d056` (the dashboard), self-review fixes to follow
Merged to `main`: pending

## Next

Step 5 — Scheduling (with indicators) and Estimates, which is where job
creation and the dashboard's "Add New Job" button belong.
