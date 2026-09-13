# PHASE 05: USABILITY REVIEW (UNIT 3)

Started: 2026-09-13
Ended: 2026-09-13

## Objective

Third and final unit of Phase 5, per the roadmap: a dedicated
usability review pass. Unlike prior units, this is review work (same
shape as `docs/DATABASE_REVIEW.md` in Phase 2), not new-feature work.

## Method

No visual browser tool is available in this environment — this
project's own `WebFetch` tool explicitly refuses `localhost` URLs.
Rather than skip real-page inspection and rely solely on the Django
test client's assertions, ran a real authenticated walkthrough against
the actual dev server:

1. `manage.py runserver 127.0.0.1:8765` in the background.
2. Logged in over real HTTP with `curl` (extracting a real CSRF token
   from the login page, posting real credentials, keeping a cookie
   jar) — not the Django test client's shortcut login.
3. Created a Company, Contact, Lead, Deal, and Task through their real
   forms; converted the Lead; completed the Task — reading the exact
   HTML the server sent back at every step, not just checking status
   codes.
4. Systematically re-read every template for accessibility basics,
   navigation completeness, feedback consistency, and terminology.

## Files created / changed

- `apps/crm/templates/crm/_activity_timeline.html`,
  `_audit_history.html` — multi-line `{# #}` comments converted to
  `{% comment %}...{% endcomment %}` (see Errors below).
- `apps/crm/templates/crm/{company,contact,lead,deal,task,activity}_form.html`
  — added a "Cancel" link to each.
- `apps/crm/views.py` — `ActivityCreateView` gained `get_context_data()`
  and `_relation_url_from_query()` to compute `cancel_url`.
- `apps/crm/templates/crm/{company,contact,lead,deal,task,activity}_list.html`
  — `sr-only` `<label>`s added to filter-form inputs/selects; `.data-table`
  wrapped in `.table-responsive`.
- `apps/core/templates/core/search.html` — same label treatment;
  `apps/core/templates/core/index.html` — pipeline table wrapped.
- `templates/base.html` — `aria-current="page"` on the current nav
  section; `role="status"` on the flash-messages list.
- `static/css/base.css` — `.sr-only`, `.table-responsive`,
  `.main-nav a[aria-current="page"]`.
- `apps/crm/tests/test_template_rendering.py` — new, 10 tests
  (comment-leak regression + Cancel-link presence).
- `apps/crm/tests/test_activity_views.py` — 2 new tests (`cancel_url`).
- `apps/core/tests/test_navigation.py` — 2 new tests (`aria-current`).
- `docs/USABILITY_REVIEW.md` — new, the review document itself.

## Commands

$ Real walkthrough via `curl` against `manage.py runserver`: login →
  dashboard → all 6 list pages → company create/detail/deactivate →
  lead create/convert → task create/complete → contact detail (cross-
  linked Deal/Task) → 404 (confirmed expected `DEBUG=True` behavior,
  not the custom template — already correctly tested elsewhere).
Result: found the comment-leak bug (see Errors) via literal inspection
of the HTML `_activity_timeline.html`/`_audit_history.html` produced on
the Company detail page — reproduced directly via
`django.template.loader.get_template().render()` before touching any
file, then bisected which part of the multi-line comment triggered it
(confirmed: any newline inside `{# #}`, not the backticks or em-dash).

$ python manage.py test apps.crm.tests.test_template_rendering
apps.crm.tests.test_activity_views apps.core.tests.test_navigation
Result: PASS — 36/36.

$ python manage.py test (full suite)
Result: PASS — 268 tests (up from 254).

$ manage.py check / makemigrations --check --dry-run
Result: PASS — no schema changes this unit.

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after one formatting-only fix
(`apps/crm/tests/test_template_rendering.py`); no real findings.

Dev server stopped; dev database confirmed clean of all
walkthrough-created records (`usabreview` user, the Company/Contact/
Lead/Deal/Task created during the walkthrough) before committing.

