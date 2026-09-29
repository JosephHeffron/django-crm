# PHASE 16: BROWSER-VERIFIED SECURITY REVIEW (CSP)

Started: 2026-09-28
Ended: 2026-09-28

## Objective

Second phase of the post-release roadmap: revisit the Content-Security-
Policy header deferred twice (`docs/SECURITY_REVIEW.md` #6,
`docs/PRODUCTION_CONFIG_REVIEW.md` #2), both times because verifying it
against Django admin's inline scripts needed a real browser, which
neither prior review's tooling could provide.

## Files created / changed

- `config/settings/base.py` — added `django.middleware.csp.
  ContentSecurityPolicyMiddleware` to `MIDDLEWARE` and
  `django.template.context_processors.csp` to `TEMPLATES`' context
  processors (required for `{% csp_nonce_attr %}`, used throughout
  Django's own admin templates, to actually render a nonce).
- `config/settings/production.py` — `SECURE_CSP` policy (production
  only, not dev — see Decisions below).
- `docs/decisions/0007-django-native-csp.md` — new ADR: why Django's
  own native CSP middleware, not Caddy or `django-csp`; full live
  verification detail.
- `docs/SECURITY_REVIEW.md`, `docs/PRODUCTION_CONFIG_REVIEW.md`,
  `docs/PRODUCTION_READINESS.md` — the CSP finding marked fixed in
  place, in each of the three documents that tracked it.
- `docs/ARCHITECTURE.md` — "Security boundaries" section mentions the
  CSP policy.
- `docs/ROADMAP.md` — Phase 16's checkbox (checked in the close-out
  commit, per established pattern, not this one).
- `static/css/error.css` — new. `templates/500.html`'s CSS, moved out
  of an inline `<style>` block (Sourcery review fix, see below).
- `templates/500.html` — links the external stylesheet instead.
- `apps/core/tests/test_error_pages.py` — new regression test
  (`test_500_template_has_no_inline_style`) asserting this stays fixed.

## Commands

$ Read Django's own installed `contrib/admin` templates directly
  (`grep -rn "<script" .venv/lib/python3.12/site-packages/django/
  contrib/admin/templates/admin/`) rather than assuming from prior
  findings' descriptions. Found every single script/style tag already
  carries `{% csp_nonce_attr %}` — no truly inline, un-nonced content
  anywhere except one `<style>` block in `change_list.html`, which also
  already carries the tag. Also grepped for inline event handlers
  (`onclick=` etc.), `javascript:` hrefs, external fonts/images/CDNs —
  none found, in either Django admin's templates or this project's own.

$ `find /home/BlueEyes/.../django -iname "*csp*"` located
  `django/middleware/csp.py`/`django/utils/csp.py` — confirmed Django
  6.1.1 (this project's actual installed version, checked via
  `django.get_version()`) ships first-class CSP support, contradicting
  the "would need `django-csp`" assumption both prior findings were
  written under.

$ Installed Playwright + a headless Chromium build into an isolated
  throwaway venv (`/tmp/.../scratchpad/csp-test/pw-venv`, never a
  project dependency) — this session had no interactive computer-use/
  browser tool available, but a headless browser engine satisfies the
  same requirement ("watch a real browser's console for CSP
  violations") without one.

$ Live verification, against a real `manage.py runserver` using
  `config/settings/production.py` unmodified except
  `SECURE_SSL_REDIRECT=False` (via an external override module outside
  the project directory, never committed — plain-HTTP `runserver`
  can't serve the real value, `True`), `--insecure` (so static files
  serve under `DEBUG=False`, since `django.contrib.staticfiles` only
  patches `runserver` to serve them automatically under `DEBUG=True`
  otherwise — a real gotcha hit and fixed mid-session, not known in
  advance):
  1. `curl -I` confirmed the header renders with a real per-request
     nonce: `Content-Security-Policy: default-src 'none'; script-src
     'self' 'nonce-<...>'; ...`.
  2. A Playwright script logged in, visited the admin index, a
     changelist page (Companies — sidebar filters, theme toggle), an
     add form (Deal — date/calendar/clock widgets, related-object
     dropdowns), and opened a real related-object "add" popup
     (Company, from the Deal form) as a second browser tab — with a
     console listener across all of them.
  Result: **zero CSP violations, zero other console errors.** A
  full-page screenshot of the add form additionally confirmed correct
  visual rendering (icons, widgets, styling) — not just an absence of
  console errors.
  3. Created the throwaway test superuser and ran this check against
     this workstation's real local dev PostgreSQL (the same database
     `manage.py runserver`/`test` always use) — non-destructive,
     matching how a developer would manually test locally; the
     throwaway user was deleted again immediately after (`deleted: 1`),
     leaving no residue.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config -q`
  / `pip-audit -r requirements.txt` / `manage.py check` / `manage.py
  check --deploy` (against production settings, throwaway env vars) /
  `manage.py makemigrations --check --dry-run`
Result: PASS.

## Tests

`python manage.py test` — 304 passed, 0 failures (303 unchanged from
before this phase, plus 1 new regression test —
`test_500_template_has_no_inline_style` — added after the Sourcery
review below).

## Decisions

- **Django's native CSP middleware over Caddy-layer header
  injection** — the plan both prior findings assumed, written before
  either knew Django 6.1 would ship this. Caddy can't generate a
  per-response nonce matching what Django's own templates render, so a
  Caddy-set CSP would have forced `'unsafe-inline'` for admin's inline
  `<style>` block; Django's own middleware does the nonce correctly for
  free. Full reasoning in `docs/decisions/0007-django-native-csp.md`.
- **Production only, not dev** — Django's own `DEBUG=True` technical
  error page has un-nonced inline `<script>`/`<style>` (confirmed by
  reading `django/views/templates/technical_500.html` directly); a
  strict CSP would visibly break the traceback page in local dev for
  zero real security benefit, since that page never renders in
  production.
- **No Report-Only rollout period** — went straight to full
  enforcement, since the live verification already found zero
  violations under enforcement; a Report-Only stage would have been
  extra process with no additional information this unit's own testing
  didn't already gather directly.
- **A headless browser (Playwright), not a computer-use/browser-
  extension tool** — none was available this session. A headless
  Chromium instance is a genuine browser engine with a real console,
  satisfying what the original findings actually asked for ("watching
  a real browser's console"), not a lesser substitute — this
  distinction is worth remembering for any future finding phrased as
  "needs a real browser."

## Sourcery review (PR #88)

One real finding, fixed before merge: this project's own custom
`templates/500.html` had a genuinely inline `<style>` block with no
nonce — my own earlier audit of this project's templates had grepped
for `<script` but never `<style>`, missing it entirely. Worse, a
nonce-based fix wasn't viable at all here: Django's default
`handler500` (`django.views.defaults.server_error`) renders `500.html`
with no context (`Context: None`, confirmed directly — calling
`loader.get_template("500.html").render()` with no arguments, exactly
as that view does), so `{% csp_nonce_attr %}` would render nothing
regardless of the CSP context processor being installed. Fixed by
moving the CSS to `static/css/error.css` and linking it as an external
stylesheet — same-origin, so `style-src 'self'` permits it with no
nonce needed. Re-verified live: added a temporary route (never
committed) that deliberately raises an exception, triggered a real 500
under full CSP enforcement, and confirmed via the browser's own
`getComputedStyle` (not just a 200 status) that the stylesheet
genuinely applied, plus zero CSP violations on that response.

## Errors

- `manage.py runserver` served every admin static asset as a 404 HTML
  page under the test settings (`DEBUG=False`) — not a CSP problem,
  though the first test run's over-broad violation-detection regex
  (matching any "Refused to..." console message) misattributed it as
  one. Root cause: `django.contrib.staticfiles` only patches
  `runserver` to auto-serve static files when `DEBUG=True`, unless
  `--insecure` is passed. Fixed by adding that flag; re-ran the check
  and got a clean, real result.
- The first popup-related-object test attempt timed out waiting for a
  new page/tab — caused by an overlapping CSS selector between two test
  steps (date-shortcut links and related-object links share enough
  structure that an earlier step's click could consume the one the
  later step expected). Fixed by narrowing each step's selector; not a
  defect in the application itself.

## Lessons learned

- Reading a dependency's actual installed source (not just its
  changelog or prior assumptions about it) can invalidate an old
  finding's premise entirely — this project's Django version had
  quietly gained exactly the capability two separate audits assumed it
  lacked, and neither audit could have known without checking again at
  implementation time.
- "Needs a real browser" is a genuine, checkable requirement, not a
  permanent blocker — a headless browser engine, installed into an
  isolated throwaway environment for the duration of one verification,
  satisfies it without needing interactive computer-use tooling or a
  GUI.

## Git

Branch: `feature/csp-django-native`
Commit: `9b2be71` (implementation), `ae6e120` (Sourcery-review fix —
the un-nonced inline `<style>` in `templates/500.html`)
Merged to `main`: `f79c3bf` (regular merge commit, PR #88 — CI green:
`test` + `dependency-audit` both pass)

## Next

Phase 17 — data portability and bulk operations, per
`docs/ROADMAP.md`.
