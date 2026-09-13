# PHASE 04: ACTIVITY TIMELINE (UNIT 1)

Started: 2026-09-11
Ended: 2026-09-11

## Objective

First unit of Phase 4, per Prompt 4.1: a reusable activity timeline
component appearing on Company/Contact/Lead/Deal detail pages, plus the
means to actually log an activity (Activity creation), replacing the
`crm:activity_list` placeholder.

## Files created / changed

- `apps/crm/forms.py` — `ActivityForm`, enforcing "at least one
  relation" at the form layer (the DB constraint was deliberately
  removed in the prior PR for exactly this purpose).
- `apps/crm/views.py` — `ActivityListView` (type filter, pagination),
  `ActivityCreateView` (query-param prefill, priority-ordered redirect
  after save); `_int_or_none()` and `_log_activity_url()` helpers;
  `get_context_data` on all four detail views (`Company`, `Contact`,
  `Lead`, `Deal`) now pass `activities` and `log_activity_url`.
- `apps/crm/urls.py` — real routes for `activity_list`/`activity_create`.
- `apps/crm/templates/crm/_activity_timeline.html` — reusable partial.
- `apps/crm/templates/crm/activity_{list,form}.html`.
- `apps/crm/templates/crm/{company,contact,lead,deal}_detail.html` —
  each now `{% include %}`s the timeline partial.
- `static/css/base.css` — `.timeline` styling.
- `apps/crm/tests/test_activity_views.py` — 20 tests.

## Commands

$ (manage.py shell, setup_test_environment + Client) full flow: empty
  list → GET create form with `?company=<id>` prefill → POST create →
  redirect to company detail → validation rejection (no relation) →
  timeline shows the new entry on the company page → list shows/filters
  it by type → multi-relation POST (company+contact) redirects to
  company (priority order) → confirmed no `activity_update` URL exists
  (`NoReverseMatch`) → unauthenticated redirect
Result: PASS, every step — before any automated test existed.

$ python manage.py test apps.crm.tests.test_activity_views
Result: PASS — 20/20 on the first run, no test bugs this time.

$ python manage.py test (full suite)
Result: PASS — 181 tests (up from 161).

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after one formatting-only fix; no real findings.

## Tests

`python manage.py test` — 181 passed, 0 failures.

## Decisions

- No `ActivityDetailView` or `ActivityUpdateView`: Activity's "detail
  page" is the timeline on whichever record it's attached to (there's
  nothing more to show on a standalone page), and Activity is immutable
  by design (`Activity.save()` already rejects updates) — adding an
  edit view would just be a form that always 500s on submit. Verified
  this empirically via `NoReverseMatch` in the tests, not just by
  omission.
- `ActivityCreateView.get_success_url()` picks a fixed priority order
  (company > contact > lead > deal) when an Activity ends up tagged to
  more than one relation at once, rather than requiring the caller to
  specify a return URL — simpler, and matches the same fixed-order
  pattern already used for redirect logic elsewhere in this app.
- The reusable timeline partial takes `activities` and
  `log_activity_url` as plain context variables rather than a Django
  template tag/inclusion tag — a plain `{% include %}` was simpler and
  sufficient; no need for the extra indirection of a custom tag for a
  single reused fragment.

## Errors

None this unit — no application bugs found via manual smoke testing,
no test-authoring bugs, and the automated review found nothing to fix.
Third unit in a row (after Leads, Deals) with a clean review pass.

## Lessons learned

- Deferring "at least one relation required" from a DB constraint to a
  form-layer rule (decided two phases ago, in the CASCADE/SET_NULL fix)
  paid off exactly as planned here — `ActivityForm.clean()` was a
  five-line addition matching the exact pattern already established for
  `DealForm`, with no surprises.
- A `?relation=<id>` query-param prefill pattern (first used for Lead
  conversion's initial values, now reused for Activity creation) is
  turning into a genuinely reusable idiom in this codebase — worth
  keeping in mind if a similar "create X in the context of Y" need
  comes up again in Phase 4's Tasks unit.

## Git

Branch: `feature/activity-timeline` (merged, deleted)
Commit: `29abe7b`
Merged to `main`: `00d78cd` (squash merge, PR #29)

## Next

Phase 4 unit 2 — Tasks (list/detail/create/edit/completion workflow,
"my tasks," "overdue tasks" views), per Prompt 4.2.
