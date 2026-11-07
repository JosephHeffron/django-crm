# Administrator guide

Phase 14 unit 1 — practical, task-oriented documentation for whoever
actually runs this CRM in production. Everything here has already been
established and verified in earlier phases; this guide's job is to
put it in one place organized around what an operator actually needs
to *do*, not to introduce anything new. Where a task needs more detail
than fits here, it links to the document that has it.

This assumes production deployment on an x86-64 Ubuntu 24.04 VPS
(a DigitalOcean droplet) running rootless Podman + Caddy + systemd
user units, per `docs/ARCHITECTURE.md` and ADR 0015. **Nothing has
been deployed yet.** The steps below come from the audit of what a
rootless Ubuntu host needs (`docs/VPS_AUDIT.md` F-VPS-1 to F-VPS-5)
and from Ubuntu's own packages, but none of them has run on the real
droplet. Expect one round of corrections the first time through, and
fix this guide when that happens.

## First-time deployment

Two accounts do the work:

- **root**, over SSH with your key, for system setup only (steps 1-2);
- **`crm`**, a dedicated account **without sudo**, for everything
  that touches the app (steps 3-11). The containers this account runs
  face the internet, so it must not be able to become root (ADR 0005).

Always reach `crm` with `ssh crm@…`, never with `su` or `sudo -u`.
`systemctl --user` needs that user's own login session; from `su` it
fails with *Failed to connect to bus*.

### 1. Create the droplet (DigitalOcean control panel)

- **Account:** turn on two-factor sign-in and a billing alert.
- **Droplet:** Ubuntu 24.04 (LTS) x64, Basic → Regular, 2 vCPU /
  4 GB / 80 GB ($24/month), a New York region, **SSH key**
  authentication (not a password). Weekly droplet backups are an
  optional second layer under the nightly B2 backups (plan §9).
- **Reserved IP:** create one and assign it to the droplet, so the DNS
  records never have to change.
- **Cloud firewall:** inbound TCP **22, 80 and 443** only, attached to
  the droplet. Nothing else: PostgreSQL publishes no port, and Django
  listens on the loopback address only (ADR 0022).

### 2. Prepare the system (as root)

```
ssh root@<reserved-ip>
apt update && apt full-upgrade -y
timedatectl set-timezone America/New_York
apt install -y podman pipx git curl restic uidmap slirp4netns
[ -f /var/run/reboot-required ] && reboot
```

