# Administrator guide

Phase 14 unit 1 — practical, task-oriented documentation for whoever
actually runs this CRM in production. Everything here has already been
established and verified in earlier phases; this guide's job is to
put it in one place organized around what an operator actually needs
to *do*, not to introduce anything new. Where a task needs more detail
than fits here, it links to the document that has it.

This assumes production deployment on a Raspberry Pi 5 running Podman
+ Caddy + systemd, per `docs/ARCHITECTURE.md`. No physical Pi exists
for this project yet (see "What's not yet proven on real hardware,"
below) — everything here has been verified via `qemu-user-static`
emulation on the development workstation instead.

## First-time deployment

1. **Create a dedicated, non-root deployment account** on the Pi (not
   the interactive login user, not root) — production runs rootless
   Podman under this account's own systemd user session, per
   `docs/decisions/0005-rootless-systemd-deployment.md`.
2. **Clone the repository** into that account's home directory:
   ```
   git clone https://github.com/JosephHeffron/django-crm.git ~/django-crm
   cd ~/django-crm
   ```
   (`systemd/crm.service`'s `WorkingDirectory=%h/django-crm` assumes
   exactly this path — cloning anywhere else means adjusting that
   line.)
3. **Configure secrets**:
   ```
   cp .env.example .env
   ```
   Fill in `DJANGO_SECRET_KEY` (generate one:
   `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`),
   `DJANGO_ALLOWED_HOSTS`/`DJANGO_CSRF_TRUSTED_ORIGINS` (your real
   public domain), and `POSTGRES_PASSWORD`. Leave
   `DJANGO_SETTINGS_MODULE` **unset** — see the comment in
   `.env.example` for why setting it is actively harmful in
   production (this was a real bug, found and fixed in
   `docs/PRODUCTION_CONFIG_REVIEW.md`).
4. **Install and start the systemd unit**, exactly per
   `systemd/crm.service`'s own header comment:
   ```
   mkdir -p ~/.config/systemd/user
   cp systemd/crm.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now crm.service
   loginctl enable-linger "$(whoami)"
   ```
   The first start builds the ARM64 image natively on the Pi and pulls
   PostgreSQL/Caddy — expect this to take a while (`TimeoutStartSec=600`
   in the unit accounts for this).
5. **Verify**: `curl https://your-domain/health/` should return
   `{"status": "ok", "database": "ok"}`. Caddy requests a real Let's
   Encrypt certificate automatically the first time it starts, given a
   real domain that resolves to this host.
6. **Install the backup timer**, per `systemd/crm-backup.service`'s
   own header comment:
   ```
   cp systemd/crm-backup.service systemd/crm-backup.timer ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now crm-backup.timer
   ```
7. **Create the first admin user**:
   ```
   podman exec -it django-crm_web_1 python manage.py createsuperuser
   ```

## Day-to-day operations

**Check whether the stack is running and healthy:**
```
systemctl --user status crm.service
curl https://your-domain/health/
podman ps
```
(`systemctl status` only tells you the unit's `ExecStart` last
succeeded — it doesn't track whether the containers are still healthy
afterward. `curl .../health/` and `podman ps` are the checks that
actually reflect current reality; see `docs/LOGGING_REVIEW.md` and
`logs/claude/phase-10-deploy-script.md` for why.)

**View logs** (gunicorn, Caddy, PostgreSQL, and Django's own
application logging all reach here — see `docs/LOGGING_REVIEW.md`):
```
journalctl --user -u crm.service
journalctl --user -u crm.service -f   # follow live
```

**Restart the stack** (e.g., after an unrelated host reboot that
somehow left it in a bad state):
```
systemctl --user restart crm.service
```

**Grant a user write access** (create/edit/deactivate CRM records):
add them to the "Staff" group via the Django admin
(`https://your-domain/admin/`) — see `docs/PERMISSIONS.md`. Every
signed-in user can already *view* every record; only write actions are
gated by group membership. Superusers bypass this automatically.

## Deploying an update

```
cd ~/django-crm
./scripts/deploy.sh <git-ref>
```

