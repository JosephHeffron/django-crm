# 0006 — restic for off-host, encrypted backup storage

## Context

`docs/BACKUP_DR_AUDIT.md`'s HIGH finding #1 (Phase 11 unit 2): backups
produced by `scripts/backup.sh` live only under `backups/` inside the
same repository checkout the application runs from — on the same disk
(the Raspberry Pi's SD card, in production) as the data they protect.
SD card failure is a well-known, common failure mode for Raspberry Pi
deployments specifically, and in that failure mode the backups are
lost in the same event as the data they exist to recover — the entire
tested procedure in `docs/DISASTER_RECOVERY.md` becomes unusable.
MEDIUM finding #2 (same audit) is related: `.env` — real secrets — is
copied into every local backup unencrypted at rest, `chmod 600` only,
which the audit explicitly deferred pending an off-host destination to
design encryption against.

Both findings were left open at the time because, per `CLAUDE.md`'s
"do not overengineer" rule, inventing a destination or encryption
scheme without a concrete choice already made would have been
speculative. `docs/ROADMAP.md`'s Phase 15 picks this up now that the
user has chosen Backblaze B2 as the destination.

## Alternatives considered

- **Plain `rclone` (or `aws s3 cp`/`b2 upload-file`) copy of the
  existing local backup archive to the bucket.** Rejected: none of
  these encrypt the archive client-side by default — they transfer it
  securely (TLS in transit) and rely on the destination's own
  server-side storage encryption, which does nothing against a
  compromised or misconfigured bucket, and does nothing to address
  finding #2 at all. Sourcery's review of an earlier draft of
  `docs/ROADMAP.md`'s Phase 15 wording caught exactly this gap — see
  PR #83.
- **`rclone` with an `rclone crypt` remote.** A real option — genuine
  client-side encryption, and `rclone` supports B2 natively. Not
  chosen only because `restic` does the same job with less
  configuration (one repository URL plus a password, versus a base
  remote plus a separate crypt remote layered on top) and adds
  deduplication and built-in retention (`restic forget`) for free,
  which `rclone` doesn't provide on its own.
- **A second physical drive, synced via `rsync`/cron.** Rejected as
  the *only* mechanism (though nothing here prevents someone from
  additionally doing this): the user doesn't have a second drive yet,
  and per the "hardware the user doesn't have yet shouldn't block
  Phase 15" reasoning already reflected in `docs/ROADMAP.md`, this
  phase is scoped to a cloud/software-only destination that needs no
  new hardware purchase.
- **Encrypting `.env` alone (e.g. with `age`/`gpg`) without addressing
  off-host storage.** Rejected as incomplete — it would resolve
  finding #2 in isolation but leave finding #1 (the actually more
  severe HIGH finding) untouched, and the audit's own reasoning
  already noted these two are best solved together once a destination
  exists.

## Decision

`scripts/backup.sh` pushes each local backup to a `restic` repository
after the local backup completes, when `RESTIC_REPOSITORY` is set (via
`.env` — unset by default, so existing deployments are unaffected
until they opt in). The repository is encrypted with `RESTIC_PASSWORD`
before anything leaves the host. The user's chosen destination is
Backblaze B2, using restic's native `b2:` repository backend
(`B2_ACCOUNT_ID`/`B2_ACCOUNT_KEY`, an application key scoped to one
bucket only — see `docs/ADMIN_GUIDE.md`). `scripts/restore_offhost.sh`
pulls a snapshot back down into `backups/`, after which
`scripts/restore.sh` proceeds unchanged.

`restic` runs as a plain binary on the deployment host (installed via
the host's own package manager, e.g. `dnf`/`apt` — not inside any
container), the same "install a required system dependency" pattern
already established for Podman and `qemu-user-static`.

## Reason

Closes both HIGH finding #1 and MEDIUM finding #2 with one mechanism:
`restic`'s repository encryption is mandatory (it refuses to operate
without `RESTIC_PASSWORD`), so the off-host copy — including the
`.env` snapshot inside it — is encrypted client-side by construction,
not as a separate step that could be forgotten. Retention
(`restic forget --keep-last`) mirrors `scripts/backup.sh`'s existing
local `BACKUP_RETENTION_COUNT` policy with the same knob, rather than
introducing a second, differently-configured retention mechanism.
Fully opt-in and backward compatible: `RESTIC_REPOSITORY` unset (the
default for every existing deployment) skips this step entirely,
producing byte-identical behavior to before this decision.

## Consequences

- `restic` becomes a new host-level dependency, documented in
  `docs/ADMIN_GUIDE.md`, not baked into any container image.
- `RESTIC_PASSWORD` is itself a single point of failure: restic has no
  password-recovery mechanism, so losing it makes the off-host backups
  permanently unrecoverable. `.env.example` explicitly tells the
  operator to keep a copy of it somewhere other than the host it's
  protecting against losing.
- A real Backblaze B2 account, bucket, and application key are outside
  what this project (or an AI assistant working on it) can create —
  `docs/BACKUP_DR_AUDIT.md`'s finding #1 is updated to reflect that the
  *mechanism* is now implemented and verified against a local throwaway
  restic repository, while real production wiring remains the
  deploying operator's own step.
- Because `scripts/backup.sh` already treats `.env` as trusted,
  readable input (it copies the file into every local backup), sourcing
  it for `RESTIC_*`/backend credentials introduces no new trust
  boundary.

## Date

2026-09-28
