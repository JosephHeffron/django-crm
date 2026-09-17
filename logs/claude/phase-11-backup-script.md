# PHASE 11: SCHEDULED POSTGRESQL BACKUPS (UNIT 1)

Started: 2026-09-17
Ended: 2026-09-17

## Objective

First of two Phase 11 units, per the roadmap: scheduled PostgreSQL
backups, per `docs/ARCHITECTURE.md`'s "Backup strategy" — logical
`pg_dump` backups, stored outside the database container, plus media
files and configuration ("equally required for recovery"), with a
retention policy.

## Files created / changed

- `scripts/backup.sh` — new. `pg_dump` (custom format, `-Fc`) of the
  database via `podman exec` (no host-side credentials needed — reads
  `$POSTGRES_USER`/`$POSTGRES_DB` from the `db` container's own
  environment, connects over the default local Unix socket the
  official image already trusts). `podman volume export` for
  `media_files`/`caddy_data`/`caddy_config` — these are named Podman
  volumes in both compose files, not host directories, confirmed by
  reading `compose.prod.yml` before assuming otherwise.
  `static_files` deliberately excluded — regenerable via
  `collectstatic`, not user data. A copy of `.env` (`chmod 600`).
  Configurable retention (`BACKUP_RETENTION_COUNT`, default 7). A
  failure-cleanup `trap` removes a partial/incomplete backup directory
  rather than leaving a misleading one behind.
- `systemd/crm-backup.service` / `systemd/crm-backup.timer` — new.
  Daily schedule (`OnCalendar=daily`, `Persistent=true` — a missed
  window, e.g. the Pi powered off, still runs at the next
  opportunity), same rootless systemd user-unit model as
  `systemd/crm.service` (Phase 10, ADR 0005).
- `.gitignore` — added `/backups/`.

## Commands