`<git-ref>` should be a tag or exact commit SHA — a pinned, known
revision, not a moving branch name. The script pulls it, rebuilds,
restarts the stack, and verifies health; if the new revision fails its
health check, it automatically rolls back to whatever was running
before and exits non-zero. See `logs/claude/phase-10-deploy-script.md`
for the real bugs found and fixed while building this (why it doesn't
route through `systemctl` for the restart, specifically).

Check current status without changing anything:
```
./scripts/deploy.sh status
```

Roll back manually (to the revision before the last deploy), if a
problem is noticed after the fact rather than caught by the automatic
health check:
```
./scripts/deploy.sh rollback
```

## Backups

Runs automatically once daily via `crm-backup.timer` (installed
above). To back up on demand:
```
cd ~/django-crm
./scripts/backup.sh
```

Produces `backups/<timestamp>/` containing a PostgreSQL dump, the
`media_files`/`caddy_data`/`caddy_config` volumes, and a copy of
`.env` — everything needed to fully reconstruct the deployment, per
`docs/ARCHITECTURE.md`'s "Backup strategy". Keeps the last 7 backups
by default (`BACKUP_RETENTION_COUNT` to change this).

**Known gap, not yet closed** (`docs/BACKUP_DR_AUDIT.md` #1):
backups currently live on the same host/SD-card as the application
data they protect. A disk failure — a real, common Raspberry Pi
failure mode — would take out both at once. Copying `backups/` to a
second location on a regular basis is the single most valuable thing
left to do before trusting this deployment with real production data;
see that document for the full reasoning.

## Disaster recovery

If the Pi is genuinely lost (SD card failure, hardware death) and
you're rebuilding from a backup copied elsewhere:

```
cd ~/django-crm   # a fresh clone, if starting from scratch
./scripts/restore.sh <backup-timestamp> --yes
```

This is destructive by design — it assumes current data is
untrustworthy and rebuilds everything from the named backup, not a
soft "restore over" operation. Full procedure, safety guards, and a
real tested drill (including two real bugs this found and fixed) are
in `docs/DISASTER_RECOVERY.md` — read it before you need it, not
during an actual emergency.

## Restoring the `.env` after a disaster

`scripts/restore.sh` deliberately never auto-applies a backup's
`.env` over the live one — it extracts it to `env.restored.backup`
for manual review instead, since the live `.env` might hold newer
secrets than whatever the backup captured. Diff the two by hand and
merge anything relevant yourself.

## Known limitations (read before depending on this in production)

- **No off-host backup storage yet** — see "Backups," above. The
  single highest-priority operational gap.
- **No physical Raspberry Pi hardware has been used yet.** Every
  ARM64 build and disaster-recovery drill in this project's history
  was verified via `qemu-user-static` emulation on a development
  workstation — functionally correct, not performance-tested. See
  `docs/ARM64_REVIEW.md`/`docs/ARM64_TESTING.md`.
  `docs/CLEAN_ENVIRONMENT_TEST.md`'s full deployment walkthrough is
  also emulation-based for the same reason.
  `docs/PRODUCTION_READINESS.md` has the complete, current picture —
  read that document for the full list of what's still open and why,
  rather than this guide trying to keep its own separate copy in
  sync.
- **`.env` backups are unencrypted at rest** (`docs/BACKUP_DR_AUDIT.md`
  #2) — acceptable while backups stay on the same trusted host;
  revisit once off-host storage is added.
- **No Content-Security-Policy header** — deferred pending a real
  browser to verify it doesn't break Django admin's own inline
  scripts; see `docs/PRODUCTION_CONFIG_REVIEW.md`.

## Where to find more

- `docs/ARCHITECTURE.md` — the system design this all implements.
- `docs/PRODUCTION_READINESS.md` — the single consolidated picture of
  what's been verified and what's still open, across every prior
  review.
- `docs/PERMISSIONS.md` — the role/group model in detail.
- `logs/claude/` — a phase-by-phase build log, including every real
  bug found during this project's own development and how it was
  fixed; genuinely useful context if something in production behaves
  unexpectedly and looks like it might be a known, previously-hit
  issue.
