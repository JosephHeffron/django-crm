# PHASE 03: AUTHENTICATION + MINIMAL BASE SHELL

Started: 2026-09-11
Ended: 2026-09-11

## Objective

First small unit of Phase 3 (CRM interface): authentication (login,
logout, password change) using Django's built-in auth views, plus the
minimal `templates/base.html` shell needed for those pages — and for the
CRM dashboard placeholder — to render. Full navigation, styling
refinement, and custom error pages are separate follow-up units, per
`CLAUDE.md`'s "break work into small logical units" rule.

## Files created / changed

- `apps/users/urls.py` — login/logout/password-change/password-change-done,
  all under the `users:` namespace.
- `config/urls.py` — mounted at `/accounts/`.
- `config/settings/base.py` — `LOGIN_URL`, `LOGIN_REDIRECT_URL`,
  `LOGOUT_REDIRECT_URL`.
- `templates/base.html` — minimal shell (brand link, nav placeholder that
  shows username + logout form when authenticated, Django messages
  block, content block), `static/css/base.css`.
- `templates/registration/{login,password_change_form,password_change_done}.html`.
- `apps/core/views.py` — `index` now `@login_required`, renders
  `apps/core/templates/core/index.html` (a placeholder dashboard) instead
  of a bare `HttpResponse`.
- `apps/{core,users}/tests/` (new packages, replacing stub `tests.py`) —
  10 tests total.

## Commands

$ python manage.py runserver ... + curl (real HTTP requests, real CSRF
  tokens extracted from actual page HTML, not hardcoded)
Result: verified end-to-end *before* writing automated tests —
unauthenticated `/` → 302 to `/accounts/login/?next=/`; login page
renders with static CSS loading; successful login → 302 to `/`; `/`
while authenticated shows "Signed in as <user>" and a working logout
form; logout → session ends, `/` redirects to login again. No errors in
the server log.

$ python manage.py test apps.users apps.core
Result: PASS — 9 tests (unauthenticated redirect incl. `?next=`
preserved, successful/failed login, logout ends session, logout requires
POST — confirmed empirically via a real 405, not assumed from Django's
changelog).

$ (later, from review) Django test client / shell reproduction of a
  password-change POST
Result: FAILED first — `NoReverseMatch: Reverse for
'password_change_done' not found` — see Errors below.

## Tests

`python manage.py test` — 48 passed (10 new: 9 from the initial commit
plus 1 regression test added with the password-change fix; up from 38
at the end of Phase 2). No failures.

## Decisions

- No custom `Profile`/`Member` model — matches the design decision
  already recorded in `docs/decisions/`; `settings.AUTH_USER_MODEL`
  (Django's built-in `User`) is used directly.
- No password-reset flow (email-based) in this unit — no `EMAIL_BACKEND`
  is configured yet, and a "reset" link that can't actually send email
  would be a broken feature, not a real one. Deferred until email sending
  is set up for a concrete reason.
- Login/logout/password-change only for now; permission-aware access
  control is deferred to the Permissions phase (Phase 6), since no
  permission model has been designed yet — nothing to enforce beyond
  "authenticated or not" at this point.

## Errors

- Automated review (`sourcery-ai`, PR #16) caught a real bug:
  `PasswordChangeView`'s default `success_url` resolves an unnamespaced
  `password_change_done`, but this URLconf only registers it as
  `users:password_change_done` (inside the `users` app namespace).
  Verified with an actual reproduction via the Django test client before
  believing the claim — a valid password-change POST raised
  `NoReverseMatch`. Fixed by setting `success_url` explicitly via
  `reverse_lazy("users:password_change_done")`. Re-verified the fix
  (302 to the done page, and the new password actually authenticates)
  and added a regression test with the failure mode documented in a
  comment.
- My own initial CSRF-token extraction in the manual `curl` smoke test
  used the wrong quote style (`'...'` instead of Django's actual
  `"..."`), silently producing an empty token and a `403`. Caught by
  inspecting the raw HTML rather than assuming the regex was right, and
  fixed before relying on the smoke test's result.

## Lessons learned

- Manually driving the actual HTTP flow (server + curl + real tokens)
  before writing the automated test suite caught a CSRF-extraction bug
  in my own test script immediately — worth doing for any auth-adjacent
  feature where "the test passed" and "the feature actually works" can
  diverge if the test itself has a bug.
- A `success_url` on a Django generic view that isn't set explicitly
  will use whatever default that view class ships with — worth checking
  explicitly whenever a URLconf uses app namespacing, since the
  unnamespaced default silently doesn't exist until it's actually
  exercised by a real POST, not by a page just loading.

## Git

Branch: `feature/authentication` (merged, deleted)
Commits: `222dca7` (initial auth + shell), `0a01501` (NoReverseMatch fix)
Merged to `main`: `9b9f57c` (squash merge, PR #16)

## Next

Remaining units of Phase 3:
1. Full navigation (Companies/Contacts/Leads/Deals/Activities/Tasks/
   Search links in the shell nav), styling refinement, custom 404/500
   error pages.
2. Companies CRUD (list/detail/create/edit/delete, search, filtering,
   pagination).
3. Contacts CRUD.
4. Leads and Deals workflows (Phase 3's later prompts).

Also still outstanding from Phase 2's review (deliberately deferred,
per the user's choice): the two HIGH findings in
`docs/DATABASE_REVIEW.md` (Activity CASCADE, on_delete enforcement),
to be resolved before Phase 4.
