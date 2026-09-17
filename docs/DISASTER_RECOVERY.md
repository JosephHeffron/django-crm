# Disaster recovery

Phase 11 unit 2 — the tested restore procedure named in the roadmap.
Documents how to recover the CRM from a backup produced by
`scripts/backup.sh` (Phase 11 unit 1), using `scripts/restore.sh`, and
records a real, live-tested disaster recovery drill — not just the
theoretical steps.

## What's covered

A backup (`backups/<timestamp>/`) contains everything needed to fully
reconstruct the running application, per `docs/ARCHITECTURE.md`'s
"Backup strategy":

- `db.dump` — a `pg_dump` (custom format) logical backup of the
  database.
- `media_files.tar` — a `podman volume export` of the `media_files`
  named volume (user-uploaded files, once the app has any).
- `caddy_data.tar` / `caddy_config.tar` — `podman volume export`s of
  Caddy's certificate storage and runtime config, so recovery doesn't
  force re-issuing a real Let's Encrypt certificate (rate-limited).
- `env.backup` — a copy of `.env` at backup time, `chmod 600`.
- `manifest.txt` — what was backed up, when, and from which git
  revision.

`static_files` is not backed up — it's fully regenerable from source
via `collectstatic`, which `scripts/entrypoint.sh` already runs on
every `web` container start.

## Restore procedure

```
./scripts/restore.sh <backup-timestamp> --yes
```

`<backup-timestamp>` names a directory under `backups/`, e.g.
`2026-09-17T03-00-00Z`. The `--yes` flag is mandatory — the script
refuses to run without it, since this is a genuinely destructive
operation.

The script models a **real disaster**, not a soft "restore over
current state": it assumes the current `postgres_data`/
`media_files`/`caddy_data`/`caddy_config` volumes are lost or
untrustworthy, and rebuilds them from the backup rather than restoring
into whatever's currently there. Concretely, in order:

1. If a `db` container currently exists, takes a fresh safety backup
   of current state first (via `scripts/backup.sh` itself) — so a
   mistaken restore still has a way back. **Skipped, not blocking, if
   no `db` container exists** — the exact case a real disaster
   produces, where there's nothing left to back up (see "A real design
   flaw this caught," below).
2. Tears down the current stack (`podman-compose down`).
3. Removes the current `postgres_data`/`media_files`/`caddy_data`/
   `caddy_config` volumes entirely.
4. Recreates `media_files`/`caddy_data`/`caddy_config` from the
   backup's volume tars (`podman volume import`).
5. Starts `db` alone against a fresh, empty `postgres_data` volume,
   waits for it to be ready.
6. Restores `db.dump` into it (`pg_restore --clean --if-exists`).
7. Starts the full stack, waits for `db`/`web` to report healthy
   (checked via `podman inspect`, the same reasoning as
   `scripts/deploy.sh` — see that script's comments for why
   `systemctl`'s view of a `Type=oneshot` unit can't be trusted for
   this).
8. Extracts the backup's `.env` to `env.restored.backup` **for manual
   review only** — never auto-applied. The live `.env` may hold newer
   or different real secrets than whatever the backup captured; only
   a human should decide what, if anything, to merge from it.

## Two real design flaws this caught

**1. The pre-restore safety backup was unconditionally required.** The
first version of `scripts/restore.sh` required step 1 (the safety
backup) to succeed before proceeding, no exceptions. Tested against a
real total-loss drill (see below) — the `db` container didn't exist
yet, `scripts/backup.sh` correctly failed with "no such container,"
and `restore.sh` correctly-per-its-own-logic refused to continue. The
result: the script was unable to recover from exactly the disaster
scenario it exists for — a total loss, with nothing left to protect by
backing it up first. Fixed by checking `podman container exists`
first: skip the safety backup (with a clear message, not silently)
only when there's genuinely nothing there; if the container exists and
the backup still fails for some other reason, that's still a hard
stop, unchanged.

