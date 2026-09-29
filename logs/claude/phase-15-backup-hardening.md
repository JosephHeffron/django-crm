# PHASE 15: BACKUP HARDENING

Started: 2026-09-28
Ended: 2026-09-28

## Objective

First phase of the post-release roadmap (`docs/ROADMAP.md`): off-host
backup storage and encrypted backup archives — closing
`docs/BACKUP_DR_AUDIT.md`'s HIGH finding #1 and MEDIUM finding #2,
deliberately scoped to a cloud/software-only destination since the
user doesn't have a second physical drive or Raspberry Pi yet (see the
Phase 15 restructuring in PR #83).

## Files created / changed

- `scripts/backup.sh` — sources `.env` (`set -a`), and after the
  existing local backup completes, pushes it to a `restic` repository
  when `RESTIC_REPOSITORY` is set — encrypted client-side via
  `RESTIC_PASSWORD`, tagged `django-crm`, with its own retention
  (`restic forget --keep-last`) mirroring `BACKUP_RETENTION_COUNT`.
  Fully opt-in: unset `RESTIC_REPOSITORY` (every existing deployment's
  default) produces byte-identical behavior to before this phase.
- `scripts/restore_offhost.sh` — new. Pulls a snapshot back down into
  `backups/`, for the case the local `backups/` directory itself is
  gone (not just the running containers/volumes) — the actual gap
  finding #1 was about.
- `.env.example` — documents `RESTIC_REPOSITORY`/`RESTIC_PASSWORD`/
  `B2_ACCOUNT_ID`/`B2_ACCOUNT_KEY`, commented out (opt-in), with an
  explicit warning to store `RESTIC_PASSWORD` somewhere other than
  this host.
- `docs/decisions/0006-offhost-backups-restic.md` — new ADR: why
  `restic`+B2 over plain `rclone`/`rclone crypt`/a second physical
  drive.
- `docs/BACKUP_DR_AUDIT.md` — findings #1 (HIGH) and #2 (MEDIUM) marked
  fixed in place, with reasoning; "Recommendation" section updated.
- `docs/DISASTER_RECOVERY.md` — new "Off-host disaster recovery (Phase
  15)" section documenting the live drill; "What this doesn't cover"
  updated (real B2 account still not created, same reasoning pattern
  as "no physical Pi yet").
- `docs/ARCHITECTURE.md` — "Backup strategy" section mentions the
  off-host push.
- `docs/ADMIN_GUIDE.md` — new "Off-host backup storage" subsection
  under "Backups" (install `restic`, create a B2 bucket/key, configure
  `.env`, recover via `restore_offhost.sh`); "Known limitations"
  updated to reflect the mechanism is now built (setup is what's left,
  not code).
- `docs/PRODUCTION_READINESS.md` — HIGH finding and its coupled MEDIUM
  finding marked fixed in the findings index and the closing
  recommendation, without rewriting the historical audit narrative.
- `docs/ROADMAP.md` — Phase 15's checkbox (checked in the close-out
  commit, per established pattern, not this one).

## Commands

$ Read every file in scope before changing anything: `scripts/
  backup.sh`, `scripts/restore.sh`, `.env.example`, `docs/
  BACKUP_DR_AUDIT.md`, `docs/DISASTER_RECOVERY.md`, `docs/
  ARCHITECTURE.md`'s Backup strategy section, `systemd/crm-backup.
  {service,timer}`.

$ `dnf list --available restic` confirmed the package exists (Fedora
  repo) for the real deployment target; `sudo dnf install restic`
  failed in this session (no interactive sudo available). Downloaded a
  static `restic` binary from the project's GitHub releases instead,
  used only for this session's own live testing — removed from the
  real project's `.venv/bin` again once testing finished. Production/
  real deployments install via `sudo dnf install restic`/
  `sudo apt install restic`, documented in `docs/ADMIN_GUIDE.md`.

$ Full live drill, in an isolated `git clone` (never the real project
  directory), against a throwaway `compose.dev.yml` stack
  (`COMPOSE_PROJECT_NAME=django-crm`, `VOLUME_SUFFIX=_dev`) and a local
  directory standing in for the real Backblaze B2 destination:
  1. Brought up `db`/`web`/`caddy`, both healthy.
  2. Created a marker `Company` record directly via `manage.py shell`.
  3. Ran `scripts/backup.sh` with `RESTIC_REPOSITORY` set — confirmed
     both the local backup and the off-host `restic` push completed
     (`restic snapshots` showed the pushed snapshot).
  4. **Simulated the actual disaster this phase exists for**: tore
     down every container, removed every volume, AND removed the
     local `backups/` directory itself (not just volumes — the gap
     finding #1 was specifically about). Confirmed nothing remained.
  5. Ran `scripts/restore_offhost.sh` — confirmed it recreated
     `backups/<timestamp>/` from the off-host snapshot, byte-for-byte
     the same layout `backup.sh` produced.
  6. Ran `scripts/restore.sh <timestamp> --yes` exactly as documented
     — no different from restoring off a local backup.
  7. Confirmed the marker `Company` record was present in the restored
     database — full recovery from literally nothing left on the host.
  8. Confirmed the encryption is real: `restic snapshots` with the
     wrong `RESTIC_PASSWORD` was flatly rejected
     (`Fatal: wrong password or no key found`), and the repository's
     raw on-disk files are opaque binary, not readable content.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config -q`
  / `pip-audit -r requirements.txt` / `manage.py check` / `manage.py
  makemigrations --check --dry-run`
