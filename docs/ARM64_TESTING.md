# ARM64 cross-architecture validation

Phase 9 unit 2 — a repeatable procedure for validating the full
`db`+`web`+`caddy` stack on `linux/arm64` before it ever reaches the
physical Raspberry Pi 5, per `docs/ARCHITECTURE.md`'s "ARM64
deployment strategy". `docs/ARM64_REVIEW.md` (Phase 9 unit 1) already
confirmed every base image and dependency *supports* `linux/arm64/v8`;
this unit proves the *application* actually works on it — real
migrations, real static files, a real page served through the real
reverse proxy — not just that the pieces are individually compatible.

## Running it

```
./scripts/test-arm64.sh
```

Requires `podman` and `qemu-user-static` with its `binfmt_misc`
handlers registered (already set up on this workstation since Phase
0 — see `docs/ARM64_REVIEW.md` for how to check). No real `.env`,
credentials, or data are used or touched — everything the script
creates is named `arm64-test-*` and is guaranteed removed when the
script exits, success or failure, via a `trap`-based cleanup.

The script builds the production `Containerfile` for `linux/arm64`,
then runs the full stack under emulation and checks each stage
actually worked, not just that each container stayed up:

1. Builds `django-crm-arm64:test` for `linux/arm64`.
2. Starts a throwaway PostgreSQL container (`linux/arm64`), waits for
   `pg_isready`.
3. Starts the Django `web` container (`linux/arm64`) against it —
   `entrypoint.sh` runs `migrate`/`collectstatic` before gunicorn ever
   starts, same as production.
4. Confirms `web`'s own logs actually show `Running migrations` and
   `static files copied` — not just that the container is "running"
   (a crashed migration inside `entrypoint.sh`'s `set -e` would exit
   the container, which `podman ps` alone wouldn't distinguish from a
   successful, still-starting one without checking the log content).
5. Curls a real page directly from gunicorn (`/accounts/login/`,
   `X-Forwarded-Proto: https` set manually since there's no proxy
   yet at this point) and asserts the actual page title.
6. Adds a Caddy container (`linux/arm64`, `Caddyfile.dev`) in front,
   aliased so its hardcoded `reverse_proxy web:8000` target resolves.
7. Curls the same page again, this time through the full proxy chain,
   and asserts the same title — proving the complete `db`→`web`→
   `caddy` path, not just `web` in isolation.
8. Tears everything down.

Exits non-zero (with a `FAIL:` message naming what to check) if any
assertion fails — this is a real pass/fail check, not just a log to
read afterward.

## A real bug this validation surfaced (and now guards against)

While building this script, an earlier interactive run of the same
steps by hand — `podman pull --platform linux/arm64
docker.io/library/postgres:18-alpine` — **silently overwrote this
workstation's local `postgres:18-alpine` tag** with the `arm64`
variant. `podman images` afterward showed the *native* `amd64` image
this workstation's actual dev/prod compose stacks depend on demoted to
`<none> <none>` (dangling), with the shared tag now pointing at
`arm64` instead. Confirmed directly: `podman inspect
docker.io/library/postgres:18-alpine --format '{{.Architecture}}'`
reported `arm64` after the pull, not `amd64`. Left alone, the next
`podman-compose -f compose.dev.yml up` on this machine would have
silently run Postgres under unnecessary, much slower qemu emulation —
not broken outright (this workstation's registered `binfmt_misc`
handlers make a foreign-arch binary still *execute*), but a real,
easy-to-miss performance regression to actual day-to-day development,
with no obvious error to point at the cause.

**Fix**: `podman pull --platform linux/amd64 <image>` for both
`postgres:18-alpine` and `caddy:2.11.4-alpine` immediately restores
the native tag. `scripts/test-arm64.sh` runs this **unconditionally in
its cleanup trap** — not as an optional nicety, but as a correctness
requirement for the script to be safe to run at all, on every exit
path (success, an assertion failure, or `Ctrl-C`). Verified live: an
injected failure partway through the script (the network-alias bug
below) still correctly restored both tags via the trap.

## A real script bug this validation caught in itself

The first full run of the finished script failed at the Caddy step:
`podman network connect --alias web ...` errored with `network is
already connected` — the `web` container was already on the test
network from its own `podman run --network ...`, so a separate
`connect` call was redundant and wrong. Fixed by aliasing `web` at
container-creation time instead (`--network-alias web` on `web`'s own
`podman run`), removing the separate `connect` call entirely. Confirms
the value of actually running the finished script rather than trusting
that each individually-tested step would compose correctly — the
cleanup trap also correctly restored the `amd64` tags on this failed
run, proving that safeguard works on the failure path too, not just
the success path.

## Result

A full, clean run of `scripts/test-arm64.sh` (after the fix above)
completed end to end:

```
db ready (aarch64)
web ready (aarch64)
migrations + collectstatic confirmed
gunicorn served a real page: <title>Log in</title>
caddy ready (aarch64)
full db+web+caddy stack served a real page through the proxy: <title>Log in</title>

=== ARM64 cross-architecture validation PASSED ===
```

## Limitations (same as `docs/ARM64_REVIEW.md`, still true here)

`qemu-user-static` emulation proves functional correctness, not
performance — this script says nothing about real throughput, memory
pressure, or timing on the Raspberry Pi 5's actual ARM cores, and makes
no such claim. No physical Pi exists yet for this project; that
remains a later, separate validation once hardware is acquired.

## Recommendation

The complete `db`+`web`+`caddy` stack — migrations, static files, the
one compiled dependency, the full reverse-proxy path — has now been
proven to actually work on `linux/arm64` under emulation, not just
individually compatible on paper. `scripts/test-arm64.sh` is safe to
re-run at any point (e.g., after a future dependency bump, or a
`Containerfile`/`Caddyfile` change) as a fast pre-hardware regression
check. Phase 9's roadmap scope is now complete; a real Raspberry Pi 5
is the next hard dependency for anything beyond this.
