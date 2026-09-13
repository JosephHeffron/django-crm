# PHASE 05: OPERATIONAL DASHBOARD (UNIT 2)

Started: 2026-09-12
Ended: 2026-09-12

## Objective

Second unit of Phase 5, per the roadmap: build out the operational
dashboard — the `core:index` page has said only "Signed in as
{{ user.username }}" since Phase 3, with a comment that it would be
built out later.

## Files created / changed

- `apps/core/views.py` — converted the function-based `index` view to
  `DashboardView` (`LoginRequiredMixin` + `TemplateView`), matching
  `SearchView`'s style. Computes: active company/contact counts, open
  lead count (excludes `converted`), open deal count + total value
  (excludes `CLOSED_STAGES`), pending task count, a per-stage pipeline
  breakdown (count + value) built by iterating `Deal.Stage.choices` in
  order, the signed-in user's own pending tasks (capped at
  `DASHBOARD_LIST_LIMIT`), and a recent-activity feed (same cap).
- `apps/core/urls.py` — `core:index` now points at `DashboardView`.
- `apps/core/templates/core/index.html` — quick-stat links, a pipeline
  table, a "your tasks" list (reusing the `is_overdue` "(overdue)"
  convention from the Task pages), and a recent-activity feed (reusing
  the same timeline markup/CSS as the per-record Activity timeline
  partial).
- `static/css/base.css` — `.dashboard-stats` (a small flex-wrap list).
- `apps/core/tests/test_dashboard.py` — 15 tests.

## Commands

$ (manage.py shell, setup_test_environment + Client) full flow:
  unauthenticated redirect → empty-state counts (all zero) → seeded
  counts (active-only companies/contacts, open-lead count excluding a
  converted one, open-deal count/value excluding a closed_won deal,
  pending-task count excluding a completed one) → my-tasks scoping
  (shows only the current user's pending tasks, marks an overdue one)
  → pipeline-by-stage breakdown values → recent-activity display.
Result: PASS, every step — before any automated test existed.

$ python manage.py test apps.core.tests.test_dashboard
Result: PASS — 15/15 on the first run.

$ python manage.py test apps.core.tests.test_navigation
apps.core.tests.test_views
Result: PASS — confirmed converting `index` from a function-based view
to `DashboardView` didn't break the existing dashboard/nav tests (they
check the rendered page's content and URLs, not the view's internal
shape).

$ python manage.py test (full suite)
Result: PASS — 254 tests (up from 239).

$ manage.py check / makemigrations --check --dry-run
Result: PASS — no schema changes this unit.

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after two formatting-only fixes (`apps/core/views.py`,
`apps/core/tests/test_dashboard.py`); no real findings.

**Post-merge review**: Sourcery was rate-limited on this PR (only its
auto-generated guide posted, no actual findings — see Git section).
Rather than a separate live adversarial script this time, reasoned
through the same class of edge cases that script would have exercised,
directly against what the 15 dedicated tests already assert: `Sum()`
over a stage with all-`None` values correctly reduces to 0 (not `None`)
via the `or 0` fallback (`test_stage_with_no_deals_shows_zero_count_and_value`),
a stage with zero matching deals is absent from the annotated queryset
entirely and the dict-based lookup correctly defaults it to 0 rather
than raising a `KeyError`, `my_tasks` is correctly scoped to
`assigned_to=request.user` and excludes other users' and completed
tasks (`test_shows_only_my_pending_tasks`), and the dashboard makes no
new per-user authorization assumption beyond what's already true
everywhere else in this app (a single shared workspace, not
multi-tenant). No new issues found.

## Tests

`python manage.py test` — 254 passed, 0 failures.

## Decisions

- "Open" leads = not `converted` (a converted Lead's own workflow is
  done, per `docs/DATABASE_DESIGN.md`'s Lifecycle section) — no new
  business rule invented, just naming an existing implicit boundary.
- Pipeline-by-stage breakdown iterates `Deal.Stage.choices` in Python,
  rather than trusting `.values('stage').annotate(...)`'s own row
  order — `Meta.ordering` doesn't apply to `.values()/.annotate()`
  queries, so without this, the breakdown would come back alphabetical
  (`closed_lost, closed_won, negotiation, ...`) instead of the actual
  pipeline sequence, which would be actively misleading on a page
  meant to show pipeline progression at a glance.
- No charting library, no JS dashboard framework — every figure is a
  plain Django ORM aggregate rendered server-side, per CLAUDE.md's
  "do not overengineer" rule. A future unit could add visual charts if
  a concrete need shows this text/table view is insufficient.
- Reused existing conventions rather than inventing new ones: the
  Task pages' "(overdue)" marker and the Activity timeline's markup/
  CSS, so the dashboard doesn't introduce a third way of representing
  the same information.

## Errors

None found via manual smoke testing, the automated test suite, or the
post-merge review reasoning pass (Sourcery itself didn't produce
findings either way — rate-limited). Two formatting-only lint fixes,
not application bugs.

## Lessons learned

- Not every "Sourcery is rate-limited" situation needs a fresh
  from-scratch adversarial script — when the dedicated test suite
  already directly asserts on the exact properties (null-handling,
  zero-default behavior, per-user scoping) an adversarial pass would
  target, reasoning through those same edge cases against the existing
  tests is a legitimate, faster way to get the same assurance, as long
  as the reasoning is actually checked against what the tests assert
  rather than just asserted from memory.

## Git

Branch: `feature/operational-dashboard` (merged, deleted)
Commit: `f9968ee`
Merged to `main`: `21b560c` (regular merge commit, PR #39 — CI green,
`mergeStateStatus: CLEAN`; Sourcery rate-limited, no findings from it)

## Next

Phase 5 unit 3 — a dedicated usability review pass (the final Phase 5
unit per the roadmap).