Result: PASS (shell-script and docs unit — no Python application code
changed).

## Tests

`python manage.py test` — 303 passed, 0 failures (unchanged — this
phase touched no Django application code).

## Decisions

- **`restic` over plain `rclone`/`aws s3 cp`.** Neither encrypts
  client-side by default — Sourcery's review of PR #83's roadmap
  wording caught this exact gap in an earlier draft (grouping
  `restic`/`rclone` as equivalent), which is what first surfaced this
  needed to be an explicit, deliberate choice rather than an
  afterthought. See `docs/decisions/0006-offhost-backups-restic.md`.
- **Opt-in via `RESTIC_REPOSITORY` presence, not a new required
  variable.** Every existing deployment (including anyone who already
  deployed this project before Phase 15) keeps working unchanged with
  local-only backups until they deliberately configure the new
  variables — no migration step, no breaking change.
- **`cd` into `BACKUPS_DIR` before calling `restic backup` with a
  relative path**, rather than the absolute `$DEST` path. Verified
  live that restic's snapshot metadata always displays canonicalized
  absolute paths regardless of how the argument was passed, but the
  actual restorable tree structure is rooted at whatever argument was
  given — using a relative path means `restic restore --target
  $BACKUPS_DIR` recreates `backups/<timestamp>/` directly, with no
  path-hunting logic needed in `restore_offhost.sh`. This was
  confirmed by direct experiment, not assumed from documentation.
- **A local directory as the test "off-host" destination**, not a real
  Backblaze B2 bucket. Creating a real B2 account/bucket/application
  key is outside what an AI assistant can do (third-party account
  creation, real credentials) — the mechanism is destination-agnostic
  (restic's `b2:` backend differs only in the repository URL and
  backend credentials), so this proves the mechanism genuinely works
  without requiring real cloud credentials to do so.

## Sourcery review (PR #86)

Three real findings, all fixed before merge:

1. **Relative local `RESTIC_REPOSITORY` resolves against different
   working directories in the two scripts** — `backup.sh` calls
   `restic` from inside `$BACKUPS_DIR`, `restore_offhost.sh` from
   `$REPO_DIR`; a relative path would silently mean two different
   repositories. My own live drill never caught this because it always
   used an absolute path. Fixed by anchoring any relative,
   non-URL `RESTIC_REPOSITORY` to `$REPO_DIR` identically in both
   scripts (a `case` statement checking for a leading `/` or a `:`,
   which also correctly leaves backend URLs like `b2:bucket:path`
   untouched). Verified in isolation: the same relative input resolves
   to the same absolute path regardless of which script's `$REPO_DIR`
   context it runs in.
2. **Hard-coded `django-crm` tag** would let two deployments sharing
   one restic repository prune or restore each other's snapshots.
   Fixed with a new `RESTIC_TAG` variable (default `django-crm`,
   documented in `.env.example`), used consistently for `--tag`/
   `--host` in `backup.sh` and `--tag` in `restore_offhost.sh`.
3. **TOCTOU race in the idempotent-init check** — two concurrent
   first-ever backups could both see `restic snapshots` fail, both
   attempt `restic init`, and the loser's failure would abort the
   whole script under `set -e` despite the repository being genuinely
   usable by then. Fixed by tolerating `restic init`'s failure and
   re-checking `restic snapshots` once more before treating it as
   fatal. Verified directly: initialized a repository, then reran the
   fixed check pattern against the now-already-initialized repository
   and confirmed it exits 0 rather than aborting.

## Errors

None requiring a fix — the two hiccups during live testing were both
test-environment artifacts, not bugs in the delivered scripts:
- `DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` still pointed at
  the `.env.example` placeholder (`crm.example.com`) after `cp
  .env.example .env` — fixed by setting them to `localhost` for this
  local test, matching Phase 13 unit 2's precedent.
- The isolated clone's directory was named `clone`, so `podman-compose`
  defaulted its project name to `clone_*` while `restore.sh` computed
  container/volume names from `SERVICE_PREFIX=django-crm` — a mismatch
  specific to this test's directory name, not a script defect. Fixed
  by exporting `COMPOSE_PROJECT_NAME=django-crm` consistently for every
  `podman-compose` invocation in the test, matching how a real
  deployment's checkout (named to match `SERVICE_PREFIX` by
  convention) would never hit this.

## Lessons learned

- Restic's snapshot metadata display (absolute, canonicalized paths)
  is not the same thing as its restorable tree structure (rooted at
  the argument given to `backup`) — worth verifying this distinction
  experimentally before designing a restore path around an assumption
  about it, which is exactly what happened here before committing to
  the design.
- A destructive-command safety net (this session's `rm -rf` hard deny)
  applies even inside an isolated throwaway clone under the scratchpad
  directory, not just the real project — `mv` (rename out of the way)
  achieved the same test condition without needing to work around that
  boundary, and was arguably a better choice anyway (reversible).

## Git

Branch: `feature/offhost-backups` (pending)
Commit: pending
Merged to `main`: pending

## Next

Phase 16 — browser-verified security review (CSP), per
`docs/ROADMAP.md`. Real Backblaze B2 account/bucket/key creation
remains the user's own step whenever they're ready to wire up a real
deployment — not blocking any further roadmap phase.
