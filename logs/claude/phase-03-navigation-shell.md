# PHASE 03: FULL NAVIGATION, ERROR PAGES, STYLING

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Second (and final) unit of the application shell (Prompt 3.1's full
scope): full navigation linking every CRM section, custom 404/500 error
pages, and styling refinement. Completes the "application shell" work
before Companies/Contacts CRUD starts.

## Files created / changed

- `apps/core/views.py` — `ComingSoonView` (a reusable
  `LoginRequiredMixin` + `TemplateView`, parameterized via
  `.as_view(section_label=...)`), used for every CRM section that
  doesn't have real views yet.
- `apps/core/templates/core/coming_soon.html`.
- `apps/crm/urls.py` — new; Companies/Contacts/Leads/Deals/
  Activities/Tasks, each a real login-required URL using
  `ComingSoonView`.
- `apps/core/urls.py` — added `/search/`.
- `config/urls.py` — mounted `apps.crm.urls`.
- `templates/base.html` — full nav (Dashboard + 6 CRM sections + Search),
  username + "change password" link + logout in a separate
  `user-controls` block.
- `templates/404.html` (extends `base.html` — has request context) and
  `templates/500.html` (deliberately standalone, no `extends`, no
  `{% static %}` — Django's `server_error` view renders it without a
  `RequestContext`, so it can't safely depend on context processors).
- `static/css/base.css` — expanded for the wider nav layout, plus a
  small `.error-page` style block.
- `apps/core/tests/test_navigation.py`, `test_error_pages.py` — 14 new
  tests.

## Commands

$ (manage.py shell, setup_test_environment + Client) hit all 8 nav URLs
  as a logged-in user
Result: PASS — every one returned 200 before any automated test existed.

$ (manage.py shell) override_settings(DEBUG=False) + Client, GET a
  nonexistent URL
Result: PASS — 404 with the custom template's text present.

$ (manage.py shell) render_to_string("500.html")
Result: PASS — renders standalone with no request/context processors,
confirming the "must not depend on `user`/`{% static %}`" constraint is
actually satisfied, not just asserted in a comment.

$ python manage.py test
Result: PASS — 52 tests (14 new), up from 38 at the start of Phase 3.

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: all PASS, no fixes needed this unit.

## Tests

`python manage.py test` — 52 passed, 0 failures.

## Decisions

- Used one reusable `ComingSoonView` (parameterized via
  `.as_view(section_label=...)`) instead of six near-identical
  placeholder view functions — avoids repetition without adding a
  real abstraction cost.
- `500.html` is deliberately standalone rather than extending
  `base.html`, following Django's own documented behavior (the
  `server_error` view intentionally skips context processors to reduce
  the chance the error page itself fails while already handling an
  error). `404.html` safely extends `base.html` since Django's
  `page_not_found` view does pass a request/context.
- Search lives under `apps.core` (cross-cutting, not owned by a single
  CRM entity), matching `docs/ARCHITECTURE.md`'s description of what
  `apps.core` is for.

## Errors

None this unit — the empirical pre-checks (nav URLs, 404, 500 template)
all passed on the first attempt, and the automated review found nothing
to fix (a first for this project's review history: 6 prior PRs each had
at least one real or genuinely useful finding).

## Lessons learned

- Reviewing every prior PR in this session found something real — this
  one didn't, which is itself worth noting rather than treating
  "no findings" as suspicious. Empirically pre-verifying every new route
  before writing tests (a habit built up over the previous units)
  likely accounts for the clean pass.

## Git

Branch: `feature/navigation-shell` (merged, deleted)
Commit: `93e2376`
Merged to `main`: `edf4ef8` (squash merge, PR #18)

## Next

Phase 3 unit 3 — Companies CRUD (list/detail/create/edit/delete,
search, filtering, pagination), replacing the `crm:company_list`
placeholder with a real view. Then Contacts CRUD, then Leads/Deals
workflows.
