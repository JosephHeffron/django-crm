# PHASE 07: DJANGO PRODUCTION CONTAINER (UNIT 1)

Started: 2026-09-13
Ended: 2026-09-14

## Objective

First unit of Phase 7, per the roadmap: a Django production container
(Gunicorn, non-root), matching the plan already laid out in
`docs/ARCHITECTURE.md`'s "Container architecture" section from Phase 0
("production image runs Gunicorn... a non-root user, and takes all
configuration from environment variables. No secrets baked into the
image").

## Files created / changed

- `Containerfile` — single-stage `python:3.12-slim` build. No
  multi-stage split: `psycopg2-binary` ships a self-contained wheel, so
  nothing here needs a C compiler or Postgres client headers, making a
  second stage pure unneeded complexity rather than a shortcut.
  Installs `requirements.txt` in its own layer (cached independently of
  app-code changes), creates a non-root `django` user (fixed UID 1000),
  runs as that user, and defaults to `gunicorn` with 3 workers logging
  to stdout/stderr.
- `.containerignore` — keeps the build context lean and guarantees
  `.env`, `requirements-dev.txt`, and dev-only files never end up in
  the image.
- `scripts/entrypoint.sh` — runs `migrate --noinput` then
  `collectstatic --noinput` before `exec`-ing the container's `CMD`
  (gunicorn). `set -e` so a failed migration stops the container
  instead of starting gunicorn against a half-migrated database.
- `requirements.txt` — added `gunicorn==26.2.0` (a real production
  dependency — the app actually runs under it in production, unlike
  the dev-only tools in `requirements-dev.txt`).

## Commands

$ `podman build -t django-crm:latest -f Containerfile .`
Result: PASS — built cleanly, no warnings besides pip's routine
root-user notice (expected and harmless at build time, since the
final `USER django` switch is what matters for runtime).

$ Full end-to-end live verification (not just "it builds"): created a
throwaway `postgres:18-alpine` container and a private Podman network,
ran `django-crm:latest` against it with realistic env vars (a
placeholder `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`), then:
  - Confirmed via container logs: all 22 migrations applied cleanly
    (including Phase 6's `crm.0005_seed_staff_group`), 131 static
    files collected, gunicorn started with 3 workers.
  - `curl http://localhost:8080/` → 301 to `https://...` — **initially
    looked wrong, verified before concluding otherwise**: this is
    `SECURE_SSL_REDIRECT=True` (already set in
    `config/settings/production.py` since Phase 6) correctly assuming
    a TLS-terminating reverse proxy in front (Caddy, Phase 8) that
    hasn't been built yet. Confirmed by re-requesting with
    `-H "X-Forwarded-Proto: https"` (simulating what Caddy will send)
    — got a normal `302` to the login page, full production security
    headers present (HSTS, `X-Content-Type-Options`,
    `X-Frame-Options`, `Referrer-Policy`,
    `Cross-Origin-Opener-Policy`), and the login page itself rendered
    correct HTML.
  - `podman exec crm-verify-app whoami` → `django` (uid 1000, not
    root) — confirmed directly, not assumed from the Containerfile's
    `USER` directive alone.
  - Restarted the app container: migrations correctly reported "No
    migrations to apply", static collection reported "131 unmodified"
    — confirms the entrypoint is safely idempotent across restarts,
    not just on first boot.
  - Final image size: 184 MB.
  - Cleaned up all throwaway containers/network afterward.

$ python manage.py check / ruff check . / ruff format --check . /
  bandit / pip-audit (with `gunicorn` now installed locally too)
Result: PASS — no issues; `pip-audit` confirms `gunicorn==26.2.0` has
no known vulnerabilities.

$ python manage.py test (full suite)
Result: PASS — 296 tests (unchanged; container/infra work doesn't add
Django test cases of its own — the verification above is the real test
for this unit, the same way it was for the usability-review unit's
live `curl` walkthrough).

## Tests

`python manage.py test` — 296 passed, 0 failures (no change from
before this unit).

## Decisions

- Single-stage `Containerfile`, not multi-stage — see Files above.
  Explicitly checked this wasn't a shortcut before deciding: confirmed
  `psycopg2-binary` (not `psycopg2`) is what's pinned, and that
  package's whole reason for existing is bundling `libpq` as a wheel,
  so there's no compiler step to isolate from the runtime image in the
  first place.
- `migrate`/`collectstatic` run from an entrypoint script at container
  **startup**, not baked in at build time — build time has no access
  to real secrets/env vars (and shouldn't need any), so anything
  requiring Django settings to load (both of these do) has to happen
  when the container actually starts with its real environment.
- Gunicorn worker count is a fixed, explicit `3`, not computed from
  `os.cpu_count()` — the deployment target (Raspberry Pi 5) is known
  and singular; a dynamic formula would be complexity spent on a
  problem (multiple deployment shapes) this project doesn't have.
- `DJANGO_SETTINGS_MODULE=config.settings.production` is baked into
  the image itself (an `ENV` line), not left to be set by whoever runs
  the container — this image only ever represents a production
  deployment (dev uses `manage.py runserver` directly, never this
  image), so hardcoding it removes an entire class of "someone forgot
  to set the env var and got `DEBUG=True` in prod" risk for free.

## Errors

None in the container itself. One thing that looked like an error at
first and wasn't: the initial plain-HTTP `curl` returning `301`
instead of an expected `302`-to-login. Investigated rather than
assumed — confirmed this is `SECURE_SSL_REDIRECT` correctly doing its
job (Phase 6's own security hardening), not a container misconfigu-
ration, by re-testing with the `X-Forwarded-Proto` header Caddy will
supply once Phase 8 exists.

## Lessons learned

- A production security setting from an earlier phase
  (`SECURE_SSL_REDIRECT`) can make a new unit's manual verification
  *look* broken when it's actually just being exercised in an
  environment (no reverse proxy yet) that setting wasn't designed to
  run in standalone. Worth checking the actual redirect target
  (`Location` header) before concluding something is wrong, the same
  "verify before reacting" discipline this project has applied to
  Sourcery findings all along.
- A container's own live logs (migrations applying, static files
  copying, gunicorn's worker-boot messages) are a direct, cheap source
  of verification — reading them caught the correct migration count
  (22, matching what `manage.py test` runs against) without needing a
  separate check.

## Git

Branch: `feature/django-production-container` (merged, deleted)
Commit: `1083af7`
Merged to `main`: `40e4a7f` (regular merge commit, PR #50 — CI green,
`mergeStateStatus: CLEAN`; the repo is now private, so Sourcery's free
tier no longer reviews it — expected, not an error, and this unit's
own live container verification already served as the equivalent
scrutiny)

## Next

Phase 7 unit 2 — PostgreSQL container with a persistent volume, plus a
complete `podman-compose` configuration wiring the Django and
PostgreSQL containers together (per `docs/ARCHITECTURE.md`'s
`compose.dev.yml`/`compose.prod.yml` split), verified with a real
`podman-compose up` rather than the manual two-container setup used to
verify this unit.
