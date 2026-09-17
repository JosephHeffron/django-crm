# PHASE 11: TESTED RESTORE PROCEDURE + BACKUP/DR AUDIT (UNIT 2)

Started: 2026-09-17
Ended: 2026-09-17

## Objective

Second and final unit of Phase 11, per the roadmap: a tested restore
procedure (`docs/DISASTER_RECOVERY.md`) and a backup/DR audit,
building on unit 1's `scripts/backup.sh`.

## Files created / changed

- `scripts/restore.sh` — new. Models a genuine disaster (current
  `postgres_data`/`media_files`/`caddy_data`/`caddy_config` state
  assumed lost/untrustworthy), rebuilding all of it from a backup
  rather than restoring "over" whatever currently exists. Requires
  `--yes`; refuses a nonexistent or incomplete backup; takes a
  best-effort pre-restore safety backup; never auto-applies a
  backup's `.env`.
- `docs/DISASTER_RECOVERY.md` — new. The runbook, plus real results
  from two live disaster recovery drills (see below).
- `docs/BACKUP_DR_AUDIT.md` — new. Findings on the complete
  backup/restore system from both Phase 11 units.

## Commands

$ Live disaster recovery drill #1, in an isolated clone (never the
  real project directory, applying Phase 11 unit 1's own lesson from
  the very first run this time): inserted a distinctive marker row
  and media marker file, took a backup, **completely destroyed every
  container and volume** (`podman-compose down` + `podman volume rm`
  on all five), confirmed via `podman ps -a`/`podman volume ls` that
  nothing remained, then ran `scripts/restore.sh`.
Result (first attempt): **failed** — `scripts/backup.sh` (called
internally for the pre-restore safety backup) correctly reported "no
such container" (since `db` didn't exist after the simulated
disaster), and `restore.sh`'s then-unconditional requirement that the
safety backup succeed caused it to refuse to continue. **Found a real
design flaw**: the script couldn't recover from precisely the
scenario it exists for. Fixed by checking `podman container exists`
first, skipping the safety backup (with a clear message) only when
genuinely nothing exists to back up.

$ Re-ran drill #1 after the fix.
Result: **succeeded** — full stack came up healthy; the marker row,
the media marker file, and a real served page (`200` through the
restored Caddy certificates) were all confirmed present afterward,
checked directly. `pg_restore` produced zero ownership warnings
(restoring into the same database role the backup was taken from,
matching real production use).

$ While designing/reviewing the restore flow, traced a second
  potential problem: the pre-restore safety backup (now working)
  itself triggers `scripts/backup.sh`'s own retention pruning — which
  runs against every backup in `backups/`, including the one currently
  being restored from. **Reproduced deliberately**: set
  `BACKUP_RETENTION_COUNT=2`, took a target backup, took one more to
  push the target to position 2 of 2 (the retention boundary), then
  restored from the target.
Result: confirmed the bug is real — the safety backup's own pruning
step logged `removing old backup: .../<target-timestamp>/`, deleting
the exact directory `restore.sh` needed to read from, mid-restore,
after the stack was already torn down. Fixed by staging a full copy
of the backup to a `mktemp -d` temporary directory before touching
anything else, and restoring from the staged copy for the rest of the
script — completely decoupling the restore from whether the original
`backups/<timestamp>/` directory survives the safety backup's pruning.

$ Re-ran the exact same reproduction after the fix.
Result: pruning still logged the same deletion of the original
directory (expected — that part of the behavior is correct and
unchanged), but the restore completed successfully anyway, and the
target backup's marker row/file were confirmed present afterward — the
staged copy is what mattered.

