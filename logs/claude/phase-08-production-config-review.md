# PHASE 08: PRODUCTION CONFIGURATION REVIEW (UNIT 2)

Started: 2026-09-16
Ended: 2026-09-16

## Objective

Second and final unit of Phase 8, per the roadmap: a production
configuration review of the complete assembled stack now that Caddy
(unit 1) exists — Django settings, `Containerfile`, `compose.prod.yml`,
`Caddyfile` — matching the established `docs/DATABASE_REVIEW.md`/
`docs/SECURITY_REVIEW.md`/`docs/USABILITY_REVIEW.md` format: findings
ranked by severity, checked empirically, fixed where safe, deferred
with reasoning where not.

## Files created / changed

- `docs/PRODUCTION_CONFIG_REVIEW.md` — new. Full findings write-up (see
  below).
- `.env.example` — the one real fix this unit produced: removed the
  `DJANGO_SETTINGS_MODULE=config.settings.development` line, replaced
  with a comment explaining why it must stay unset.

## Commands

$ `manage.py check --deploy` against `config.settings.production`,
  run twice — first with a deliberately short/weak throwaway
  `DJANGO_SECRET_KEY` (confirmed the checker actually flags that, so a
  clean result afterward isn't just the checker being silent), then
  with a properly random one.
Result: PASS (zero issues) with the random key — confirms no
regression from Phase 7/8 unit 1's additions.

$ Traced how `DJANGO_SETTINGS_MODULE` actually reaches each container
  at runtime (image `ENV` vs. compose `env_file:` vs. `manage.py`/
  `wsgi.py`'s own `setdefault` fallback), rather than trusting the
  documented intent. **Found a real HIGH-severity bug this way**:
  `podman run --env-file` with `DJANGO_SETTINGS_MODULE=config.settings.
  development` set (matching `.env.example`'s original content)
  against the actual built production image
  (`localhost/django-crm:latest`) loaded `config.settings.development`
  — `DEBUG=True`, `SECURE_SSL_REDIRECT=False` — confirmed by reading
  real settings values back from inside a running Python process, not
  inferred from reading the settings files. `env_file:` wins over the
  `Containerfile`'s baked-in `ENV`, and this line carries no
  `change-me` placeholder, so a real deployer following the documented
  "copy `.env.example`, fill in real values" procedure had no reason
  to touch it.
- Fixed by removing the line from `.env.example` — `manage.py`/
  `wsgi.py`/`asgi.py` already `os.environ.setdefault(...)` to
  `config.settings.development` correctly for native dev when the var
  is unset, so nothing needed to change there.
- **Re-verified against the actual fixed file**, not just the
  reasoning: copied the real (post-fix) `.env.example` verbatim, filled
  in only the placeholders a real deployer would, ran it against the
  same built image — now correctly loads `config.settings.production`,
  `DEBUG=False`, `SECURE_SSL_REDIRECT=True`.

$ `grep` across `templates/`/`static/` for inline `<script>`/`<style>`
  and external resource references, to assess whether a
  Content-Security-Policy header could be added safely at the Caddy
  layer (a Phase 6 `docs/SECURITY_REVIEW.md` deferred item, revisited
  now that Caddy exists).
Result: no external references, no inline scripts in this project's
own templates — but Django's built-in `/admin/` (actively used) ships
its own inline `<script>` blocks in its base template, and this
environment has no way to check whether a strict `script-src` CSP
would silently break an admin widget in a real browser (`curl` only
sees HTTP status, not console-level CSP violations). Kept deferred
rather than ship an unverified change.

$ `podman run --entrypoint sh caddy:2.11.4-alpine -c whoami`
Result: `root` — the official image's default, no non-root variant
shipped. Documented as an accepted, substantially-mitigated trade-off
(rootless Podman's user-namespace isolation already narrows the real
blast radius) rather than building/maintaining a custom non-root image
for it.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config -q`
  / `pip-audit`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated to this unit, confirmed as the same baseline from
Phase 7's own phase logs).

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — this unit is a review plus a
one-line env-file fix, not application code).

## Tests

`python manage.py test` — 296 passed, 0 failures.

## Decisions

- Removed `DJANGO_SETTINGS_MODULE` from `.env.example` entirely rather
  than, say, adding a warning comment next to it — the safest fix here
  is for the file to simply not carry a value that can silently
  override two already-correct defaults (`manage.py`/`wsgi.py`'s
  `setdefault`, the `Containerfile`'s `ENV`). Removing the footgun
  outright is more robust than trusting a comment to be read before
  the line is copied.
- CSP stays deferred rather than shipped speculatively — this
  environment's tooling (`curl`, HTTP status codes) cannot detect a
  silently-broken admin widget the way a real browser's console would.
  Shipping an unverified assumption about Django admin's inline script
  behavior would violate this project's "never claim a test passed
  unless it was actually executed" rule in spirit, even though no
  literal test exists to run.
- Caddy running as root inside its own container is documented, not
  "fixed" with a custom image — the marginal security gain doesn't
  currently justify the ongoing maintenance cost of tracking a custom
  Caddy build against upstream releases, given rootless Podman already
  substantially narrows what "root inside the container" actually
  means on the host.

## Errors

One real, substantive bug found and fixed during this unit's own live
verification — not from an automated review (repo is private, so
Sourcery doesn't review it; this unit's own live verification served
the same purpose):

1. **`.env.example`'s `DJANGO_SETTINGS_MODULE=config.settings.
   development` line would silently downgrade a real production
   deployment to `DEBUG=True`.** Caught by actually tracing environment
   variable precedence end-to-end and running the real built image
   against an env file matching the documented deployment procedure —
   not by reading the settings files and assuming the intent matched
   reality. This is exactly the class of bug Phase 7/8 unit 1's own
   live verification didn't catch, because that verification used a
   hand-written throwaway env file that already had the correct value
   — it never exercised the actual "copy `.env.example`" procedure a
   real deployer follows.

## Lessons learned

- Reading a settings/compose file and reasoning about what "should"
  happen isn't the same as tracing what actually happens at runtime —
  this unit's one real finding only surfaced by empirically checking
  environment-variable precedence across image `ENV`, compose
  `env_file:`, and Python's own `setdefault` fallback, not by re-
  reading `config/settings/production.py` more carefully.
- A prior unit's live verification can still miss a real bug if its
  test fixtures (a hand-crafted throwaway `.env`) don't match the
  actual documented procedure a real user would follow — worth
  occasionally testing against the literal, unmodified template file
  a deployer would copy, not just a fixture built to already be
  correct.
- Some findings are correctly left deferred not because the fix is
  hard, but because *verifying* the fix is safe requires tooling
  (a real browser) this environment doesn't have — shipping an
  unverified change here would be worse than documenting the gap
  honestly.

## Git

Branch: `feature/production-config-review`
Commit: `4f3a190`
Merged to `main`: `0df7b15` (regular merge commit, PR #56 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live verification already served as the equivalent scrutiny)

## Next

**Phase 8 (Caddy and HTTPS) is now fully complete** (both units: Caddy
container, production configuration review). Next is Phase 9 — ARM64
deployment: ARM64 compatibility audit (`docs/ARM64_REVIEW.md`), ARM64
image builds via `qemu-user-static`, repeatable cross-architecture
validation (`docs/ARM64_TESTING.md`).
