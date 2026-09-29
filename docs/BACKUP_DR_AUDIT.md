# Backup / disaster recovery audit

Phase 11 unit 2 — the audit named in the roadmap, reviewing the
complete backup/restore system built in this phase
(`scripts/backup.sh`, `scripts/restore.sh`,
`systemd/crm-backup.{service,timer}`, `docs/DISASTER_RECOVERY.md`).
Same format as `docs/DATABASE_REVIEW.md`/`docs/SECURITY_REVIEW.md`/
`docs/PRODUCTION_CONFIG_REVIEW.md`: findings ranked by severity,
checked empirically, fixed where safe and contained, deferred with
reasoning where not.

## Method

- Read every file in scope end to end.
- Traced what actually happens on a real disaster, not just what the
  scripts claim to do — this is what surfaced both real bugs already
  documented in `docs/DISASTER_RECOVERY.md` ("Two real design flaws
  this caught") during this same phase's own live testing, referenced
  here rather than re-litigated.
- Considered the specific, actual failure modes of the real target
  hardware (a Raspberry Pi 5 booting from an SD card) rather than
  generic backup best practice in the abstract.
- Checked file permissions on everything a backup produces that holds
  secrets.

## HIGH

### 1. Backups live only on the same host as the application

`scripts/backup.sh` writes to `backups/` inside the same repository
checkout the application runs from — on the same disk (the Raspberry
Pi's SD card) as `postgres_data`, `media_files`, and everything else
a backup exists to protect. SD card corruption and failure is a
well-known, common failure mode for Raspberry Pi deployments
specifically — arguably the single most likely real disaster this
project will ever face, more likely than, say, a PostgreSQL bug
corrupting data while the card itself stays healthy. In that failure
mode, the backups are lost in the same event as the data they were
meant to recover, and `docs/DISASTER_RECOVERY.md`'s entire tested
procedure becomes unusable — there'd be nothing in `backups/` to
restore from.

**Status: FIXED (Phase 15) — mechanism implemented and verified,
production wiring is the deploying operator's own remaining step.**
`scripts/backup.sh` now pushes each backup to a `restic` repository
(client-side encrypted) when `RESTIC_REPOSITORY` is configured;
`scripts/restore_offhost.sh` pulls a snapshot back down for
`scripts/restore.sh` to complete the restore. See
`docs/decisions/0006-offhost-backups-restic.md` for the design and
`docs/DISASTER_RECOVERY.md` for the live-verified drill (a full
disaster — containers, volumes, AND the local `backups/` directory
itself all destroyed — recovered purely from a local throwaway restic
repository standing in for the real destination). The user chose
Backblaze B2 as the actual destination; creating that real B2 account/
bucket/application key is outside what this project (or an AI
assistant working on it) can do — it requires the operator's own
action, documented in `docs/ADMIN_GUIDE.md`'s "Backups" section. Until
that's done on a given deployment, `RESTIC_REPOSITORY` stays unset and
behavior is identical to before this fix (local-only backups) — this
is not a silent gap, it's an explicit, documented opt-in step.

## MEDIUM

### 2. `.env` backups are unencrypted at rest

`scripts/backup.sh` copies `.env` (real secrets: `DJANGO_SECRET_KEY`,
`POSTGRES_PASSWORD`) into every backup directory, `chmod 600`. That
permission bit only helps if the filesystem/host itself is otherwise
trusted — it does nothing once a backup is copied elsewhere (finding
1) onto a destination with different or weaker access control, and
does nothing against an attacker who already has filesystem access to
the Pi (at which point they could read the live `.env` directly
anyway, so this specifically isn't a *new* exposure — but it is one
more copy of the same secrets, in more places, for longer).

**Status: FIXED (Phase 15) as a side effect of finding 1's fix** — the
off-host copy of every backup, `.env` included, now travels inside a
`restic` snapshot, encrypted client-side with `RESTIC_PASSWORD` before
it leaves the host; verified live that the wrong password is flatly
rejected and the repository's on-disk contents are opaque binary, not
plaintext. The **local** on-disk copy in
`backups/<timestamp>/env.backup` remains `chmod 600` only, unchanged —
that's still the same trusted-single-host threat model finding 1's
original deferral reasoning described, not a new gap introduced by
this fix.

### 3. No automated, ongoing restore verification

This phase's own testing proved a *specific* backup restores
correctly, once, by hand (`docs/DISASTER_RECOVERY.md`'s live drills).
Nothing checks that *future*, unattended, `crm-backup.timer`-triggered
backups keep being genuinely restorable over time — a `pg_dump` could
start silently failing in a way that still produces a file (unlikely
given `set -e` and this project's failure-cleanup trap, but not
provably impossible for every conceivable failure mode), or bit rot
could affect an on-disk backup between when it's written and when it's
eventually needed.

**Status: not fixed, deferred** — a scheduled, automated "restore the
latest backup into a scratch database and check it" job is the correct
long-term answer, mirroring `scripts/test-arm64.sh`'s own
self-verifying design (Phase 9), but building and scheduling that is
real new scope beyond what this unit's roadmap line ("a tested restore
procedure") asked for. Worth a future small unit once Phase 11's
immediate scope is done, not scope-crept into this one.

## LOW

### 4. Retention policy (default: 7 daily backups) has no relationship to how quickly a problem might be noticed

If a real data problem (not a hardware disaster — e.g. a bad
migration, or an operator mistake) isn't noticed within the retention
window, the last good backup could be pruned before anyone realizes
they need it. This is a real, if narrow, risk with any time-based
retention policy, not specific to this implementation.

**Status: informational, not a defect** — `BACKUP_RETENTION_COUNT` is
already configurable per-deployment via an environment variable
(`scripts/backup.sh`), so tuning it is already possible without a code
change; 7 is a reasonable, unremarkable default for daily backups, not
a value this audit found reason to second-guess. Worth keeping in mind
operationally, not fixing here.

### 5. No formal RTO/RPO target

`docs/DISASTER_RECOVERY.md` already states this plainly rather than
inventing a number without real hardware timing data to base it on.
Restated here only to confirm the audit considered it, not as a new
finding — a real target is reasonable Phase 13/14 (final audit /
handoff documentation) scope, once real hardware exists to measure
against.

## Checked and confirmed solid (not just assumed)

- The actual backup-and-restore mechanism works, end to end, on real
  (if throwaway) data — proven twice in this phase's own live testing,
  not assumed from reading the scripts (`docs/DISASTER_RECOVERY.md`).
- `restore.sh` refuses to run without an explicit `--yes` flag, refuses
  a nonexistent backup timestamp, and refuses an incomplete backup
  directory — each verified live, not just read in the script.
- `restore.sh` never auto-applies a backup's `.env` over the live
  one — extracted separately for manual review, verified live.
- `static_files` is correctly excluded from backups (regenerable via
  `collectstatic`, confirmed already relied on by
  `scripts/entrypoint.sh` on every `web` container start) — not a
  missing backup, a deliberate and correct exclusion.
- `scripts/backup.sh`'s failure-cleanup trap correctly removes a
  partial, misleading backup directory rather than leaving one behind
  — verified live via a deliberate mid-backup failure.
- The systemd timer (`crm-backup.timer`) schedules correctly
  (`OnCalendar=daily`, `Persistent=true` for a missed window) and
  integrates cleanly with `journalctl --user` — verified live.

## Recommendation

The mechanism itself is sound and has been proven to actually work,
three times now, against real failure scenarios — the two real bugs
this phase's own testing found and fixed, plus Phase 15's off-host
push/pull mechanism (documented in `docs/DISASTER_RECOVERY.md`/
`docs/decisions/0006-offhost-backups-restic.md`, not repeated here).
Both the HIGH and MEDIUM findings originally recorded here are now
fixed; see each finding's own updated status above. What's left is
operational, not architectural: an actual Backblaze B2 account/bucket/
key needs to be created and wired into a given deployment's `.env`
before that deployment is trusted with real production data on real
hardware — the mechanism to do so is built and verified, only the
account creation itself remains, and that's necessarily outside what
this project can do on the operator's behalf.
