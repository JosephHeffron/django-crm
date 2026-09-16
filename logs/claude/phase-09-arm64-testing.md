# PHASE 09: ARM64 IMAGE BUILD + CROSS-ARCHITECTURE VALIDATION (UNIT 2)

Started: 2026-09-16
Ended: 2026-09-16

## Objective

Second and final unit of Phase 9, per the roadmap: ARM64 image builds
via `qemu-user-static` and repeatable cross-architecture validation
(`docs/ARM64_TESTING.md`) — the functional proof `docs/ARM64_REVIEW.md`
(unit 1) deliberately deferred. Unit 1 confirmed every base image and
dependency *supports* `linux/arm64/v8`; this unit proves the
*application* actually works on it.

## Files created / changed

- `scripts/test-arm64.sh` — new. A repeatable, self-verifying script:
  builds the production `Containerfile` for `linux/arm64`, runs the
  full `db`+`web`+`caddy` stack under emulation, and asserts (exits
  non-zero with a `FAIL:` message if not) that migrations ran, static
  files collected, and a real page renders both directly through
  gunicorn and through the full Caddy proxy chain. Cleans up
  unconditionally via a `trap`, on every exit path.
- `docs/ARM64_TESTING.md` — new. Documents the procedure and both real
  bugs found while building it (see below).

## Commands

$ `./scripts/test-arm64.sh` — first run.
Result: **failed** at the Caddy step —
`podman network connect --alias web ...` errored with `network is
already connected` (the `web` container was already attached to the
test network from its own `podman run`, making the separate `connect`
call both redundant and wrong). Fixed by aliasing at container-
creation time instead (`--network-alias web` on `web`'s own `podman
run`), removing the separate `connect` call.

$ `./scripts/test-arm64.sh` — second run, after the fix.
Result: **PASSED** end to end:
```
db ready (aarch64)
web ready (aarch64)
migrations + collectstatic confirmed
gunicorn served a real page: <title>Log in</title>
caddy ready (aarch64)
full db+web+caddy stack served a real page through the proxy: <title>Log in</title>

=== ARM64 cross-architecture validation PASSED ===
```

$ **Found a real environment bug while building this, separately from
  the script bug above**: an earlier interactive run of the same
  steps by hand (`podman pull --platform linux/arm64
  docker.io/library/postgres:18-alpine`) silently overwrote this
  workstation's shared local `postgres:18-alpine` tag with the
  `arm64` variant — confirmed directly via `podman inspect
  docker.io/library/postgres:18-alpine --format
  '{{.Architecture}}'`, which reported `arm64` after the pull, with
  the native `amd64` image (the one this project's actual dev/prod
  compose stacks depend on) demoted to a dangling `<none> <none>`
  entry. Left uncorrected, the next real `podman-compose -f
  compose.dev.yml up` on this workstation would have silently run
  Postgres under unnecessary qemu emulation — not broken outright
  (the registered `binfmt_misc` handlers still execute a foreign-arch
  binary), but a real, easy-to-miss performance regression to actual
  day-to-day development with no obvious error pointing at the cause.
  Fixed immediately by `podman pull --platform linux/amd64
  <image>` for both `postgres:18-alpine` and `caddy:2.11.4-alpine`,
  restoring the native tags — confirmed via the same `podman inspect`
  check, now reporting `amd64` again.

$ Built this restoration into `scripts/test-arm64.sh`'s cleanup
  `trap` **unconditionally**, not as an optional nicety — verified it
  actually fires on both exit paths: the first (failed) run above
  still correctly restored both tags to `amd64`, and the second
  (passed) run did too.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit).

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — this unit is a script + review
doc, no application code).

## Tests

`python manage.py test` — 296 passed, 0 failures.
`./scripts/test-arm64.sh` — PASSED (the unit's actual functional test).

## Decisions

- Made the `amd64` tag restoration **unconditional** in the cleanup
  trap, not something the script only does on a clean exit — the bug
  it guards against (a workstation's real dev images silently
  demoted) can happen regardless of how the script itself ends, so the
  fix has to run regardless too.
- Asserted on `web`'s actual log content (`grep -q "Running
  migrations"` / `"static files copied"`), not just on the container
  staying in a `running` state — a failed migration inside
  `entrypoint.sh`'s `set -e` would exit the container, and `podman ps`
  alone doesn't distinguish that from a healthy, still-starting one
  without checking what actually happened.
- Extended validation to the full 3-container stack (added Caddy),
  not just `web` in isolation — the roadmap explicitly asks for
  "repeatable cross-architecture validation" of the deployment, and
  Phase 8's own Caddy↔Django header-trust interplay is exactly the
  kind of thing that's worth re-confirming still works under a
  different architecture, not assumed to carry over unchanged.

## Errors

Two real, substantive things found and fixed during this unit's own
live verification — not from an automated review (repo is private, so
Sourcery doesn't review it; this unit's own live verification served
the same purpose):

1. **`podman pull --platform linux/arm64` silently overwrites a
   shared local image tag** — a real environment-hygiene bug that
   would have degraded this workstation's actual native dev
   performance with no obvious error message pointing at the cause.
   Caught by explicitly checking `podman inspect ...
   {{.Architecture}}` after the fact, not assumed safe because the
   pull itself succeeded.
2. **A redundant, incorrectly-ordered `podman network connect` call**
   in the first draft of `scripts/test-arm64.sh` — caught by actually
   running the finished script end to end rather than trusting that
   each individually-verified interactive step would compose
   correctly into a script.

## Lessons learned

- A multi-arch base image's *shared* local tag is a shared, mutable
  resource — pulling a specific `--platform` under that tag doesn't
  create a separate reference alongside the existing one, it replaces
  it. Any workflow that pulls a non-native platform for an image also
  used natively elsewhere on the same machine needs an explicit,
  reliable restoration step, not just an assumption that Podman's
  local cache "just works" per-architecture.
- Running a finished script for real, not just its individual steps
  interactively, is what surfaces ordering/state bugs (the redundant
  `network connect`) that look fine in isolation — consistent with
  this project's broader theme of live verification catching things
  static review alone wouldn't.
- A cleanup routine that only guards the "happy path" isn't actually a
  safety net — this unit's tag-restoration fix only matters because it
  runs unconditionally, confirmed by deliberately checking it against
  a real failed run, not just the successful one.

## Git

Branch: `feature/arm64-testing`
Commit: `9bf8bfb`
Merged to `main`: `e0b28e9` (regular merge commit, PR #60 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live script execution already served as the equivalent scrutiny)

## Next

**Phase 9 (ARM64 deployment) is now fully complete** (both units:
ARM64 compatibility review, ARM64 image build + cross-architecture
validation). Next is Phase 10 — systemd on the Raspberry Pi: a
production systemd unit, and a safe non-destructive deployment script
with rollback.