**2. The safety backup's own retention pruning could delete the
backup being restored from, mid-restore.** `scripts/backup.sh` prunes
old backups down to `BACKUP_RETENTION_COUNT` every time it runs —
including when `restore.sh` calls it internally for the pre-restore
safety backup (fix 1, above). If the backup being restored from
happened to sit right at the retention boundary, taking one more
(safety) backup pushed it past the cutoff and deleted it — *while the
restore was already mid-flight*, after the live stack had already
been torn down. Reproduced deliberately: set `BACKUP_RETENTION_COUNT=2`,
took a target backup, took one more to push the target to position 2
of 2, then restored from the target — the safety backup's own pruning
step logged `removing old backup: .../<target-timestamp>/` for the
exact directory being restored from. Fixed by staging a full copy of
the backup to a temporary directory (`mktemp -d`) before doing
anything else, and restoring from that staged copy for the rest of the
script — completely decoupling the restore from whether the original
`backups/<timestamp>/` directory still exists once the safety backup's
pruning runs. Re-ran the exact same reproduction after the fix:
pruning still logged the same deletion of the original directory, but
the restore completed successfully anyway, and the target backup's
marker row/file were confirmed present afterward — the staged copy is
what mattered, and it never depended on the original surviving.

## Live disaster recovery drill

Run against a real throwaway 3-container stack (never the actual
project's data), in an isolated clone (never the real project
directory — see "A real process mistake" in
`logs/claude/phase-11-backup-script.md` for why that discipline
exists).

1. Inserted a distinctive marker row into the database and a
   distinctive marker file into the `media_files` volume.
2. Took a real backup (`scripts/backup.sh`).
3. **Simulated total disaster**: tore down every container and removed
   every volume (`postgres_data`, `static_files`, `media_files`,
   `caddy_data`, `caddy_config`) — confirmed via `podman ps -a`/
   `podman volume ls` that nothing remained.
4. Ran `./scripts/restore.sh <timestamp> --yes`.
5. Confirmed, directly, not just from the script's own "success"
   message:
   - The marker row was present in the restored database, exact text
     intact.
   - The marker file was present in the restored `media_files` volume,
     exact content intact.
   - The full stack (`db`, `web`, `caddy`) was healthy and the app
     served a real page (`200` on the login page) through the
     restored Caddy certificates.
   - `env.restored.backup` was extracted with `600` permissions and
     was **not** applied to the live `.env`.
   - `pg_restore` produced zero ownership warnings this time (a
     separate, earlier isolated test that restored into a
     differently-named database role did produce harmless
     `ALTER TABLE ... OWNER TO` warnings — expected there, and
     specifically not expected in a real restore, which always uses
     the same `POSTGRES_USER` the backup was taken from).
6. Also verified, before the drill, that the safety guards actually
   refuse: missing `--yes`, a nonexistent backup timestamp, and an
   incomplete backup directory (missing one of the four required
   files) — each correctly refused with a clear error, nothing
   touched.

Result: **full recovery confirmed**, database and media data intact,
application serving real traffic again, `.env` correctly left for
manual review rather than silently overwritten.

A second, separate drill specifically reproduced and verified the fix
for the retention-boundary bug above: `BACKUP_RETENTION_COUNT=2`, a
target backup, then one more to push the target to the retention
boundary, then a restore from the target. Confirmed the safety
backup's pruning step really did delete the original target directory
mid-restore (logged explicitly), and confirmed the restore still
completed successfully and the target's marker data was present
afterward — proving the fix, not just that the restore "didn't error."

## What this doesn't cover (stated plainly)

- **No physical Raspberry Pi exists yet** — this drill ran on the
  Fedora workstation against a throwaway stack, the same honest
  limitation already stated in `docs/ARM64_REVIEW.md`/
  `docs/ARM64_TESTING.md`. The mechanics (compose, volumes, `pg_dump`/
  `pg_restore`) are architecture-independent, so this proves the
  *procedure*, not performance or timing on real hardware.
- **Backups currently live only on the same host** as the application
  — a full-disk failure, host theft, or SD-card corruption would take
  the backups down with the application they're meant to protect
  against exactly that. This is a real, known gap, not a silent one —
  `docs/BACKUP_DR_AUDIT.md` addresses it directly rather than leaving
  it implicit.
- **No automated restore testing** — this drill was run by hand, once,
  for this unit. It's not (yet) a scheduled, repeatable check the way
  `scripts/test-arm64.sh` is for ARM64 builds. Also addressed in the
  audit.

## Recovery time (informal, this environment only)

The full drill (steps 2-5 above) took a few minutes end to end on this
workstation — dominated by container image pulls/builds and the
health-check wait loops in `restore.sh`/`deploy.sh`, not by the actual
`pg_dump`/`pg_restore` transfer (a small test database). No formal RTO
target exists yet for this project; a real target, informed by real
hardware timing, is a reasonable Phase 13/14 (final audit / handoff
documentation) follow-up, not something to invent here without data.
