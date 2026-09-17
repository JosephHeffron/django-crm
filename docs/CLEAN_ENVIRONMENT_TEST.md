# Clean-environment end-to-end test

Phase 13 unit 2 — the clean-environment end-to-end test named in the
roadmap. This ties together every script and doc Phases 7-13 have
produced into one continuous walkthrough, run against a genuinely
fresh `git clone` of the real public GitHub repository (not a local
shortcut), following only what's actually documented — no assumed
tribal knowledge from having built this project. It found one more
real, previously-uncaught bug.

## Method

- `git clone https://github.com/JosephHeffron/django-crm.git` into an
  isolated location — a real clone from the real remote, not a local
  copy, confirming the repository is genuinely usable by someone who
  has never touched this project before.
- Followed only what each file's own documentation says: the README
  for native dev setup, `.env.example`'s own comments plus
  `docs/ARCHITECTURE.md` for environment configuration,
  `systemd/crm.service`'s own header comment for installation,
  `scripts/backup.sh`/`scripts/restore.sh`'s own header comments for
  the backup/DR lifecycle.
- Used isolated, throwaway names throughout (a distinct database role,
  a distinct systemd unit name, a distinct Podman project name derived
  from the clone's own directory name) specifically so nothing in this
  test could collide with or affect this workstation's real,
  already-existing local development environment.

## Native dev setup (README) — not completed this unit

Attempted the README's documented PostgreSQL setup
(`sudo -u postgres createuser`/`createdb`) with an isolated role name.
This workstation's sudo requires an interactive password this
environment can't supply. Presented to the user as a choice (run the
three commands themselves, or skip and focus on the production path);
the user chose to skip it and focus this unit on the production
deployment path, which needs no sudo (rootless Podman). **Not a defect
in the README** — this is an environment limitation specific to this
automated test session, not evidence the documented steps are wrong.
Re-verifying the README's native setup fresh remains a reasonable,
cheap thing to do by hand at some point, just not blocking for this
unit.

## Production deployment path — completed end to end

1. **Configuration** — `cp .env.example .env`, filled in following
   only the file's own comments (a generated `DJANGO_SECRET_KEY`,
   `DJANGO_ALLOWED_HOSTS=localhost` for this local test,
   `POSTGRES_PASSWORD`). Confirmed the file still has no
   `DJANGO_SETTINGS_MODULE` line — Phase 11's fix for the bug that
   line caused holds correctly for a genuinely fresh clone.
2. **Systemd install** — installed `systemd/crm.service` exactly as
   its own header comment documents (`mkdir -p
   ~/.config/systemd/user`, copy, `daemon-reload`, `enable --now`),
   adapted only in `WorkingDirectory` (this test's clone path, not
   `~/django-crm`) and the compose file it references
   (`compose.dev.yml`, not `compose.prod.yml` — no real public domain
   exists for this local test to request a real Let's Encrypt
   certificate against; everything else in the unit file was left
   untouched). `systemctl --user enable --now` brought up all three
   containers (`db`, `web`, `caddy`), all reporting healthy.
3. **Real functional verification, not just HTTP status codes** —
   created a superuser, then logged in with a real cookie
   jar/CSRF-token round trip against `https://localhost:8443/`
   (through Caddy, the actual production entry point) and confirmed
   the dashboard rendered showing the logged-in username. Then
   submitted the real "add Company" form the same way (fetching a
   fresh page-specific CSRF token, not reusing an unrelated one from
   elsewhere on the page — the first attempt at this failed with a
   `403` for exactly that reason, corrected) and confirmed the new
   Company record appeared in the real list view afterward. This is
   the application actually working for a fresh deployment, not just
   infrastructure plumbing returning `200`.
4. **Backup** — ran `scripts/backup.sh` against this real deployment's
   real data.
5. **Simulated total disaster** — tore down every container and
   removed every volume (`postgres_data_dev`, `static_files_dev`,
   `media_files_dev`, `caddy_data_dev`, `caddy_config_dev`), confirmed
   nothing remained.
