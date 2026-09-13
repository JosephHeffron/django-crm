# PHASE 04: TASKS (UNIT 2)

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Second unit of Phase 4, per Prompt 4.2: Task list/detail/create/edit
views, a completion workflow, and "my tasks"/"overdue tasks" views,
replacing the `crm:task_list` placeholder.

## Files created / changed

- `apps/crm/models.py` — `Task.is_overdue` property (pending + past due
  date), `Task.get_absolute_url()`.
- `apps/crm/forms.py` — `TaskForm` (plain `ModelForm`; no custom
  `clean()` needed, since Task has no "at least one relation" DB rule
  unlike Deal/Activity).
- `apps/crm/views.py` — `_sync_task_completed_at()` helper (mirrors
  `_sync_deal_closed_at`); `TaskListView` (status/priority filters,
  `?mine=1`, `?overdue=1`, pagination); `TaskDetailView`;
  `TaskCreateView` (defaults `assigned_to` to the current user, prefills
  `contact`/`deal` from query params); `TaskUpdateView`;
  `TaskCompleteView` (POST-only one-click completion, safe `next`
  redirect via `url_has_allowed_host_and_scheme`).
- `apps/crm/urls.py` — real routes for
  `task_{list,create,detail,update,complete}`, replacing the
  `ComingSoonView` placeholder (its import removed — no CRM section
  still needs it).
- `apps/crm/templates/crm/task_{list,detail,form}.html`.
- `apps/crm/templates/crm/contact_detail.html`,
  `apps/crm/templates/crm/deal_detail.html` — their existing (unlinked)
  task lists now link to `task_detail`, now that the page exists.
- `apps/crm/tests/test_task_views.py` — 28 tests (26 from the original
  unit + 2 regression tests added by the post-merge fix below).

## Commands

$ (manage.py shell, setup_test_environment + Client) full flow:
  unauthenticated redirect → create GET defaults `assigned_to` to the
  current user → query-param prefill for `contact` → create POST →
  update to `completed` sets `completed_at` → reopening to `pending`
  clears it → `TaskCompleteView` one-click completion → `overdue`/
  `mine`/`status`/`priority` filters → open-redirect `next` rejected,
  falls back to task detail.
Result: PASS, every step — before any automated test existed.

$ python manage.py test apps.crm.tests.test_task_views
Result: PASS — 26/26. (One authoring fix along the way: two Deal
fixtures needed a `company` to satisfy `deal_has_company_or_contact` —
caught by the DB constraint itself, not a hidden bug.)

$ python manage.py test (full suite)
Result: PASS — 207 tests at merge time (up from 181); 209 after the
post-merge fix added two regression tests.

$ manage.py check / makemigrations --check --dry-run
Result: PASS — no issues, no pending migration (both new `Task` members
are Python-only: a property and a `get_absolute_url` method).

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after one formatting-only fix to the new test file; no
real findings.

Dev database confirmed clean of smoke-test leftovers (`Task.objects.count()
== 0`, no `smoketest_*` users) before committing.

## Tests

`python manage.py test` — 209 passed, 0 failures (as of the post-merge
fix; 207 at original merge time).

## Decisions

- No DB-level "at least one relation" constraint for Task (unlike Deal/
  Activity) — a Task can legitimately stand alone (e.g. "follow up on
  general admin"), so `TaskForm` has no custom `clean()`.
- `completed_at` lifecycle handled the same way as `Deal.closed_at`:
  a small `_sync_task_completed_at()` helper called from both
  `TaskCreateView.form_valid()` and `TaskUpdateView.form_valid()`, set
  when status becomes `completed`, cleared otherwise (reopened to
  `pending` or moved to `cancelled`) — an application-layer invariant,
  documented in `docs/DATABASE_DESIGN.md`'s existing Lifecycle section
  for the pattern generally.
- `TaskCompleteView` is a separate `View` (not folded into
  `TaskUpdateView`) so completing a task from the list or detail page
  doesn't require going through the full edit form — the dedicated
  "completion workflow" Prompt 4.2 calls for. POST-only, reuses the
  same open-redirect-safe `next` handling pattern as elsewhere.
- Linked Contact/Deal detail pages' existing task listings to
  `task_detail` now that it exists — a small, directly-related fix
  rather than a separate unit, since those pages already rendered task
  titles/statuses with no way to reach them.

## Errors

None from manual smoke testing or automated review at merge time
(Sourcery was rate-limited on this PR — see Git section). One
self-caught test-authoring issue: two `Deal` fixtures needed a
`company` to satisfy the existing `deal_has_company_or_contact`
constraint — an assertion of my own test data, not an application bug.

**Found after merge**, during a deliberately more thorough manual
review specifically to compensate for the missing Sourcery pass: a
direct POST to `TaskCompleteView` (bypassing the UI, which only shows
the "Mark complete" action for pending tasks) would force *any* task —
including an already-cancelled one — straight to `completed`, silently
reviving it. Same shape as a bug `LeadConvertView` already guards
against for "already converted" leads. Fixed by adding the same kind
of guard: `TaskCompleteView.post()` now no-ops (with an info message)
unless the task is currently pending. Two regression tests added
(`test_does_not_complete_a_cancelled_task`,
`test_already_completed_task_is_left_unchanged`). See the follow-up
fix PR in the Git section below.

## Lessons learned

- The `?relation=<id>` query-param prefill idiom (Lead conversion →
  Activity creation → now Task creation) continues to hold up as a
  genuinely reusable pattern with zero surprises on its third use.
- Sourcery's review budget is rate-limited (250,000 diff characters per
  7 days) and can be exhausted mid-project — this PR merged on local
  verification alone (full test suite, ruff, bandit, pip-audit) with
  CI green, since no automated review was available. That gap turned
  out to matter: a real state-machine bug (see Errors above) slipped
  through into `main` and was only caught by a deliberate post-merge
  review pass, not by anything in the original PR's checks. Worth
  treating "no Sourcery review" as a reason to review more carefully
  myself, not just proceed on CI + local tests as if nothing were
  missing.

## Git

Branch: `feature/tasks-crud` (merged, deleted)
Commit: `bc79614`
Merged to `main`: `ab2af6d` (regular merge commit, PR #31 — CI green;
Sourcery's own review was rate-limited for this PR, so no automated
review findings either way this unit)

Follow-up fix (`TaskCompleteView` status guard, found via post-merge
review): see `logs/git/commits.md` / `logs/git/branches.md` for the
branch/commit/PR/merge detail once that cycle completes.

## Next

Phase 4 unit 3 — lightweight audit history for important CRM record
changes (who changed this / what changed / when), per Prompt 4.3.