$ Also found, while reviewing `restore.sh`'s own `usage()` function: a
  shell redirection ordering bug (`ls -1 "$BACKUPS_DIR" 2>/dev/null
  >&2`) that silently sent the directory listing itself to
  `/dev/null` — `2>/dev/null` redirects stderr first, then `>&2`
  redirects stdout to wherever stderr *currently* points (already
  `/dev/null` at that point), so both streams ended up discarded.
  Confirmed live: the "Available backups:" section printed nothing
  even with a real backup present. Fixed by swapping the order
  (`>&2 2>/dev/null` — redirect stdout to the terminal's stderr
  first, then hide `ls`'s own error messages).

$ Verified the safety guards directly, not just read them: missing
  `--yes` (refused, listing shown correctly after the fix above), a
  nonexistent backup timestamp (refused), an incomplete backup
  directory missing one of the four required files (refused, named
  the specific missing file).

$ Cleanup after each drill: tore down containers, removed volumes, the
  throwaway built image, backup directories, and the extracted
  `env.restored.backup` file. Confirmed no stray state left in the
  isolated clone.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check`
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit).

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — this unit is scripts/docs, no
application code).

## Tests

`python manage.py test` — 296 passed, 0 failures.
Two full live disaster-recovery drills (see Commands) — the unit's
real test.

## Decisions

- `restore.sh` rebuilds volumes from scratch rather than restoring
  "into" whatever currently exists — modeling a genuine disaster (data
  assumed lost/corrupted) is the actually useful thing to test and
  design for, not a softer "revert to an earlier point" operation that
  would leave open questions about what state a partially-intact
  volume was actually in beforehand.
- The pre-restore safety backup is best-effort, not mandatory — see
  the first bug above. A hard requirement sounds safer in the abstract
  but actually makes the tool useless for its primary purpose.
- Staging the backup being restored from to a temporary directory,
  immune to the safety backup's own retention pruning, was chosen over
  alternatives (e.g., excluding the in-progress restore's source from
  pruning by name, or reordering operations to restore before taking
  the safety backup) because it's the simplest fix that doesn't
  require `scripts/backup.sh` to know anything about what `restore.sh`
  is doing, or vice versa — the two scripts stay decoupled.
- The backup/DR audit's one HIGH finding (same-host-only backups) is
  deliberately left unfixed rather than solved with an invented
  destination — CLAUDE.md's "do not overengineer" rule applies as much
  to inventing infrastructure (an S3 bucket, a second host) this
  project hasn't actually chosen as it does to any other speculative
  addition.

## Errors

Three real, substantive things found and fixed during this unit's own
live verification — not from an automated review (repo is private, so
Sourcery doesn't review it; two full disaster-recovery drills, plus
deliberately reproducing an edge case, served the same purpose, more
thoroughly than a single review pass would have):

1. The pre-restore safety backup was unconditionally required,
   defeating the script's ability to recover from a total loss.
2. The safety backup's own retention pruning could delete the exact
   backup being restored from, mid-restore.
3. A shell redirection ordering bug silently hid the "available
   backups" listing in the usage message.

## Lessons learned

- A "take a safety backup before doing something destructive" pattern
  needs to explicitly handle the case where there's nothing left to
  back up — treating that as a hard failure defeats the pattern's own
  purpose in exactly the scenario that matters most.
- Two independent scripts that each seem correct in isolation
  (`backup.sh`'s retention pruning, `restore.sh`'s use of `backup.sh`
  as a safety step) can interact in a way that's only visible once you
  trace the actual sequence of filesystem operations across both —
  reading each script individually wouldn't have surfaced this; only
  reasoning through what state existed at each point in time did.
- `2>/dev/null >&2` and `>&2 2>/dev/null` are not equivalent — shell
  redirection is evaluated left to right, and getting the order wrong
  silently discards output rather than erroring, making it an easy
  mistake to ship unnoticed without actually running the code path.
- Deliberately reproducing a suspected edge case (the retention
  boundary scenario) rather than just reasoning about whether it could
  happen turned a plausible concern into a confirmed, then
  confirmed-fixed, bug — the same discipline this project has applied
  throughout (Phase 8's port conflict, Phase 9's tag collision, Phase
  10's systemctl no-ops) continuing to pay off here.

## Git

Branch: `feature/restore-dr`
Commit: `f7da04e`
Merged to `main`: `c3b4a68` (regular merge commit, PR #68 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own two live disaster-recovery drills already served as the equivalent
scrutiny)

## Next

**Phase 11 (Backups and disaster recovery) is now fully complete**
(both units: scheduled backups, tested restore procedure + backup/DR
audit). Next is Phase 12 — Logging and monitoring: a health-check
endpoint (explicitly deferred since Phase 7's healthchecks first
needed it), and an application logging review (what's logged, what
never is).