**Swap**, so a memory spike during an image build does not kill
PostgreSQL (audit F-VPS-8: three gunicorn workers plus PostgreSQL on
4 GB is untested):
```
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

**Security updates and SSH.** Both of these should already be true on
a fresh droplet. Check them anyway:
```
systemctl is-enabled unattended-upgrades          # enabled
sshd -T | grep -i '^passwordauthentication'       # passwordauthentication no
```

**Let rootless Caddy bind ports 80 and 443** (audit F-VPS-1). Without
this line, Caddy cannot start:
```
echo 'net.ipv4.ip_unprivileged_port_start=80' > /etc/sysctl.d/90-unprivileged-ports.conf
sysctl --system
sysctl net.ipv4.ip_unprivileged_port_start        # = 80
```

**The `crm` account**, with the subordinate ID ranges rootless Podman
needs (F-VPS-5), lingering so the stack and its timers keep running
with nobody logged in (F-VPS-4), and your SSH key:
```
adduser --disabled-password --gecos "" crm
grep '^crm:' /etc/subuid /etc/subgid
# Each file must print a line such as crm:100000:65536. Only if either printed nothing:
#   usermod --add-subuids 100000-165535 --add-subgids 100000-165535 crm
loginctl enable-linger crm
install -d -m 700 -o crm -g crm /home/crm/.ssh
install -m 600 -o crm -g crm ~/.ssh/authorized_keys /home/crm/.ssh/authorized_keys
```

### 3. Install podman-compose and check Podman (as `crm`)

**Do not use Ubuntu's `podman-compose` package.** Ubuntu 24.04 ships
version 1.0.6, which ignores the `depends_on` health conditions that
`compose.prod.yml` relies on (Caddy waits for a healthy Django,
Django for a healthy PostgreSQL). podman-compose honours them from
version 1.3.0. Install it with pipx instead. Use the same version as
the workstation the stack was verified on (`podman-compose version`
there), and never anything older than 1.3.0:
```
ssh crm@<reserved-ip>
pipx install podman-compose==<version>
pipx ensurepath
exit
```
Then sign in again and check:
```
ssh crm@<reserved-ip>
podman-compose version                             # 1.3.0 or later
podman info --format '{{.Host.Security.Rootless}}' # true
podman unshare cat /proc/self/uid_map              # a second line mapping a range of 65536
loginctl show-user crm --property=Linger           # Linger=yes
```
`systemd/crm.service` finds a pipx install in `~/.local/bin` through
its own `PATH` line (audit F-VPS-2).

### 4. DNS (at Wix, for now)

Add two **A records** pointing at the reserved IP: **`crm`** and
**`new`**. Both are subdomains, so the website customers see today is
not touched. `new` is the website's preview address. Caddy needs a
real website hostname from its first start (ADR 0016). Do not change
the apex or `www` records; that is unit 6. Check before going on:
```
getent hosts crm.heffronexteriorservices.com new.heffronexteriorservices.com
```
Both should print the reserved IP.

### 5. Clone and configure (as `crm`)

```
git clone https://github.com/JosephHeffron/django-crm.git ~/django-crm
cd ~/django-crm
cp .env.example .env && chmod 600 .env
```
(`systemd/crm.service` assumes exactly `~/django-crm`.) Edit `.env`
and set:

| Setting | Value |
|---|---|
| `DJANGO_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"` |
| `DJANGO_ALLOWED_HOSTS` | `crm.heffronexteriorservices.com` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `https://crm.heffronexteriorservices.com` |
| `CRM_HOST` | `crm.heffronexteriorservices.com` |
| `WEBSITE_HOST` | `new.heffronexteriorservices.com` (the apex at the cutover) |
| `WEBSITE_WWW_HOST` | leave unset until the cutover |
| `POSTGRES_PASSWORD` | `openssl rand -hex 32` |

Leave `DJANGO_SETTINGS_MODULE` **unset**. `.env.example` explains
why: setting it once booted a production container with `DEBUG=True`.
**Never put a space in a value.** `scripts/backup.sh` reads this file
as shell, and a space turns the rest of the line into a command. Check
it the same way the backup reads it:
```
sh -c 'set -e; set -a; . ./.env' && echo ok
```
The backup settings come in step 9.

### 6. Start the stack (as `crm`)

```
mkdir -p ~/.config/systemd/user
cp systemd/crm.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now crm.service
```
The first start builds the web image and pulls PostgreSQL and Caddy.
Expect several minutes on 2 vCPU (`TimeoutStartSec=600` allows for
it). Caddy then requests certificates for both hostnames, which needs
step 4's records to resolve.

### 7. Verify (as `crm`)

```
cd ~/django-crm
./scripts/deploy.sh status
```
It should print four healthy lines: db and web, the CRM through Caddy,
and the website. Then:

- **Caddy sees real visitor addresses (ADR 0022).** Do not skip this:
  if it fails, ten wrong passwords from anyone lock everybody out of
  signing in.
  ```
  ss -tlnp | grep -E ':(80|443) '
  ```
  The process on both ports must be **`caddy`**. If it is
  `rootlessport`, Caddy is behind Podman's port forwarder rather than
  on the host network. Stop, and do not let anyone sign in until it
  is fixed.
- **Private photos stay private:**
  ```
  curl -s -o /dev/null -w '%{http_code}\n' https://crm.heffronexteriorservices.com/media/private/x.jpg   # 404
  ```
