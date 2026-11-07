# 0020 — A database cache, and hand-rolled login rate limiting

> **Amended 2026-11-06 by
> [ADR 0022](0022-caddy-on-the-host-network-for-real-client-addresses.md).**
> The per-IP count below relies on Caddy's peer being the visitor.
> Under rootless Podman with Caddy on the compose network, it was not:
> Podman's port forwarder rewrote every source address, so all
> visitors shared one bucket. Production Caddy now runs on the host
> network.
>
> **Also amended in the review of #208:** each counter update now runs
> under a PostgreSQL advisory lock on its key
> (`apps/users/throttle.py`'s `_serialize`). Two failures in two
> workers could otherwise both read N and both write N + 1, so a burst
> of guesses was undercounted.

*(Number reserved for this decision by `docs/VPS_DEPLOYMENT_PLAN.md`'s
ADR table; the recommendation is its D4.)*

## Context

`/accounts/login/` and `/admin/login/` take **unlimited password
guesses** (`docs/VPS_AUDIT.md` F-SEC-1 and F-PUB-2, both Verified).
There is no MFA until Phase 23, so a password is the only thing between
a guesser and the business's customer list. Phase 22.5 unit 3 puts
`crm.heffronexteriorservices.com` on the public internet, so this has
to land first.

Two facts shape the answer:

- **No `CACHES` is configured**, so Django falls back to per-process
  `LocMemCache`, and `Containerfile` runs **3 gunicorn workers**. A
  limiter on that cache counts roughly a third of the attempts and
  lets three times the guesses through — and it would pass a test
  suite, because the test runner is one process. F-SEC-1 named this.
- **Caddy terminates TLS and proxies to Django**, so `REMOTE_ADDR` is
  the proxy's address for every request. Without reading
  `X-Forwarded-For`, a per-IP limit is a single global bucket.

## Alternatives considered

- **`django-axes`.** The usual answer, and it does more than this
  (lockout records, admin integration, reset tooling). It is also a
  dependency with its own migrations, settings surface and upgrade
  path, for a business with seven accounts. `CLAUDE.md`'s complexity
  rule asks what problem a dependency solves that the simple thing
  does not: here, nothing we need.
- **`django-ratelimit`.** Lighter, but still a dependency, and it
  needs the same shared cache to be correct — so it solves the easy
  half and leaves the half that actually mattered.
- **Redis for the cache.** Named in `CLAUDE.md` as something not to
  add. A second service, its own memory, its own failure mode, on a
  2 vCPU box, to count login failures for seven people.
- **Blocking `/admin/login/` entirely.** Tempting, and it was
  impossible when the audit was written because the admin was the only
  way to create a user (F-CRM-1). #193 fixed that, so blocking it is
  now *possible* — but a superuser still needs the admin for
  `changepassword` recovery (ADR 0021) and schema-level work, and
  hiding a login page is not the same as limiting it.

## Decision

**A database cache, and about sixty lines of our own limiter.**

- `CACHES` uses `django.core.cache.backends.db.DatabaseCache` against a
  `crm_cache` table, created by a **migration** rather than a manual
  `createcachetable` step, so `manage.py migrate` — which the container
  entrypoint already runs — is the whole deploy path. Configured in
  `base.py`, so development and the tests use the same backend as
  production; a limiter that is only correct in production is a limiter
  nobody has tested.
- `apps/users/throttle.py` counts **failed** attempts under two keys,
  per IP and per username, in a 15-minute window, and refuses once
  either passes **10**. Both pages share it.
- The client IP comes from the **last** entry of `X-Forwarded-For` when
  that header is present, falling back to `REMOTE_ADDR`. Caddy appends
  the peer it actually spoke to, so the last entry is the real client
  even when the client sent a header of its own — taking the first
  entry would let anybody choose their own bucket.
- A refusal renders a plain page with **HTTP 429** and tells the person
  to wait, with no hint about whether the username exists.
- A **successful** sign-in clears both counters, so somebody who
  mistyped their password four times is not then punished for getting
  it right.

## Reason

The expensive part of this problem was never the counting — it was
having a counter that all three workers share and an IP that is
actually the client's. Both are configuration, and once they are right
the limiter is a dictionary with a timeout. A dependency would have
brought features for a scale this business will not reach, and would
not have fixed either of the two things that were wrong.

## Consequences

- **A table, not a service.** `crm_cache` lives in the same PostgreSQL
  the app already backs up and restores, so a cache that must survive
  a worker restart does, and nothing new needs monitoring.
- **Writes on failed logins.** A database write per failed attempt is
  slower than memory, and measurable only under an attack — which is
  the one time being correct matters more than being fast.
- **A known username can be locked out for 15 minutes** by somebody
  guessing against it deliberately. Accepted: the alternative, limiting
  by IP alone, lets a botnet spread its guesses across addresses and
  never trip anything. For seven accounts where the owner can set a
  password directly (ADR 0021), fifteen minutes is a smaller harm than
  an unlimited guessing window.
- **The counters are not transactionally atomic.** Django's cache
  `incr` is a get-then-set, so two simultaneous failures can count as
  one. Off by one on the way to a limit of ten does not change what the
  limit is for, and the alternative is a locking scheme around a
  counter of mistyped passwords.
- **`/admin/login/` is served by our own route**, declared before
  `admin/` in `config/urls.py` so it wins. `reverse("admin:login")`
  still resolves to the same path, so nothing in the admin notices.
- **The cache is now available to anything else that needs one** — the
  plan's phase 5 rate limit on the public booking page reuses it rather
  than introducing a second mechanism.

## Date

2026-11-03
