# PHASE 12: HEALTH-CHECK ENDPOINT (UNIT 1)

Started: 2026-09-17
Ended: 2026-09-17

## Objective

First of two Phase 12 units, per the roadmap: a health-check endpoint,
replacing Phase 7's plain-TCP-connect `web` healthcheck (both compose
files), which its own comment explicitly deferred to this phase.

## Files created / changed

- `apps/core/views.py` — new `HealthCheckView`: runs `SELECT 1` against
  the database, returns `{"status": "ok", "database": "ok"}` (200) or
  `{"status": "error", "database": "error"}` (503) on failure, with
  `logger.exception(...)` on the failure path. Unauthenticated
  (monitoring tooling can't log in), GET-only.
- `apps/core/urls.py` — wired at `health/` (`core:health`, resolves to
  `/health/`).
- `apps/core/tests/test_health.py` — new: anonymous-access healthy
  response, a mocked database failure returning 503, POST correctly
  405s.
- `compose.prod.yml` / `compose.dev.yml` — `web`'s healthcheck now
  calls `/health/` via `urllib` (stdlib, no new image dependency —
  same reasoning as the original TCP-connect check).
- `config/settings/production.py` — added `SECURE_REDIRECT_EXEMPT =
  [r"^health/$"]` (see Errors, below).

## Commands

$ Live verification in an isolated throwaway 3-container stack (never
  the real project directory).
First attempt: `web` reported **unhealthy**. `podman exec ... python
-c "import urllib.request; urllib.request.urlopen(...)"` reproduced
the exact failure directly: a `TimeoutError` deep inside an SSL
handshake. **Root cause**: production's `SECURE_SSL_REDIRECT = True`
301-redirected the plain-HTTP healthcheck request to `https://`, and
`urllib`'s default redirect-following behavior chased it — but `web`
itself never terminates TLS (only Caddy does), so attempting to
negotiate TLS directly against gunicorn just hangs until the client's
own timeout fires. Confirmed via `web`'s access log: a `301` on every
`GET /health/` attempt.
Fixed with `SECURE_REDIRECT_EXEMPT` — Django's built-in mechanism for
exactly this ("this path should never be redirected to HTTPS").

$ Re-verified after the fix — rebuilt the image explicitly
  (`podman-compose build web`, having learned in Phase 10 that a plain
  `up -d` reuses a stale image) and brought the stack back up.
Result: `web` reported **healthy**.
  - `podman exec ... urllib.request.urlopen('http://localhost:8000/health/')`
    → `{"status": "ok", "database": "ok"}`.
  - `curl -sk https://localhost:8443/health/` (through the full Caddy
    proxy chain) → same body, confirming the endpoint works both
    same-container (what the healthcheck itself does) and through the
    real external path.

$ Stopped the `db` container and waited for `web`'s own healthcheck to
  re-evaluate.
Result: `web` correctly transitioned to **unhealthy**;
  `curl -sk https://localhost:8443/health/` returned a real `503` —
  confirming this is now a genuine application-level check (detects a
  downed database), not just proof gunicorn is listening on a TCP
  port, which is what Phase 7's original check could only ever tell.

$ Cleanup: tore down the stack, removed volumes and the throwaway
  built image. A stray, overlapping `podman-compose up -d` process
  from before the fix (left running from an earlier interrupted test)
  was found and killed before rebuilding, to avoid ambiguity about
  which image version was actually running — confirmed via `ps aux`
  before proceeding, not assumed clean.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit).

$ `manage.py check --deploy` (production settings, realistic random
  secret key)
Result: PASS — zero issues, confirming `SECURE_REDIRECT_EXEMPT`
introduces no new deploy-check warnings.

$ `python manage.py test` (full suite)
Result: PASS — 299 tests (296 + 3 new for `HealthCheckView`).

## Tests

`python manage.py test` — 299 passed, 0 failures.

## Decisions

- `SECURE_REDIRECT_EXEMPT` over alternatives (e.g. having the
  healthcheck client set a fake `X-Forwarded-Proto: https` header, or
  disabling redirect-following in the `urllib` call) — it's the
  correct, idiomatic Django mechanism for "this specific path should
  never be forced to HTTPS," and doesn't require the healthcheck
  client to know anything about the app's own security configuration
  to work around it.
- The exemption is safe specifically because `web` publishes no host
  port in production (`compose.prod.yml`) — `/health/` is never
  reachable from outside the internal Podman network regardless of
  this setting, and the endpoint itself exposes nothing more sensitive
  than "ok"/"error" per component.
- Kept the response body minimal (`status`/`database` only, no stack
  traces, no connection details) — a monitoring tool has no legitimate
  need for more, and this is an unauthenticated endpoint.
- `logger.exception(...)` on the failure path, not just a silent
  503 — ties into Phase 12 unit 2's "application logging review,"
  giving that unit a real, already-existing example of what this
  project's logging looks like today to review, rather than a blank
  slate on the health-check path specifically.

## Errors

One real bug found and fixed during this unit's own live
verification — not from an automated review (repo is private, so
Sourcery doesn't review it; this unit's own live healthy/unhealthy
verification already served as the equivalent scrutiny):

1. `SECURE_SSL_REDIRECT` redirecting the same-container healthcheck
   request into an unreachable HTTPS endpoint, timing out the check
   entirely. Caught by actually running the healthcheck and observing
   `web` report unhealthy, then reproducing the exact failure directly
   via `podman exec`, not by reading the settings and assuming the
   interaction would be fine.

## Lessons learned

- A container-internal healthcheck that talks to the app directly
  (bypassing the reverse proxy on purpose, to test the app in
  isolation) can collide with security settings written assuming every
  request arrives *through* that proxy (`SECURE_SSL_REDIRECT`) — worth
  checking explicitly whenever a new same-container check is added
  to an app with proxy-aware security settings, not just assumed safe
  because the proxy-facing path already works.
- Reused Phase 10's own lesson directly: a plain `podman-compose up
  -d` after a source change doesn't rebuild the image — `build` (or
  `up -d --build`) is required, or the healthcheck (or anything else)
  will silently keep testing stale code. Applying an already-learned
  lesson correctly the first time here avoided a repeat of that
  specific confusion.

## Git

Branch: `feature/health-endpoint`
Commit: `3f30543`
Merged to `main`: `a47a8b6` (regular merge commit, PR #70 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live healthy/unhealthy verification already served as the
equivalent scrutiny)

## Next

Phase 12 unit 2 — an application logging review (what's logged, what
never is). Phase 12 is not yet complete — `docs/ROADMAP.md` stays
unchecked until unit 2 also merges.
