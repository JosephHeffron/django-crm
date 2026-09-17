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

**Status: not fixed, documented as the clearest concrete gap this
phase leaves** — no off-host storage destination (a second Pi, a NAS
on the LAN, an object storage bucket) exists yet in this project's
architecture, and inventing one without a concrete choice already
made would be exactly the kind of speculative addition CLAUDE.md's
"do not overengineer" rule asks to avoid. This is the most important
open item for whoever deploys this to real hardware to close before
depending on it — copying `backups/` to a second location, by
whatever means fits that deployment, is a small addition once a
destination exists to copy to.

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

**Status: not fixed, deferred** — encrypting a single file (e.g.
`age`/`gpg` with a key kept off-host) is a reasonable, low-effort
addition, but it's tightly coupled to finding 1: an off-host backup
destination is the point at which encrypting `.env` specifically
starts to matter (protecting it in transit/at rest somewhere less
trusted than the Pi itself), so it makes more sense to solve both
together once finding 1 has an actual destination to design against,
rather than encrypt now for a threat model (a trusted single-host
backup directory) where it adds process without much real benefit.

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
twice, against real failure scenarios — including two real bugs this
phase's own testing found and fixed (documented in
`docs/DISASTER_RECOVERY.md`, not repeated here). The one HIGH finding
(backups living only on the same host/SD-card as the data they
protect) is the clearest concrete gap: for a Raspberry Pi deployment
specifically, that's a real, plausible way for this entire backup
system to fail to help exactly when it's needed most. It's correctly
left as a documented, prioritized gap rather than a speculative fix,
since closing it well requires a concrete off-host destination this
project hasn't chosen yet — but it should be the first thing addressed
before this deployment is trusted with real production data on real
hardware.