- **From your phone, on mobile data,** open
  `https://crm.heffronexteriorservices.com` and
  `https://new.heffronexteriorservices.com`.

The stack starting at all is also the answer to audit F-VPS-3 (the
`:Z` mount option on a host without SELinux): if Caddy serves both
sites, it could read its mounts.

### 8. Accounts

```
podman exec -it django-crm_web_1 python manage.py createsuperuser
```
Sign in, then **create a second Owner** under Team → *Add someone*.
Either Owner can set the other's password, which is the only way back
in from inside the app for an owner who forgets theirs (ADR 0021).
Then add the staff accounts.

### 9. Backups, and the alarm for when they stop

1. **Backblaze B2:** a private bucket, and an application key scoped
   to that bucket only (not the account's master key).
2. **Healthchecks.io** (free plan): a check named for the backup, with
   a period of **1 day** and a grace time of **2 hours**, alerting by
   email. It is a dead man's switch: it alerts when the daily ping
   *stops*. That covers a backup that fails, a push that fails, and a
   timer that never runs, which no error handler can report. The email
   comes from their servers, so DigitalOcean's SMTP block does not
   matter. Any service that alerts on a missing HTTP request works the
   same way.
3. **Add to `.env`:**
   ```
   RESTIC_REPOSITORY=b2:<bucket>:django-crm
   RESTIC_PASSWORD=<openssl rand -hex 32>
   B2_ACCOUNT_ID=<the application key's ID>
   B2_ACCOUNT_KEY=<the application key>
   BACKUP_PING_URL=<the check's ping URL>
   ```
   **Keep a copy of `RESTIC_PASSWORD` off this server** (a password
   manager). It cannot be recovered, and the only other copy is inside
   the backups it encrypts (audit F-BAK-5).
4. **Install the timer and run one backup now:**
   ```
   cp systemd/crm-backup.service systemd/crm-backup.timer ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now crm-backup.timer
   ./scripts/backup.sh
   ```
   The output should end with `off-host push complete` and then
   `monitoring notified`, and the check on healthchecks.io should turn
   green. **No ping is sent unless the backup reached B2.** A local-only
   backup does not count, so a missing or wrong `RESTIC_REPOSITORY`
   shows up as an alert rather than as silence.

### 10. Follow-up timer

```
cp systemd/crm-followups.service systemd/crm-followups.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now crm-followups.timer
```
This raises repeat-service follow-ups once a day at 07:00. Skipping
it costs no data; follow-ups simply never appear on their own.

### 11. The restore drill, before any real data

Restore last night's backup into a scratch database on this droplet,
following `docs/TESTING_INSTRUCTIONS.md` §7, and write down what
happened. The restore path has never run end to end (audit F-BAK-1),
and once real customer data is in, a restore that does not work is
discovered at the worst possible moment. Expect the script to need a
fix; that is what the drill is for.

### What the first run settles

None of this has run on the droplet. The parts most likely to need a
correction:

- **podman-compose ≥ 1.3 on Podman 4.9.3.** The workstation runs a
  newer Podman. If `podman-compose up` misbehaves, the version pairing
  is the first suspect.
- **Container names.** `deploy.sh` and `backup.sh` expect
  `django-crm_db_1` and `django-crm_web_1`. `podman ps` shows the
  real names; if they differ, those two scripts need the new ones.
- **The `ss` check in step 7**, which is the only proof that ADR 0022
  works.

Record what happened in the phase log, and fix this guide in the same
PR.

### Updating later

Deploy updates with `./scripts/deploy.sh <ref>` (see *Deploying an
update*, below). A deploy now counts as healthy only when db and web
are healthy **and** Caddy is serving the CRM and the website, so a
Caddyfile it rejects rolls back instead of taking both sites offline
with a "success".

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

**Private media.** `media/private/` holds job photos and profile
pictures, and the web server deliberately does **not** serve it:
both Caddyfiles answer `/media/private/*` with 404, and those files go
through Django, which checks who's asking and whether they're allowed to
see the job the photo belongs to (`apps/jobs/media.py`). Everything else
under `media/` — the business logo — is public on purpose. If you ever
change the proxy config, keep that 404: without it the files are
readable by anyone with the URL.

Reading them through Django costs a worker for the length of the
download, which is the right trade at this size. If photo volume ever
makes that hurt, the upgrade is an internal redirect (Caddy
`handle_response` serving the file itself), and it needs testing on the
real machine before being trusted.

**Place service addresses on the map** (Phase 17.5 step 8, ADR 0011).
The Map page shows addresses that have coordinates; getting them calls
OpenStreetMap's Nominatim, which allows one request a second, so it is a
command rather than something a page waits on:
```
podman exec -it django-crm_web_1 python manage.py locate_properties --limit 50
```
It only touches addresses with no coordinates, unless you pass `--redo`.
Addresses Nominatim can't find are named in the output, and anyone can
drop those pins by hand on the Map page instead. Each address is sent
once; the answer is stored. Run it after importing customers, or on a
timer beside the follow-up generator.

Two things about the map reach the internet, and nothing else does:
the address lookups above, and the map images staff browsers fetch from
`tile.openstreetmap.org` (which the production CSP names explicitly, and
nothing else). If the machine is offline the Map page says so and the
rest of the app is unaffected.

**Leaflet is vendored**, not installed from a CDN —
`static/vendor/leaflet/` with its version, licence and checksums in the
README there. Dependabot does not see it, so updating is a deliberate
step: replace the files, re-run the checksums, record them in the same
commit.

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

**Team accounts** are managed in the app, by the Owner, at
**Team** (from your own profile). No Django admin, and no shell: the
Owner role deliberately does not grant admin access, so this page is
the whole of it.

- **Add someone:** Team → *Add someone*. You set their username, name,
  role and first password in one step, then tell them the password —
  the app sends no email (ADR 0021). They can change it themselves
  afterwards from their profile.
- **Give or change a role:** open the person → *What they can reach*.
  Exactly one of **Owner**, **Sales Rep** or **Cleaner**, or none —
  see `docs/PERMISSIONS.md`. Someone with no role can sign in but sees
  nothing beyond a "no role assigned" notice, by design. Superusers are
  always treated as Owner.
- **Reset a forgotten password:** open the person → *Set a new
  password*, then tell them what it is. It signs that person out on
  every device, which is what you want if the reason is a shared or
  stolen password. This is the only recovery path: the app sends no
  email, by decision (ADR 0021), because the host blocks outbound SMTP.
  If you are unavailable, a locked-out person waits — that is the
  accepted cost.
- **If *you* are the one locked out**, there is no in-app route — the
  page refuses to set your own password, and *Change password* asks for
  the one you have forgotten. Two answers, in order of preference:
  - **Keep a second Owner account.** Either Owner can reset the other
    from the Team page, so recovery stays in the app and needs no
    server access. Do this before you need it.
  - **Otherwise, on the server**, with shell access:
    ```
    podman exec -it django-crm_web_1 python manage.py changepassword <username>
    ```
    It prompts twice and applies the same password rules. This is the
    only path if you are the sole Owner, so losing both your password
    and your server access means losing administrative control of the
    CRM — the database would have to be edited directly.
- **Ten wrong passwords locks a sign-in attempt out for fifteen
  minutes**, counted per address and per username on both the app's
  sign-in page and `/admin/login/` (ADR 0020). It clears itself; there
  is nothing to unlock. If somebody is stuck and cannot wait, **set
  them a new password** — doing that clears their count as well, so
  they can sign in straight away. (Their *address* may still be
  counting if the failures came from one machine; that expires on its
  own within the window.)
- **Everything on this page is recorded.** Adding an account,
  changing a role, turning sign-in off, setting somebody's password,
  and changing their hourly rate or working days all appear in
  **Settings → Change log** (Owner-only) with who did it and when. The
  password itself is never recorded — only that it changed. Nothing
  emails the person, so this log is the only trace, and the rate
  history is there too: `hourly_rate: 22.00 → 24.50`.
  A password change made in the Django admin instead is recorded by
  the admin's own history, at
  `/admin/auth/user/<id>/history/`, not here — the app's log covers
  changes made through the app, as it always has.
- **Stop someone signing in:** open the person → *What they can reach*
  → turn off **Can sign in**. Use this rather than deleting an account.
  Every job, quote and task they created still refers to them, and the
  database refuses to delete a row other rows depend on, so
  deactivating is both the reversible answer and the only one that
  works. Their history stays intact and their name keeps appearing
  where it should.

**Branding:** set `CRM_BRAND_NAME` (and optionally
`CRM_BRAND_SHORT_NAME`, shown under the home-screen icon, ~12
characters) in `.env`; the business timezone is `CRM_TIME_ZONE`
(default `America/New_York`). Restart the stack to apply.

**Help and feedback email:** set `CRM_SUPPORT_EMAIL` in `.env` to the
address staff should write to. It appears as the sidebar's **Ideas**
and **Report a bug** links and in the help (?) button. Left blank, those
links are hidden. Keep the address in `.env` only — the repository is
public.

**Business name, logo, and currency** are set by the Owner in the app
(gear → Business settings) and stored in the database; the logo file
lives under `media/branding/`, so it's covered by the existing
`media_files` backup. `CRM_BRAND_NAME` remains the default name until
one is set there.

## Follow-ups, and checking the timers are alive

Two things run on a schedule: the nightly backup and the daily
follow-up generation (07:00). Both are rootless systemd *user* timers,
so every command below needs `--user` and must run as the deployment
account.

```
systemctl --user list-timers 'crm-*'
```

That one line is the health check. It shows when each timer last ran
and when it fires next. What to look for:

- **`LAST` more than a day ago** on `crm-followups.timer` — the timer
  is not firing. Check `systemctl --user is-enabled crm-followups.timer`.
- **`n/a` under `LAST`** — it has never run since the unit was
  installed.
- **The timer missing entirely** — it was never enabled, or
  `daemon-reload` was not run after copying the units in.

Then the detail:

```
journalctl --user -u crm-followups.service --since '2 days ago'
```

A healthy run prints one line: `Created N follow-up task(s) for
<date>.` `N` is legitimately 0 most days — a follow-up is only raised
when a customer passes their service's interval — so **zero is not a
failure**. A *failed* run is a non-zero exit, which systemd records and
this command shows.

### Why a missed day is not a lost day

`generate_followups` is idempotent, and whether a customer is due is
computed from "has the interval elapsed since their last job or contact
touch", not from "did we run yesterday". A customer who became due
yesterday is still due today, so a skipped run raises their follow-up a
day late rather than never. The same is **not** true of a missed
backup, which is a permanent hole — hence `Persistent=true` on both
timers, but far more urgency about the backup one.

What is not self-correcting is the timer being *broken* rather than
skipped: a renamed container, a stack that never came up, the units
never enabled. Then follow-ups stop and the only symptom is an absence
of them, which is easy not to notice for weeks. That is what the
`list-timers` check above is for, and why `scripts/followups.sh` exits
non-zero on every failure path rather than shrugging.

### Running it by hand

```
./scripts/followups.sh                      # same as the timer does
./scripts/followups.sh --date 2026-09-29    # as if it were that day
```

Safe at any time, as often as you like.

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

**A change to the public website only** (pages, stylesheet, images —
anything under `website/` except `website/partials/`) can skip the
rebuild and restart:
```
./scripts/deploy.sh --website-only <git-ref>
```
It refuses, and changes nothing, if the revision touches anything else
compared with what is deployed. The same rule (`scripts/change-scope.sh`)
lets CI run only the website's checks on such a pull request. After
checking out, it fetches the home page through Caddy on this host
(`https://$WEBSITE_HOST/`, certificate checked) and expects the shared
header in it. If that check fails, it puts the previous revision back
and exits non-zero. `docs/WEBSITE.md` has the details.

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

### Off-host backup storage (recommended before trusting this with real data)

By default, backups live on the same disk as the application data
they protect — one failed volume, or one deleted droplet, takes out
both at once. Set this up to close that
gap (`docs/BACKUP_DR_AUDIT.md`'s formerly-open finding #1,
`docs/decisions/0006-offhost-backups-restic.md`):

1. Install `restic` on the host (not in any container):
   ```
   sudo dnf install restic      # Fedora
   sudo apt install restic      # Debian/Ubuntu
   ```
2. Create a [Backblaze B2](https://www.backblaze.com/cloud-storage)
   account and bucket, then an **application key scoped to that one
   bucket only** (B2's "Application Keys" page — not the account's
   master key).
3. Add to `.env` (see `.env.example`'s own comments for the full
   explanation):
   ```
   RESTIC_REPOSITORY=b2:your-bucket-name:django-crm
   RESTIC_PASSWORD=<a long random value — generate with `openssl rand -base64 32`>
   B2_ACCOUNT_ID=<the application key's ID>
   B2_ACCOUNT_KEY=<the application key itself>
   ```
   **Store a copy of `RESTIC_PASSWORD` somewhere other than this
   host** (a password manager, printed and kept safely) — restic has
   no password recovery, and a copy that only lives on the host being
   protected defeats the point.
4. Run `./scripts/backup.sh` — it now pushes to the off-host
   repository automatically after the local backup completes (visible
   in its output: `--- pushing ... off-host via restic ---`). Every
   future backup, including the daily timer-triggered one, does this
   automatically from here on; no further setup needed.
5. Set `BACKUP_PING_URL` to a dead-man's-switch check (healthchecks.io
   or similar; *First-time deployment* step 9). `backup.sh` requests it
   only after the off-host push succeeds. A day without that request,
   for any reason including the timer not running, becomes an email
   from the monitoring service (audit F-BAK-3, F-BAK-4).

If a disaster destroys the local `backups/` directory itself (not just
the running containers/volumes — the actual scenario off-host storage
exists for), recover it first:
```
./scripts/restore_offhost.sh            # pulls the latest snapshot back into backups/
./scripts/restore.sh <timestamp> --yes  # then proceeds exactly as below
```

## Disaster recovery

If the server is genuinely lost (destroyed droplet, failed volume,
unrecoverable host) and you're rebuilding from a backup held
elsewhere:

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

- **Off-host backup storage requires setup** — the mechanism is built
  and verified (see "Backups," above), but nothing is pushed off-host
  until you've created a real Backblaze B2 account/bucket/key and set
  the `RESTIC_*`/`B2_*` variables in `.env` yourself. Until then, this
  deployment has local-only backups, same as before Phase 15, and
  `BACKUP_PING_URL` is deliberately never pinged, so the monitor will
  say so.
- **No server has been deployed to yet.** Every build and
  disaster-recovery drill in this project's history ran on a
  development workstation — functionally correct, not
  performance-tested, and never on the host that will serve real
  traffic. `docs/CLEAN_ENVIRONMENT_TEST.md`'s deployment walkthrough
  is a workstation run for the same reason. `docs/VPS_AUDIT.md` lists
  what the move still needs; the earlier ARM64 work was dropped with
  the Raspberry Pi target (ADR 0015).
  `docs/PRODUCTION_READINESS.md` has the complete, current picture —
  read that document for the full list of what's still open and why,
  rather than this guide trying to keep its own separate copy in
  sync.

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