6. **Restore** — ran `scripts/restore.sh` against the backup from step
   4.
7. **Confirmed recovery directly** — the real Company record created
   through the real web form in step 3 was present in the restored
   database; a media-volume marker file was present; the full stack
   was healthy and served real pages again.
8. **Cleanup** — stopped the systemd unit (its own `ExecStop` tore the
   stack down correctly), disabled and removed it, removed all
   volumes and the built image, removed the throwaway backup
   directories.

## A real bug found here, not caught by any prior unit

Step 4's first attempt **silently produced wrong backups**.
`scripts/backup.sh` hardcodes volume names as
`${SERVICE_PREFIX}_media_files`/`caddy_data`/`caddy_config` — correct
for `compose.prod.yml`'s volumes, which carry no suffix, but wrong for
`compose.dev.yml`'s, which all carry a `_dev` suffix (added in Phase 7
specifically so the two stacks never share volumes on the same host).
No prior unit's testing caught this because every prior test that
exercised `scripts/backup.sh` used a `compose.prod.yml`-style copy
(only Caddy's ports changed) specifically to sidestep this exact
mismatch — this is the first time this project tested `backup.sh`
against `compose.dev.yml` itself, which the script's own header
comment had actually offered as a documented, supported usage example.

**Confirmed live, and confirmed deeper than expected**: the resulting
`media_files.tar` was a real file, `podman volume export` exited `0`,
and the backup reported "complete" with no warning — but the tar
contained none of the real marker data. Investigating further:
`podman volume export <name-that-does-not-appear-in-podman-volume-ls>`
on this project's Podman version doesn't reliably fail the way a
missing resource normally would (confirmed directly: exporting a
name that `podman volume ls` doesn't list still exited `0` and
produced a small, valid-looking, empty tar) — so `set -e` alone,
which every other safety mechanism in these scripts has relied on,
was not enough to catch this specific failure mode.

**Fixed two ways**, both re-verified live via a full second
backup → disaster → restore cycle after applying them:

1. Added a `VOLUME_SUFFIX` environment variable (default empty, so
   `compose.prod.yml` behavior is completely unchanged) to both
   `scripts/backup.sh` and `scripts/restore.sh`, appended to every
   volume name — set it to `_dev` when testing against
   `compose.dev.yml`.
2. `scripts/backup.sh` now explicitly checks `podman volume exists`
   before attempting to export, failing loudly with a clear error if
   the target volume genuinely isn't there — rather than trusting
   `podman volume export`'s own exit code, which this unit found
   isn't reliable for this failure mode on this Podman version.

Re-ran the exact same lifecycle (real Company record created through
the real form → backup with `VOLUME_SUFFIX=_dev` → simulated total
disaster → restore with the same flag) after both fixes: the
`media_files.tar` this time genuinely contained the marker file, and
after the full disaster/restore cycle, the real Company record and the
media marker were both confirmed present again, and the app served
real pages through Caddy afterward.

## What this means for real production use

**Compose.prod.yml is unaffected** — its volume names never carried a
suffix, so `VOLUME_SUFFIX`'s default (empty) preserves the exact
behavior already tested throughout Phase 11. This bug only manifested
for the specific combination this unit was the first to actually
try: pointing `scripts/backup.sh`/`scripts/restore.sh` at
`compose.dev.yml`, using their own already-documented `COMPOSE_FILE`
override. Real production backups taken before this fix, against the
real `compose.prod.yml` stack, were not affected by this specific bug.

## Recommendation

The production deployment path — systemd install, real login and CRUD
through the actual web UI, backup, simulated total disaster, and
restore — works end to end for a genuinely fresh clone, following only
what's documented. One real bug was found and fixed along the way,
specifically because this was the first test to exercise a
documented-but-previously-untested code path
(`scripts/backup.sh`/`scripts/restore.sh` against `compose.dev.yml`).
Native dev setup (the README's own path) was not re-verified fresh
this session due to an environment-specific sudo limitation, not a
documentation defect — worth a cheap, separate manual check at some
point, not a blocker for this unit or for calling the production path
production-ready.
