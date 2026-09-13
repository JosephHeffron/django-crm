# PHASE 06: SECURITY AUDIT (UNIT 1)

Started: 2026-09-13
Ended: 2026-09-13

## Objective

First unit of Phase 6, per the roadmap: a full Django security audit,
written up in `docs/SECURITY_REVIEW.md`. Same shape as
`docs/DATABASE_REVIEW.md`/`docs/USABILITY_REVIEW.md` — a review
document with ranked findings, not new-feature work.

## Method

- `manage.py check --deploy` against `config.settings.production`
  with realistic (throwaway) environment variables — Django's own
  built-in deployment checklist.
- Manual read of all three settings files against Django's security
  documentation, beyond what `--deploy` itself checks.
- Repo-wide `grep` for known anti-patterns: raw SQL/`cursor.execute`/
  `.extra()`, `mark_safe`/`|safe`, `@csrf_exempt`, `eval`/`exec`,
  `FileField`/`ImageField`.
- Re-confirmed rather than re-assumed two protections built in earlier
  phases: template auto-escaping (originally verified with a literal
  `<script>` payload during Phase 4's audit-log work) and
  `TaskCompleteView`'s open-redirect guard.
- One settings change (`CSRF_COOKIE_HTTPONLY`) needed a **live** check:
  Django's test client disables real CSRF enforcement by default, so
  the existing 268 passing tests couldn't actually verify this
  wouldn't break anything. Started `manage.py runserver`, logged in
  over real HTTP with `curl` (real CSRF token, real cookie jar), and
  submitted a real Create-Company form — confirmed via the cookie
  jar's `#HttpOnly_` prefix that the flag took effect, and that the
  full login → form → submit flow still succeeded end to end.

## Files created / changed

- `docs/SECURITY_REVIEW.md` — new, the audit itself.
- `config/settings/base.py` — `CSRF_COOKIE_HTTPONLY = True`;
  `AUTH_PASSWORD_VALIDATORS`'s `MinimumLengthValidator` given
  `OPTIONS: {"min_length": 12}` (was Django's default of 8).
- `apps/core/tests/test_security_settings.py` — new, 3 tests.

## Commands

$ `manage.py check --deploy` (dev-realistic env vars, production
  settings module)
Result: PASS — zero issues both before and after this unit's changes.

$ Live `curl` walkthrough against `manage.py runserver`: login → cookie
  jar shows `csrftoken` gained the `#HttpOnly_` prefix → GET the
  Company create form → POST it with the real CSRF token → 302 to the
  new record.
Result: PASS — the HttpOnly change has zero functional impact, verified
directly rather than assumed from "no JS reads this cookie" alone.

$ python manage.py test apps.core.tests.test_security_settings
Result: PASS — 3/3 (an 11-character password rejected, a 12-character
password accepted, `CSRF_COOKIE_HTTPONLY` is `True`).

$ python manage.py test (full suite)
Result: PASS — 271 tests (up from 268).

$ manage.py check / makemigrations --check --dry-run
Result: PASS — no schema changes this unit.

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after one auto-fixed import-order issue in the new test
file; no real findings.

Dev database confirmed clean of the live-walkthrough's test user
(`secreview`) and test company (`Security Review Co`) before
committing.

## Tests

`python manage.py test` — 271 passed, 0 failures.

## Decisions

- Fixed only the two findings that were genuinely safe and
  zero-downside to apply immediately (`CSRF_COOKIE_HTTPONLY`, password
  minimum length). Everything else found — no role separation, no
  login-attempt rate limiting, the admin at its default `/admin/`
  path, no Content-Security-Policy header, no custom
  `AUTH_USER_MODEL` — is documented as a deliberate deferral with
  reasoning in `docs/SECURITY_REVIEW.md`, not silently dropped:
  - Role separation is Phase 6's own next unit (Unit 2,
    `docs/PERMISSIONS.md`), not a Unit 1 fix.
  - Rate-limiting/CSP are better suited to the reverse-proxy layer
    (Caddy, Phase 8) than a new Django dependency, given this app
    isn't yet deployed anywhere internet-reachable.
  - The admin path is easy to change later but not worth an
    operational-memory cost now for a non-deployed app.
  - The default `AUTH_USER_MODEL` is a Phase 2 trade-off already
    documented in `docs/DATABASE_DESIGN.md`, restated here so a
    security-focused reader doesn't mistake it for an oversight.
- Chose `min_length: 12` over adding complexity-composition rules
  (e.g. requiring symbols/mixed case) — length is the
  well-established stronger lever, and Django's existing validators
  (similarity, common-password, all-numeric) already cover the other
  common weak-password shapes.

## Errors

None found — this unit's audit surfaced hardening opportunities, not
active vulnerabilities. `manage.py check --deploy` was clean both
before and after.

## Lessons learned

- Django's test client silently disables CSRF enforcement by default.
  A settings change that specifically touches CSRF/cookie behavior
  can pass 268/268 tests while never having been exercised against
  real cookie/CSRF mechanics at all — worth remembering for any future
  security-adjacent settings change: verify live, don't trust the test
  suite's green checkmark alone for exactly the behavior it can't see.
- `manage.py check --deploy` is a genuinely useful first pass (caught
  nothing here because the production settings were already solid
  from Phase 0/1), but it only checks what Django itself knows to
  check — it doesn't substitute for a manual grep-based pass for
  things like raw SQL, `mark_safe`, or `@csrf_exempt`, which it has no
  way to see.

## Git

Branch: `security/csrf-and-password-hardening` (merged, deleted)
Commit: `a140a41`
Merged to `main`: `71ada2a` (regular merge commit, PR #43 — CI green,
`mergeStateStatus: CLEAN`; Sourcery rate-limited, no findings from it)

## Next

Phase 6 unit 2 — a practical role/permission model
(`docs/PERMISSIONS.md`), using Django's built-in Groups/Permissions
framework.
