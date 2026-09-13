# Security review

Phase 6 unit 1 — a full Django security audit, per the roadmap. Same
format as `docs/DATABASE_REVIEW.md`/`docs/USABILITY_REVIEW.md`:
findings ranked by severity, checked empirically, fixed where the fix
is safe and contained, deferred (with reasoning) where it isn't.

## Method

- `manage.py check --deploy` run against `config.settings.production`
  with realistic environment variables (a throwaway `DJANGO_SECRET_KEY`,
  not a real one) — Django's own built-in deployment checklist.
- Manual review of `config/settings/{base,development,production}.py`
  against Django's security documentation, beyond what `--deploy`
  itself checks.
- Repo-wide `grep` for known anti-patterns: raw SQL / `cursor.execute`,
  `mark_safe`/`|safe`, `@csrf_exempt`, `eval`/`exec`, file upload
  fields.
- Re-confirmed (rather than re-assumed) two protections already built
  during earlier phases: template auto-escaping against a literal
  `<script>` payload (originally verified during Phase 4's audit-log
  work) and the open-redirect guard on `TaskCompleteView`'s `next`
  param (`url_has_allowed_host_and_scheme`, built in Phase 4).
- A real, live HTTP round trip (login + a CSRF-protected form
  submission) via `curl` against a running dev server for the one
  settings change (`CSRF_COOKIE_HTTPONLY`) that Django's test client
  can't meaningfully verify — the test client's CSRF checks are
  disabled by default, so the existing 268 passing tests don't
  actually exercise real cookie behavior.

## HIGH

None found.

## MEDIUM

### 1. `CSRF_COOKIE_HTTPONLY` was not set (defaulted to `False`)

Django's CSRF cookie is readable by JavaScript by default, to support
apps that read it client-side to set an `X-CSRFToken` header for AJAX
requests. This app has **no JavaScript at all** beyond the browser's
own form submission — every `{% csrf_token %}` is a server-rendered
hidden `<input>`, confirmed by grepping every template and the static
directory for any `.js` file (none exist). There is no reason for the
cookie to be script-readable, and leaving it readable is a small,
free-to-close attack surface (a successful XSS elsewhere could exfiltrate
the token) with zero functional benefit here.

**Status: FIXED.** `CSRF_COOKIE_HTTPONLY = True` added to
`config/settings/base.py` (applies to both dev and production).
Verified with a real login + form-submission round trip against a
live `manage.py runserver` instance via `curl` — confirmed the cookie
jar now marks `csrftoken` as `HttpOnly`, and the full login → fetch
form → submit flow still succeeds end-to-end. This is the kind of
change Django's test client (CSRF checks disabled by default) cannot
actually verify, so it was checked live rather than assumed safe.

### 2. No role/permission separation

Every authenticated user can view, create, edit, and deactivate every
record — there's no concept of "my records only" or an
admin/regular-user distinction beyond Django's own `is_staff`/
`is_superuser` gating the admin site. This is a real gap for anything
beyond a single-user or fully-trusted-small-team deployment, but it's
not a Unit 1 finding to fix here — it's precisely what Phase 6 Unit 2
(`docs/PERMISSIONS.md`, a practical Django Groups/Permissions model)
exists to address next. Noted here so it isn't silently missing from
this audit, not left as a surprise.

## LOW

### 3. Password minimum length was Django's default (8 characters)

`AUTH_PASSWORD_VALIDATORS`'s `MinimumLengthValidator` had no `OPTIONS`
override, so it used Django's built-in default of 8. Current guidance
(and most contemporary internal tooling) treats 8 as a floor, not a
target.

**Status: FIXED.** Raised to `min_length: 12` in
`config/settings/base.py`. This only affects future password
sets/changes (Django validators run at set-time, not retroactively),
so it doesn't lock out or affect any existing account. Confirmed the
one test that exercises the password-change form
(`apps/users/tests/test_auth.py::PasswordChangeTests`) already uses
passwords well over 12 characters, so nothing needed updating there.

### 4. Django admin left at the default `/admin/` path

A well-known target for automated scanners/bots, though not itself a
vulnerability — the admin login still requires valid credentials and
is subject to the same password validators as everywhere else.
**Deferred, not fixed**: relocating it is easy but adds an
operational cost (a non-obvious path to remember/document) for
marginal benefit against a targeted attacker who'd find it via
directory brute-forcing regardless. Revisit during Phase 8
(Caddy/HTTPS) if IP-allowlisting or a similar reverse-proxy-level
restriction on `/admin/` turns out to be worthwhile once this is
actually deployed and reachable from outside a trusted network.

### 5. No login-attempt rate limiting / account lockout