$ First live test run — **found a real process mistake, not a script
  bug**: ran `scripts/backup.sh` directly against the actual project
  working directory instead of an isolated clone. It correctly did
  exactly what it was written to do — copied `.env` into
  `backups/<timestamp>/env.backup` — except that `.env` was the real,
  already-existing one with real secrets, not a throwaway test file.
  Caught this immediately, confirmed with the user before deleting it
  (`env.backup` removed first, then the rest of that backup
  directory's throwaway contents, then the empty directories via
  `rmdir` after a plain `rm -rf` was correctly blocked by this
  project's permission policy). All further testing moved to an
  isolated throwaway git clone (`git clone` of the local repo into a
  scratch directory, matching the pattern already established for
  `scripts/deploy.sh` in Phase 10 unit 2) — never the real project
  directory again for anything that touches `.env` by path.

$ Full live verification, from that point on entirely inside the
  isolated clone: brought up a throwaway 3-container stack (a
  non-privileged-port copy of `compose.prod.yml`, matching the real
  container/volume naming `backup.sh` expects), inserted a real marker
  row directly into the database and a real marker file directly into
  the `media_files` volume (via a throwaway root container, since the
  app itself has no write access to `/app/media` as a non-root user —
  noted as an aside, not a Phase 11 concern, since the app has no
  `FileField`/`ImageField` yet).
  - Ran `scripts/backup.sh` — produced `db.dump`, `media_files.tar`,
    `caddy_data.tar`, `caddy_config.tar`, `env.backup` (confirmed
    `600` permissions), `manifest.txt`.
  - `pg_restore --list db.dump` (via a throwaway `postgres:18-alpine`
    container, `:Z` SELinux label needed on the bind mount — same
    class of issue as Phase 8 unit 1's Caddyfile mount) — confirmed a
    valid, well-formed custom-format archive, 200 TOC entries.
  - **The actual proof this unit needed**: restored `db.dump` into a
    completely fresh, separate database (`pg_restore`) and confirmed
    the marker row survived — not just that the dump's structure
    looked right. (Harmless `ALTER TABLE ... OWNER TO` warnings
    appeared, expected since the test restored into a
    differently-named role than the dump's original owner — a real
    production restore uses the same `POSTGRES_USER`, so this
    wouldn't occur there.)
  - `tar -tvf media_files.tar` — confirmed the real marker file
    present.
  - `tar -tvf caddy_data.tar` / `caddy_config.tar` — confirmed real
    certificate/config content present.
  - Tested the retention policy directly: ran the script repeatedly
    with `BACKUP_RETENTION_COUNT=2` and confirmed old backup
    directories were actually pruned, not just that the flag was
    accepted.
  - Tested the systemd timer live: installed a throwaway
    `crm-backup-test.{service,timer}` pointed at the clone, triggered
    the service manually (`systemctl --user start`), confirmed
    `journalctl --user` transparently captured the script's real
    output; enabled the timer and confirmed via `systemctl --user
    list-timers` that `OnCalendar=daily` resolved to a correct,
    sensible next-run time.
  - Tested the failure-cleanup `trap` directly: stopped the `db`
    container mid-test, re-ran the backup, confirmed it failed loudly
    (`pg_dump` couldn't connect) and **removed the resulting partial
    backup directory** rather than leaving a misleading, incomplete
    one behind — the two prior good backups were untouched.
  - Cleaned up: all throwaway containers, volumes, the built test
    image, the throwaway systemd units, and the backup test
    directories.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit).

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — this unit is scripts/systemd
units, no application code).

## Tests

`python manage.py test` — 296 passed, 0 failures.
`scripts/backup.sh`'s own live backup-then-restore cycle (see
Commands) — the unit's real test.

## Decisions

- `pg_dump` (logical, custom format), not a raw volume
  export/`pg_basebackup`, for the database itself — matches
  `docs/ARCHITECTURE.md`'s already-documented decision, and is safer
  (a proper MVCC-consistent snapshot of a live database) and more
  portable than copying a running Postgres data directory's raw files.
- `static_files` is excluded from backups on purpose — it's fully
  regenerable from source (`collectstatic`), so backing it up would
  just be redundant storage, not real data protection.
- The failure-cleanup `trap` removes an incomplete backup directory
  rather than leaving it — a partial backup that looks superficially
  present (files exist, but `db.dump` might be truncated) is worse
  than no backup at all, since it could go unnoticed until an actual
  disaster reveals it's unusable.
- `.env` is backed up as a plain file copy, `chmod 600`, not
  encrypted — acceptable for now since the backups directory itself
  stays on the same host under the same access controls as the
  running application; revisiting this (e.g. before ever copying
  backups off-host) is exactly the kind of thing Phase 11 unit 2's
  audit should explicitly weigh in on, not something to solve
  speculatively here.

## Errors

One real, substantive mistake this unit's own process caught — not a
defect in the script's logic, but in how it was first exercised:
running it against the real project directory copied the real `.env`
into a throwaway-looking backup output. This is exactly the sort of
thing the project's "test in an isolated clone, never the real
working tree, for anything that touches `.env`" discipline (already
established for `scripts/deploy.sh`) exists to prevent — the lesson
here is that the discipline needs to be applied *before* the first
run of a new script that touches `.env`, not only once something has
already gone wrong once with a different script.

## Lessons learned

- Any script that reads or copies `.env` by path (not by parsed
  content) needs to be tested from an isolated clone from the very
  first run, not just once a prior unit has already demonstrated why —
  the risk is inherent to what the script does, not specific to which
  script it is.
- Proving a backup is real means actually restoring it and checking
  the data, not just checking that the backup file exists and has a
  plausible size, or that a dump's table-of-contents lists the right
  tables. A structurally valid but practically unusable backup would
  pass every check except the one that matters.
- A backup script's failure mode matters as much as its success mode —
  an incomplete backup that looks present is a worse outcome than an
  absent one, because it creates false confidence that isn't
  discovered until the moment it's actually needed.

## Git

Branch: `feature/backup-script`
Commit: `6b7b496`
Merged to `main`: `b8c01a1` (regular merge commit, PR #66 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live backup-and-restore verification already served as the
equivalent scrutiny)

## Next

Phase 11 unit 2 — a tested restore procedure (`scripts/restore.sh`,
`docs/DISASTER_RECOVERY.md`) and a backup/DR audit. Phase 11 is not
yet complete — `docs/ROADMAP.md` stays unchecked until unit 2 also
merges.
