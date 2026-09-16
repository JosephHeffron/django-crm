# PHASE 07: POSTGRESQL CONTAINER + PODMAN-COMPOSE (UNIT 2)

Started: 2026-09-16
Ended: 2026-09-16

## Objective

Second and final unit of Phase 7, per the roadmap: a PostgreSQL
container with a persistent volume, plus a complete `podman-compose`
configuration wiring it together with the Django production container
from Unit 1 — matching `docs/ARCHITECTURE.md`'s "Container
architecture" section, which names both `compose.dev.yml` (local/
staging use) and `compose.prod.yml` (production, the stricter of the
two: no unnecessary host port exposure, health checks, restart
policies).

## Files created / changed

- `compose.prod.yml` — new. `db` (postgres:18-alpine, named volume,
  `pg_isready` healthcheck, `restart: unless-stopped`) and `web` (built
  from `Containerfile`, `depends_on: db: condition: service_healthy`,
  a plain-TCP-connect healthcheck since no dedicated health endpoint
  exists yet — that's Phase 12). **`web` publishes no host port** —
  the correct final shape once Caddy (Phase 8) exists to proxy to it
  over the internal network, not a placeholder.
- `compose.dev.yml` — new. Same two services, but both publish a host
  port (`web` 8000, `db` 5432) for local/staging inspection, since
  there's no Caddy yet to reach `web` through and direct `psql` access
  to `db` is genuinely useful while testing the stack. Uses separate
  volume names from `compose.prod.yml` so the two stacks never share
  state.
- `.env.example` — added a comment clarifying that `POSTGRES_HOST=
  localhost` is correct for native dev, but gets overridden to `db`
  (the compose service name) for the containerized `web` service.

## Commands

$ `podman-compose -f <test-copy> config` — validated both compose
  files' YAML/schema before attempting a real `up`. **Caught a real
  bug this way**: I had written `containerfile: Containerfile` under
  `build:`, but the Compose Specification's actual key — used by both
  Docker Compose and Podman Compose, regardless of the file's literal
  name — is `dockerfile:`. Verified this was the correct key before
  fixing it (didn't just guess), then fixed both files.

$ Full live verification against a throwaway `.env` (never the real,
  already-existing local `.env` — a separate `.env.compose-verify`
  file was used instead, to avoid touching real local secrets) and a
  test-only copy of `compose.prod.yml` pointing at it:
  - First `up` attempt: **`db` exited immediately** with a real error
    from the official `postgres:18-alpine` image — PostgreSQL 18+
    changed its expected volume mount convention from
    `/var/lib/postgresql/data` to a single mount at
    `/var/lib/postgresql` (the image manages its own major-version
    subdirectory underneath, for `pg_ctlcluster`/`pg_upgrade`
    compatibility). Confirmed this was the actual cause by reading the
    image's own error message in full, not guessed — then fixed the
    mount path in both compose files and documented why directly in
    each file's own comments, not just in this log.
  - Second attempt: both containers came up `healthy`. Container logs
    confirmed all 22 migrations applied and 131 static files
    collected — DNS-based service discovery (`POSTGRES_HOST: db`)
    resolved correctly across the compose network.
  - **The actual persistence guarantee this unit exists to deliver**,
    verified directly rather than assumed from "the volume is named":
    inserted a marker row directly via `podman exec ... psql`, ran
    `podman-compose down` (removing both containers, keeping the named
    volumes), brought the stack back up from scratch, and confirmed
    the marker row was still there.
  - Verified `web` actually serves real Django pages (not just "the
    process is running") from *inside* the container via
    `podman exec ... python -c "urllib.request..."` — `compose.prod.yml`
    deliberately publishes no host port, so this is the only way to
    check without changing the file just for testing.
  - All throwaway containers, the built test image, named test
    volumes, and two anonymous leftover volumes (`Anonymous: true`,
    auto-created by the Postgres image's own `VOLUME` declaration
    during earlier ephemeral test runs — checked their metadata before
    removing them, not assumed safe) were cleaned up afterward.

$ python3 -c "import yaml; yaml.safe_load(...)" on both compose files
Result: PASS — valid YAML (a cheap, fast check run before the much
slower full `podman-compose up` cycle each time).

$ manage.py check / ruff check . / ruff format --check . / bandit /
  pip-audit
Result: PASS — no issues (this unit touches no Python/Django source,
only compose YAML and an env-file comment, so these were run for
consistency with the project's standard per-unit verification, not
because anything here was expected to be affected).

$ python manage.py test (full suite)
Result: PASS — 296 tests (unchanged — infra work adds no Django test
cases; the live compose verification above is this unit's real test,
the same as Unit 1's).

## Tests

`python manage.py test` — 296 passed, 0 failures.

## Decisions

- `web` publishes no host port in `compose.prod.yml` — the correct
  final production shape (Caddy, Phase 8, will be the only externally
  reachable container), verified without needing a host port by
  checking from inside the container via `podman exec`, rather than
  temporarily exposing a port "just for now" and having to remember to
  remove it later. Prefers a design that's already correct today over
  one that needs a follow-up cleanup step in Phase 8.
- `compose.dev.yml` runs the *same* production-configured image as
  `compose.prod.yml` (not a separate `DEBUG=True` variant) — its only
  real difference is published ports, for inspecting the containerized
  stack itself. This project's actual day-to-day development remains
  native (pyenv + local PostgreSQL, `manage.py runserver`), unchanged
  since Phase 0 — `compose.dev.yml` is for testing the container stack
  the same way a future staging environment would run it, not a
  replacement for that native workflow. Documented this distinction
  directly in the file, not just decided silently.
- No dedicated health-endpoint-based healthcheck for `web` — a plain
  TCP connect to gunicorn's own bound port is sufficient today and
  avoids adding `curl`/`wget` to the image just for this; a real
  health endpoint is explicitly Phase 12's job.
- Verified with a throwaway `.env.compose-verify` file rather than the
  project's real, already-existing `.env` — the real file has actual
  local secrets in it and this unit's verification had no reason to
  touch it.

## Errors

Two real, substantive things found and fixed during this unit's own
verification — not from an automated review (the repo is private now,
so Sourcery doesn't review it; this unit's live verification served
the same purpose):

1. **`containerfile:` is not a valid Compose Specification key** — the
   correct key is `dockerfile:`, regardless of the actual file's name
   or whether Docker or Podman is doing the building. Caught by
   running `podman-compose config` (a fast, cheap validation step)
   before attempting a real `up`, not by a failed build.
2. **PostgreSQL 18's official image expects a different volume mount
   point** than earlier major versions — `/var/lib/postgresql`, not
   `/var/lib/postgresql/data`. Caught by reading the `db` container's
   own exit-1 logs in full (the image's own error message names the
   correct fix directly), not by guessing from general Postgres
   knowledge that happened to be out of date for this specific image
   version.

## Lessons learned

- `podman-compose config` (schema validation, no containers started)
  is a genuinely useful, fast first check before the much slower
  `up` cycle — worth running by default for any new or changed compose
  file, the same way `manage.py check`/`makemigrations --check` are
  already a standard first step for Django changes in this project.
- An official base image's own conventions can change between major
  versions in ways that only surface at actual container-start time,
  not at build time or from reading generic documentation about the
  software — `postgres:18-alpine`'s changed volume-mount expectation
  wouldn't have been caught by anything short of actually running the
  container and reading its logs.
- The single most direct way to verify "does the persistent volume
  actually persist" is to actually destroy and recreate the containers
  and check the data survived — not to reason about it from the
  compose file's `volumes:` section looking correct on paper.

## Git

Branch: `feature/postgres-podman-compose` (merged, deleted)
Commit: `f5a177c`
Merged to `main`: `7f0bc02` (regular merge commit, PR #52 — CI green,
`mergeStateStatus: CLEAN`; the repo is private now, so Sourcery doesn't
review it — expected, not an error, and this unit's own live
destroy-and-recreate verification already served as the equivalent
scrutiny)

## Next

Phase 7 is now fully complete (both units: Django production
container, PostgreSQL container + podman-compose). Next is Phase 8 —
Caddy and HTTPS: reverse proxy, HTTPS termination, static/media file
serving, security headers, a production configuration review — the
phase that will finally let `web`'s published-nowhere design in
`compose.prod.yml` actually be reached from outside the host.