## Tests

`python manage.py test` — 268 passed, 0 failures.

## Decisions

- Fixed every finding within this same unit rather than deferring —
  all were small, contained template/CSS changes with no schema or
  behavior-contract impact, matching the "small, reviewable changes"
  rule. Two items were explicitly deferred (dashboard quick-add
  shortcuts, currency formatting) as genuine nice-to-haves, not bugs.
- Cancel links use `object.get_absolute_url`/list-view fallback for
  the five models with both Create and Update views; Activity (no
  Update view, no single natural "list" context) gets a computed
  `cancel_url` reusing the same `?relation=<id>` query-param priority
  logic already established for `get_initial()`/`get_success_url()`,
  rather than inventing a new pattern.
- `role="status"` (not `role="alert"`) on flash messages — these are
  ordinary confirmations ("Created company…"), not urgent/interrupting
  errors; `alert` is reserved for the latter in ARIA's own guidance.
- Wrapped `.data-table` in a `.table-responsive` div rather than
  putting `overflow-x`/`display: block` on the table element directly
  — the latter is a common shortcut but breaks the table's own
  column-alignment layout.

## Errors

**Found via this unit's own walkthrough, not by a prior automated
test:** Django's `{# ... #}` comment tag does not support multi-line
content — confirmed empirically (`from_string()` bisection) that any
newline inside `{# #}` causes the entire literal text to render
instead of being stripped, while a single-line comment strips
correctly. `_activity_timeline.html` and `_audit_history.html` both had
multi-line comments, so every Company/Contact/Lead/Deal detail page
had been showing raw template-source text since Phase 4 units 1 and 3
— live on `main` this whole time, undetected by any of the ~250 tests
written in those two units, because none of them asserted on the
*absence* of that text. A repo-wide scan (`re.DOTALL` regex across
every `.html` template) confirmed these were the only two instances.
Fixed by converting both to `{% comment %}...{% endcomment %}` blocks
(which do support multi-line), verified directly against Django's
template engine both before and after, and covered with 4 regression
tests asserting the specific leaked strings are absent from all four
detail pages.

No findings from Sourcery this unit (rate-limited on this PR too), but
unlike the two prior units where that meant "no external review at
all," this unit's entire premise already supplied an equivalent (a
real, deliberate manual walkthrough) rather than needing a substitute
adversarial pass afterward.

## Lessons learned

- This is the clearest evidence yet in this project that
  `assertContains`-style automated tests and a real rendered-page
  walkthrough catch different classes of bugs: every existing test
  touching these four detail pages passed the whole time, because
  "contains X" doesn't rule out "also contains garbage Y." A dedicated
  usability/manual-review pass earns its keep specifically by looking
  at the *whole* page, not just the assertion under test.
- When something surprising shows up in raw output (a template
  comment appearing as literal text), reproduce it in the smallest
  possible harness before touching any file — `from_string()` with
  hand-built test strings isolated the exact cause (multi-line, not
  content) in under a minute, rather than guessing.
- Each `Bash` tool call is a fresh shell — a variable set in one call
  (e.g. an extracted CSRF token) does not persist to the next call.
  Several of this unit's own `curl` attempts hit spurious CSRF 403s
  purely from this, not from any application bug; combining
  token-extraction and the dependent request into one shell invocation
  fixed it. Worth remembering before concluding a request failure is a
  real app bug.

## Git

Branch: `fix/usability-review` (merged, deleted)
Commit: `a9adeac`
Merged to `main`: `00c778d` (regular merge commit, PR #41 — CI green,
`mergeStateStatus: CLEAN`; Sourcery rate-limited, no findings from it,
but this unit's own manual walkthrough already served that role)

## Next

Phase 5 is now fully complete (all 3 units: Global search, Operational
dashboard, Usability review). Next is Phase 6 — Security hardening.
