# PHASE 10: DEPLOYMENT SCRIPT WITH ROLLBACK (UNIT 2)

Started: 2026-09-16
Ended: 2026-09-17

## Objective

Second and final unit of Phase 10, per the roadmap: a safe,
non-destructive deployment script with rollback (`scripts/deploy.sh`),
per `docs/ARCHITECTURE.md`'s "Production deployment architecture"
("pull the intended git revision, build/pull ARM64 images, run
migrations, restart, verify health, and support rollback") and
`CLAUDE.md`'s DEPLOYMENT RULES ("Deployments are scripted,
non-destructive, and reviewable... with a documented rollback path").

## Files created / changed

- `scripts/deploy.sh` — new. `<git-ref>` deploys a specific revision
  (tag/commit recommended, branch name also resolved); `rollback`
  reverts to the previously-deployed revision; `status` reports
  current revision/health without changing anything. Refuses to run
  against an uncommitted working tree. Auto-rolls-back on a failed
  health check after a deploy.
- `.gitignore` — added `/.deploy-last-good-ref` (the script's rollback
  marker — host-local state, never meaningful to commit).

## Commands

This unit's real work was almost entirely live debugging, not
first-draft implementation — the first version of `deploy.sh` looked
reasonable on paper and was wrong in four different ways, each only
found by actually exercising the failure/rollback path against a real
throwaway git clone with a deliberately broken commit (bad
`config/settings/production.py`, `NameError` at import time). A
happy-path-only test (deploy something that already works) would not
have caught any of these.

$ First full test cycle: deploy a good commit, then deploy the broken
  one, expecting auto-rollback.
Result: **web kept running the OLD, broken code** after "rollback" —
confirmed via `podman inspect <container> --format '{{.Image}}'`
showing an image ID hours older than the just-rebuilt tag.
**Root cause 1**: `systemctl restart` (`ExecStart=podman-compose up
-d`) reuses an already-existing container as-is, even a crashed one,
rather than recreating it from a freshly-built image.
**Fix attempt 1**: explicit `systemctl stop` before `start`.

$ Re-ran the same cycle.
Result: **still ran the old code** — same stale-image symptom.
**Root cause 2**: `systemctl stop` on a unit already in `failed`
state (from the previous attempt's `TimeoutStartSec` timeout) is a
no-op — it does not run `ExecStop`. This is precisely the state a
rollback runs in, right after a failed deploy — not an edge case.
**Fix attempt 2**: call `podman-compose down` directly (bypassing
`systemctl stop`), then `systemctl start`.

$ Re-ran again.
Result: **containers were entirely absent** ("db is 'missing'")
despite `systemctl start` returning success. `systemctl status`
showed the unit `active (exited)` — but from an unrelated, much
earlier successful start, not this one.
**Root cause 3**: `systemctl start` on a unit systemd already
*believes* is `active` (`RemainAfterExit=yes`) is *also* a no-op,
regardless of whether the containers underneath were separately torn
down. All three root causes share one underlying fact: a
`Type=oneshot`/`RemainAfterExit=yes` unit's "active" state only ever
reflects "`ExecStart` last exited 0" — systemd never tracks whether
the containers it started are still alive afterward.
**Real fix**: stopped going through `systemctl` for orchestration
entirely — `deploy.sh` now calls `podman-compose down`/`up -d`
directly. `systemd/crm.service` (Phase 10 unit 1) is untouched; it
still does its actual job (start the stack on boot), `deploy.sh` just
doesn't route through it.

$ Re-ran again with the direct-podman-compose version.
Result: `podman-compose up -d` **hung for over 20 minutes**, never
returning. **Root cause 4**: `caddy`'s `depends_on: web: condition:
service_healthy` (in both compose files) makes `podman-compose up -d`
block until `web` passes its healthcheck — and since `web` never does
(the deliberately broken commit), `up -d` has no timeout of its own
and just waits forever.
**Fix**: wrapped the call in `timeout 300`, treating a timeout as
non-fatal — the script's own health-check loop is the real arbiter of
success/failure either way; this just stops `up -d` itself from being
the thing that hangs.

$ Full scenario suite, re-run end to end after all four fixes, against
  a real throwaway git clone (never the actual project working tree):
  - Deploy a good commit → succeeds, containers healthy, previous ref
    recorded to `.deploy-last-good-ref`.
  - Deploy the broken commit → `up -d` correctly times out at 300s,
    health check correctly fails, script correctly rebuilds and
    rolls back to the previous good commit, **that rollback's own
    health check genuinely passes** (real containers, real image IDs
    matching the good commit — checked directly, not assumed), script
    exits non-zero (deploy failed, even though rollback succeeded).
  - `./scripts/deploy.sh rollback` (standalone) — works correctly on
    its own.
  - `./scripts/deploy.sh status` — reports current revision, rollback
    target, and real container health without changing anything.
  - Dirty working tree (`echo >> README.md`) → correctly refused with
    a clear error, nothing touched.
Result: **PASS** on all five scenarios.

$ Cleanup: tore down all throwaway containers, removed all throwaway
  named volumes (both `_dev`- and prod-named, from earlier test
  variations), removed the throwaway `django-crm_web:latest` image,
  removed the throwaway git clone, confirmed no stray systemd user
  units remained. Also re-confirmed the local workstation's shared
  `python:3.12-slim`/`postgres:18-alpine`/`caddy:2.11.4-alpine` tags
  were still `amd64` (no `--platform` pulls happened during this
  unit's testing, so no repeat of Phase 9 unit 2's tag-collision
  issue) — checked directly, not assumed.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit).

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — this unit is a deploy script,
no application code).

## Tests

`python manage.py test` — 296 passed, 0 failures.
`scripts/deploy.sh`'s own full scenario suite (see Commands) — the
unit's real test, since there's no Django test runner for a shell
script's interaction with systemd/podman.

## Decisions

- `deploy.sh` drives `podman-compose` directly rather than through
  `systemctl {restart,stop,start} crm.service` — the central decision
  of this unit, forced by three separate, live-confirmed failures of
  the systemctl-based approach (see Commands). `systemd/crm.service`
  keeps its own real purpose (boot-time start) unchanged.
- `podman-compose up -d` is wrapped in `timeout 300`, with a timeout
  treated as non-fatal — the script's own health-check loop (checking
  real `podman inspect ... Health.Status`, not systemd or
  podman-compose's own success/failure signal) is the actual arbiter
  throughout. This was a deliberate design principle reinforced by
  every bug found this unit: never trust a tool's own "I succeeded"
  signal when the actual, directly-checkable state (a real running,
  healthy container) is available instead.
- Migrations are not a separate step in `deploy.sh` — `scripts/
  entrypoint.sh` already runs `migrate`/`collectstatic` on every `web`
  container start. Duplicating that here would just be a second place
  for the two to drift out of sync.
- `require_clean_tree` refuses to deploy over uncommitted changes —
  `git checkout --detach` doesn't need this to avoid data loss (it
  would refuse on its own for a conflicting change), but this makes
  the refusal an explicit, clear, early error rather than a possibly
  confusing git error mid-deploy.
- `SERVICE`/`COMPOSE_FILE` environment-variable overrides (both
  defaulting to the real production values) exist specifically to make
  this kind of throwaway, non-destructive live testing possible
  without ever touching the real compose files or systemd unit.

## Errors

Four real, substantive bugs found and fixed during this unit's own
live verification — not from an automated review (repo is private, so
Sourcery doesn't review it; this unit's own repeated, adversarial live
testing served the same purpose, more thoroughly than a single review
pass would have):

1. `systemctl restart` silently reuses a stale container instead of
   recreating it from a newly-built image.
2. `systemctl stop` on an already-`failed` unit is a no-op — doesn't
   run `ExecStop`.
3. `systemctl start` on a unit systemd believes is already `active` is
   also a no-op, independent of the real container state underneath.
4. `podman-compose up -d` can hang indefinitely when a `depends_on:
   condition: service_healthy` dependency never becomes healthy.

## Lessons learned

- A `Type=oneshot`/`RemainAfterExit=yes` systemd unit's "active" state
  is a claim about the past (did `ExecStart` last exit 0), never a
  live view of the present — any tooling built on top of such a unit
  that needs to know "is this actually running right now" has to check
  the real underlying state directly (here: `podman inspect`), not
  systemd's own belief.
- Testing only the deploy of a *working* revision — the natural first
  thing to try — would have shipped a deployment script whose entire
  reason for existing (safe rollback on a bad deploy) silently didn't
  work. The rollback path is the one that most needs a deliberately
  broken test case, not the happy path.
- A tool's own "operation succeeded" signal (`systemctl start` exit 0,
  `podman-compose up -d` if it hadn't been wrapped in `timeout`) is
  not the same as the outcome actually being correct — this unit's
  entire debugging arc was, in effect, repeatedly discovering that a
  "succeeded" signal from one layer didn't mean what it appeared to
  mean at the layer below it.
- `podman-compose up -d`'s own dependency-waiting behavior
  (`depends_on: condition: service_healthy`) has no timeout of its
  own — any automation that calls it needs to supply one, or a broken
  dependency chain can hang the calling process indefinitely.

## Git

Branch: `feature/deploy-script`
Commit: `ef0f0d1`
Merged to `main`: `7b042fb` (regular merge commit, PR #64 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own extensive, repeated-failure-driven live verification already
served as the equivalent scrutiny, arguably more thoroughly than a
single automated review pass would have)

## Next

**Phase 10 (systemd on the Raspberry Pi) is now fully complete** (both
units: production systemd unit, deployment script with rollback).
Next is Phase 11 — Backups and disaster recovery: scheduled PostgreSQL
backups, a tested restore procedure (`docs/DISASTER_RECOVERY.md`), a
backup/DR audit.