Django ships no built-in brute-force throttling on `LoginView`.
**Deferred, not fixed**: adding this means either a new dependency
(`django-axes` or similar) or custom middleware — a real cost for an
app not yet deployed anywhere reachable from the open internet, and
exactly the kind of addition CLAUDE.md's "do not overengineer" rule
asks to justify concretely before adding. If this app becomes
internet-facing without a trusted network/VPN boundary in front of it,
revisit then; a reverse-proxy-level rate limit (Caddy, Phase 8) may be
the simpler fix at that point anyway, rather than an
application-level dependency.

### 6. No Content-Security-Policy header

Not set anywhere; Django has no first-class built-in for this (would
need `django-csp` or hand-rolled middleware). **Deferred**: this is a
better fit for the reverse-proxy layer (Caddy, Phase 8) than an added
Django dependency, and with zero third-party JavaScript or inline
scripts anywhere in the app today, the risk this would mitigate is
already small.

### 7. No custom `AUTH_USER_MODEL`

Django's own documentation strongly recommends setting up a custom
user model at the very start of a project, specifically because
swapping it out later is disruptive — this project uses the default
`django.contrib.auth.User`, and by now has eight foreign keys across
six models (`Company.owner`/`created_by`, `Contact.owner`/
`created_by`, `Lead.owner`/`created_by`, `Deal.owner`/`created_by`,
`Task.assigned_to`/`created_by`, `Activity.created_by`,
`AuditLogEntry.user`) pointing at it. Changing this now would be a
genuinely painful migration, not a quick fix. **Not a new finding** —
this is the same trade-off `docs/DATABASE_DESIGN.md`'s "Decisions that
intentionally avoid overengineering" section already made
consciously in Phase 2 ("a custom profile model would only be
justified if a concrete field...is needed, which nothing today
requires"). Restated here so a security-focused read of this project
doesn't mistake it for an oversight — it's a deliberate, documented,
informed trade-off, revisited only if a concrete need for custom User
fields actually arises.

## Checked and confirmed solid (not just assumed)

- `manage.py check --deploy` against `config.settings.production`
  (with realistic env vars) reports **zero issues** — `DEBUG = False`
  hardcoded (not env-controlled) in production, `SECURE_SSL_REDIRECT`,
  full HSTS (`SECURE_HSTS_SECONDS` = 1 year, subdomains, preload),
  `SESSION_COOKIE_SECURE`/`CSRF_COOKIE_SECURE`,
  `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS = "DENY"` are all
  already correctly configured.
- No raw SQL, no `.raw()`/`cursor.execute()`/`.extra()` anywhere in
  application code (migrations and tests excluded from the search,
  same as the project's Bandit config already excludes) — every query
  goes through the ORM.
- No `mark_safe()` or `|safe` filter anywhere — every user-supplied
  value rendered in a template goes through Django's default
  auto-escaping. Re-confirmed with a literal `<script>alert(1)</script>`
  payload against the audit-log history display during Phase 4;
  correctly escaped.
- No `@csrf_exempt` anywhere; every state-changing form (including the
  one-click Task-complete action and the logout button) submits a real
  CSRF token.
- `TaskCompleteView`'s `next` redirect parameter is validated with
  `django.utils.http.url_has_allowed_host_and_scheme` before use — the
  one place in the app that redirects based on user-controlled input.
- No self-service signup and no password-reset-via-email flow — the
  only auth views are login, logout, and authenticated password
  change. This removes a whole class of common attack surface (email
  enumeration through a "forgot password" flow, reset-token
  interception/leakage) that a small, admin-provisioned-accounts CRM
  like this one doesn't need to carry.
- No `FileField`/`ImageField` anywhere in the models — no file-upload
  attack surface exists yet (file attachments are explicitly out of
  initial release scope per `docs/ROADMAP.md`).
- Dependencies are pinned to exact versions in `requirements.txt`
  (`Django==6.1.1`, `psycopg2-binary==2.9.13`, `python-dotenv==1.2.3`);
  `pip-audit` has been run repeatedly throughout this project with
  zero findings so far (a full, dedicated dependency audit is Phase 6
  Unit 3, immediately following this one).
- Every CRM view requires authentication (`LoginRequiredMixin` or
  `@login_required`) — exercised by an "anonymous user is redirected"
  test on essentially every view added across this entire project.

## Recommendation

No HIGH findings. Both safe, zero-downside MEDIUM/LOW fixes
(`CSRF_COOKIE_HTTPONLY`, password minimum length) were applied in this
unit. The remaining items are genuinely deferred, not ignored: role
separation is Phase 6's own next unit; rate-limiting, the admin path,
and CSP are better addressed once Caddy is in front of this app
(Phase 8) or if a concrete deployment need actually demonstrates they
matter, rather than added speculatively now; the default user model is
an informed, already-documented trade-off from Phase 2, not new.
