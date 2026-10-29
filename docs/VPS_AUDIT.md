# VPS deployment audit

**Audit only.** No code, configuration, infrastructure or DNS was
changed in producing this document. Dated 2026-10-27, against
`main` at commit `38e9e31`.

Every finding is labelled **Verified** (with `path:line`),
**Assumption** (reasoned, not proven here) or **Open** (needs the
owner, or a machine this audit does not have). Severity follows the
brief: **P0** before the CRM holds real data, **P1** before the public
website launches, **P2** recommended, **P3** future.

What this audit deliberately does not do: re-run the earlier audits.
`docs/PRODUCTION_READINESS.md`, `docs/SECURITY_REVIEW.md`,
`docs/PRODUCTION_CONFIG_REVIEW.md` and `docs/BACKUP_DR_AUDIT.md` are
treated as established except where a VPS move changes the answer or
where their claim has gone stale — those are called out by name in
§7.

---

## 1. Summary

**Not ready to go live, and close.** Nothing in this codebase is
architecturally wrong for an x86-64 VPS: the image is
architecture-neutral, the stack is three ordinary containers, and the
security posture (CSP, private media, roles) is stronger than most
projects this size. What stands between it and a real business using it
is a short list of concrete, mostly small things — one of which will
stop the stack starting at all on a fresh Ubuntu box.

### The top five blockers

| # | Blocker | Severity | Why it blocks |
|---|---|---|---|
| 1 | **Rootless Caddy cannot bind ports 80/443**, and nothing in the repo or docs sets `net.ipv4.ip_unprivileged_port_start` | **P0** | `compose.prod.yml:71-73` publishes 80 and 443; ADR 0005 runs the whole stack rootless. On a fresh Ubuntu 24.04 host the unprivileged port floor is 1024, so `podman-compose up` fails on the Caddy container. This is the "nothing works and the logs look unrelated" surprise |
| 2 | **No in-app way to create a user, and no password reset** | **P0** | `apps/users/urls.py:6-21` is login, logout and password-*change* only. Onboarding an employee, or recovering one who is locked out, requires the Django admin — and there is no reset-by-email flow at all, because no email is configured (blocker 3) |
| 3 | **No outbound email** | **P0** | No `EMAIL_BACKEND`, `EMAIL_HOST` or `DEFAULT_FROM_EMAIL` anywhere in `config/settings/`. Django's default would try localhost:25. Password resets, quote confirmations and owner notifications all depend on this |
| 4 | **`scripts/restore.sh` has never run end to end** | **P0** | `docs/PROJECT_STATE.md`'s Known issues. Backups that have never been restored are a hope, not a backup — and this is the one thing that cannot be fixed after the data is real |
| 5 | **One Caddy site address, taken from `{$DJANGO_ALLOWED_HOSTS}`** | **P1** | `Caddyfile:16`, and its own comment at `Caddyfile:7-15` says a comma-separated value parses as one invalid address. Serving the apex and `www` alongside `crm.` needs a second site block and a second variable, plus an update to the test that validates both Caddyfiles |

A sixth, listed here because it is cheap and a public website makes it
reachable: **the Django admin login page is on the internet with no
rate limiting** (§4, F-PUB-2 and F-SEC-1).

---

## 2. Architecture as actually configured

### Production (`compose.prod.yml`)

```
            :80 :443  (host ports, published by Podman)
                 |
        +--------v---------+   only container reachable from outside
        |  caddy:2.11.4    |   HTTPS via Let's Encrypt, site address
        |  (alpine)        |   = {$DJANGO_ALLOWED_HOSTS}
        +---+----------+---+
            |          |  reads static_files:/srv/static  (ro)
            |          |  reads media_files:/srv/media    (ro)
            |          \_ /media/private/* -> respond 404
            | reverse_proxy web:8000
        +---v--------------+
        |  web             |  gunicorn, 3 workers, no published port
        |  python:3.12-slim|  DJANGO_SETTINGS_MODULE baked to production
        +---+--------------+
            | POSTGRES_HOST=db (compose override)
        +---v--------------+
        |  db              |  postgres:18-alpine, pg_isready healthcheck
        +------------------+   volume postgres_data:/var/lib/postgresql
```

- **Verified** `compose.prod.yml:13-97` — three services, named volumes
  `postgres_data`, `static_files`, `media_files`, `caddy_data`,
  `caddy_config`; `web` has no published port; `caddy` publishes 80 and
  443 (`:71-73`); `caddy` waits on `web` being *healthy* (`:68-70`) and
  `web` on `db` being healthy (`:44-46`).
- **Verified** `Containerfile:6` — `FROM python:3.12-slim`, no
  `--platform`; `:22-25` creates a non-root `django` user (uid 1000)
  and runs as it; `:35` gunicorn with `--workers 3`.
- **Verified** `scripts/entrypoint.sh` runs `migrate` and
  `collectstatic` (so `scripts/deploy.sh:105-108` deliberately does
  not duplicate them).
- **Verified** `systemd/crm.service:27-41` — a **user** unit,
  `Type=oneshot` with `RemainAfterExit=yes`,
  `WorkingDirectory=%h/django-crm`,
  `ExecStart=/usr/bin/podman-compose -f compose.prod.yml up -d`,
  `TimeoutStartSec=600`. Linger is documented as an install step at
  `:17`, not automated.
- **Verified** `config/settings/production.py` — `DEBUG=False` (`:7`),
  `ALLOWED_HOSTS` from a comma-separated env var (`:9-11`),
  `CSRF_TRUSTED_ORIGINS` likewise (`:13-17`),
  `SECURE_PROXY_SSL_HEADER` (`:21`), `SECURE_SSL_REDIRECT` with
  `/health/` exempt (`:22`, `:37`), HSTS one year with
  `includeSubDomains` and `preload` (`:41-43`), and a strict CSP
  (`:66-84`): `default-src 'none'`, nonce-based script and style, and
  exactly one external origin — `https://tile.openstreetmap.org` for
  map tiles (`:73`).
- **Verified** `config/settings/base.py:113` — `CSRF_COOKIE_HTTPONLY`,
  so no script can read the CSRF token; `:119` business timezone from
  `CRM_TIME_ZONE`, default `America/New_York`.

### Development

- **Verified** `compose.dev.yml` + `Caddyfile.dev` exist for a local
  stack; `.env.example:36-42` documents that `POSTGRES_HOST=localhost`
  is for native development and both compose files override it to the
  `db` service name.
- Tests run natively against a local PostgreSQL (ADR 0002: PostgreSQL
  in development and production, never SQLite).

### Scheduled work

- **Verified** `systemd/crm-backup.{service,timer}` — daily,
  `Persistent=true`, runs `%h/django-crm/scripts/backup.sh`.
- **Verified** `systemd/crm-followups.{service,timer}` — the follow-up
  generator (Phase 19).
- Both are user units, so both depend on linger being enabled.

---

## 3. Findings

### x86-64 / Ubuntu 24.04

| ID | Finding | Evidence | Status | Sev |
|---|---|---|---|---|
| F-VPS-1 | **Rootless Caddy cannot bind 80/443 on a default Ubuntu host.** Nothing in the repo or docs sets `net.ipv4.ip_unprivileged_port_start`; the only mention of ports is the published mapping itself | `compose.prod.yml:71-73`; repo-wide grep for `ip_unprivileged_port_start` returns nothing; ADR 0005 (rootless) | **Verified** (absence) | **P0** |
| F-VPS-2 | The systemd unit hardcodes `/usr/bin/podman-compose`. Ubuntu 24.04 ships `podman-compose` in *universe*; installed any other way (pipx, pip) the binary is not at that path, and the unit fails with a bare 203/EXEC | `systemd/crm.service:35`; `scripts/deploy.sh:99-160` also calls `podman-compose` by name | **Verified** (path), **Open** (which package the VPS will have) | P1 |
| F-VPS-3 | `:Z` SELinux relabel on the Caddyfile bind mount. Ubuntu uses AppArmor; Podman is expected to no-op relabelling when SELinux is disabled, so this is probably harmless — but it is unverified on Ubuntu, and the comment above it describes Fedora behaviour as the reason it exists | `compose.prod.yml:75-81` | **Assumption** | P1 |
| F-VPS-4 | `loginctl enable-linger` is a documented manual step, not part of any script. Without it the stack and both timers stop when the deploy user's session ends | `systemd/crm.service:17`; `docs/ADMIN_GUIDE.md:49` | **Verified** | P1 |
| F-VPS-5 | subuid/subgid ranges for the deployment user are assumed, never checked. Rootless Podman needs them; a user created with plain `useradd` may have none | no reference anywhere in `systemd/`, `scripts/`, or `docs/ADMIN_GUIDE.md` | **Verified** (absence) | P1 |
| F-VPS-6 | The deployment guide is written for a Raspberry Pi 5 and gives Fedora/Raspberry Pi OS package commands | `docs/ADMIN_GUIDE.md:10`, `:282-283` | **Verified** | P1 |
| F-VPS-7 | Nothing in the build is ARM-only: no `--platform`, no `arch`-conditional logic. ARM is only comments plus a standalone validation script | `Containerfile:6`, `:30`; `systemd/crm.service:38-39`; `scripts/deploy.sh:8`; `scripts/test-arm64.sh:1-12` | **Verified** | P3 |
| F-VPS-8 | `--workers 3` and `TimeoutStartSec=600` were sized for a 4-core Pi. On a 2 GB VPS also running PostgreSQL and Caddy, three gunicorn workers plus Postgres is plausible but untested; memory is the constraint to watch, not CPU | `Containerfile:30-35`; `systemd/crm.service:38-41` | **Assumption** | P2 |

### Two sites behind one Caddy

| ID | Finding | Evidence | Status | Sev |
|---|---|---|---|---|
| F-CAD-1 | One site address, interpolated from the same variable Django uses for `ALLOWED_HOSTS`. Its own comment states that a comma-separated value parses as a single invalid address, so this cannot serve three hostnames as written | `Caddyfile:7-15`, `:16`; `config/settings/production.py:9-11` | **Verified** | **P1** |
| F-CAD-2 | The private-media guard adapts **both** Caddyfiles with `caddy adapt` and asserts that every `/media/private/*` matcher sorts ahead of every `/media/*` `file_server`, across all servers in the adapted config. A second site is safe **unless** the website serves its own `/media/*` path, which would trip this — correctly | `apps/jobs/tests/test_private_media.py:304-347`, `:432-449` | **Verified** | P1 |
| F-CAD-3 | The same test family runs `caddy validate` with only `DJANGO_ALLOWED_HOSTS` in the environment. A new variable for the website hostnames must be given a value there in the same change, or validation fails and the guard goes red for an unrelated reason | `apps/jobs/tests/test_private_media.py:462-470`, env at `:316-318` | **Verified** | P1 |
| F-CAD-4 | Security headers are set per-block (static, media) rather than site-wide, deliberately: a site-wide block produced each header twice on the proxied path. A website block therefore needs its own headers; the CRM's cannot simply be hoisted | `Caddyfile:20-29`, `:33-37`, `:64-69` | **Verified** | P1 |
| F-CAD-5 | Django's CSP applies only to responses Django renders. A static site served straight from disk by Caddy gets no CSP, no `X-Frame-Options` and no `Referrer-Policy` unless its own block sets them | `config/settings/production.py:66-84`; `Caddyfile:30-70` | **Verified** | P2 |
| F-CAD-6 | HSTS is sent with `includeSubDomains` and `preload`. Served from `crm.example.com` it claims authority over `*.crm.example.com` only, so it does **not** constrain the apex — but preload submission is a one-way door and should wait until both sites are HTTPS-only | `config/settings/production.py:41-43` | **Verified** | P3 |

### Public surface

| ID | Finding | Evidence | Status | Sev |
|---|---|---|---|---|
| F-PUB-1 | Exactly nine application routes answer a signed-out visitor, each with a stated reason, and the list is enforced by a sweep that walks the URL resolver rather than a hand-kept list: `/accounts/login/`, `/accounts/logout/`, `/health/`, `/manifest.webmanifest`, `/sw.js`, `/offline/`, `/branding/logo/`, `/leads/` and `/deals/` (the last two are permanent redirects) | `apps/core/tests/test_access_sweep.py:49-59`; paths resolved live | **Verified** | — |
| F-PUB-2 | **`/admin/login/` answers 200 to anyone**, and the access sweep deliberately excludes `admin/` routes from its walk. The Django admin is also the only way to create a user (F-CRM-1), so it cannot simply be blocked | `apps/core/tests/test_access_sweep.py:80` (admin skipped); `config/urls.py:22`; measured: `/admin/` → 302 → `/admin/login/` → 200 | **Verified** | P1 |
| F-PUB-3 | `/branding/logo/` serves the business logo unauthenticated by design (it is on the sign-in page). Nothing else public exposes business data | `apps/core/tests/test_access_sweep.py:55` | **Verified** | — |
| F-PUB-4 | `/health/` returns only `{"status","database"}` as `ok`/`error`, 503 on failure. Suitable for an uptime monitor as-is, and exempt from the SSL redirect so a plain-HTTP probe works | `apps/core/views.py:432-457`; `config/settings/production.py:37` | **Verified** | — |

### Security

| ID | Finding | Evidence | Status | Sev |
|---|---|---|---|---|
| F-SEC-1 | **No rate limiting anywhere**, and none is possible per-process-safely today: `requirements.txt` has no `django-axes`/`django-ratelimit`, and no `CACHES` is configured, so Django falls back to per-process locmem — one bucket per gunicorn worker, three workers | `requirements.txt:1-5`; no `CACHES` in `config/settings/*`; `Containerfile:35` | **Verified** | P1 |
| F-SEC-2 | No MFA. Phase 23 (two-factor) is the next unstarted roadmap item | `docs/ROADMAP.md` Phase 23 | **Verified** | P2 |
| F-SEC-3 | The photo pipeline re-encodes every upload and drops all metadata, with size, pixel and edge caps — directly reusable for public uploads | `apps/jobs/photos.py:38`, `:41`, `:44`, `:64-110` (`exif_transpose` at `:103`, no `exif=` passed at `:110`) | **Verified** | — |
| F-SEC-4 | Private media is refused by Caddy and served only through Django's own permission check | `Caddyfile:40-60`; `apps/jobs/media.py` | **Verified** | — |

### CRM gaps that block day-to-day business use

| ID | Finding | Evidence | Status | Sev |
|---|---|---|---|---|
| F-CRM-1 | No in-app user creation. An employee is onboarded in the Django admin | `apps/users/urls.py:6-21`; `apps/users/profile_urls.py:10-16` (profile and team pages only, no create) | **Verified** | **P0** |
| F-CRM-2 | No password reset. A locked-out employee needs the owner and the admin | `apps/users/urls.py:9-20` is password-*change*, which requires being signed in; repo grep for `PasswordReset` finds none outside tests | **Verified** | **P0** |
| F-CRM-3 | No outbound email configured at all | no `EMAIL_BACKEND`/`EMAIL_HOST`/`DEFAULT_FROM_EMAIL` in `config/settings/*` | **Verified** | **P0** |
| F-CRM-4 | A payment cannot be corrected and an expense cannot be deleted in the app, though the permissions are granted. Since Phase 20 a payment is the primary record that money arrived, so a mistyped one matters more than it used to | `docs/PROJECT_STATE.md` Known issues; `docs/PERMISSIONS.md` | **Verified** | P1 |
| F-CRM-5 | A service type cannot be created in the app; `jobs.add_servicetype` is granted with no code path | `docs/PROJECT_STATE.md` Known issues | **Verified** | P2 |
| F-CRM-6 | Known, accepted calendar edges: a job running past midnight is placed on its start date only; the spring-forward 2:00-3:00am slot resolves elsewhere | `docs/PROJECT_STATE.md` Known issues; `apps/jobs/calendar.py` | **Verified** | P3 |

### Backups and disaster recovery

| ID | Finding | Evidence | Status | Sev |
|---|---|---|---|---|
| F-BAK-1 | **The restore path has never been run end to end.** The drill is written down; it needs a host to run on, which a VPS finally provides | `docs/PROJECT_STATE.md` Known issues; `docs/TESTING_INSTRUCTIONS.md` §7 | **Verified** | **P0** |
| F-BAK-2 | Coverage is better than the brief assumed: each run produces `db.dump`, `media_files.tar`, `caddy_data.tar`, `caddy_config.tar`, `env.backup` and a manifest — so media, `.env` **and** Caddy's certificates are all included | `scripts/backup.sh:14-15`, `:3-5` | **Verified** | — |
| F-BAK-3 | **A failed backup is silent.** No `OnFailure=`, no mail, no alerting in the unit or the script; a timer that starts failing looks identical to one that is working | `systemd/crm-backup.service` (no `OnFailure`), `scripts/backup.sh` (no alerting) | **Verified** (absence) | P1 |
| F-BAK-4 | restic must be installed on the host, not in a container, and the off-host push is skipped silently when `RESTIC_REPOSITORY` is unset — which is also how a misconfigured deployment looks | `.env.example:44-61`; `scripts/backup.sh:36-40` | **Verified** | P1 |
| F-BAK-5 | `.env` is inside the backup, and `.env` holds the B2 credentials and `RESTIC_PASSWORD`. That is correct for restoring, and it means the restic password must also be kept somewhere else entirely — the repo says so | `.env.example:52-59`; `scripts/backup.sh:14-15` | **Verified** | P2 |
| F-BAK-6 | Nothing backs up the static website's files (they do not exist yet). Where they live decides whether they need their own coverage or come back with the repo | — | **Open** | P1 |

### Tests

| ID | Finding | Evidence | Status | Sev |
|---|---|---|---|---|
| F-TST-1 | Suite result for this audit: see §6. The suite is large and genuinely behavioural, and three guards are unusual enough to name: the resolver-walking access sweep, the `caddy adapt` proxy-config assertions, and a backup-integrity test | `apps/core/tests/test_access_sweep.py`; `apps/jobs/tests/test_private_media.py:404-470`; `apps/core/tests/test_backup_integrity.py` | **Verified** | — |
| F-TST-2 | CI runs `check`, `makemigrations --check --dry-run`, `migrate`, the full suite and lint on `ubuntu-latest`, and installs the Caddy binary specifically so the proxy-config tests are not skipped | `.github/workflows/ci.yml:11`, `:54-66`, `:69-81` | **Verified** | — |
| F-TST-3 | Nothing tests a public form, because none exists: no CSRF-on-public-origin test, no spam/rate-limit test, no test that a public route exposes no customer data beyond what F-PUB-1 lists | — | **Verified** (absence) | P1 |
| F-TST-4 | The proxy-config tests cover one site. A second site block needs its own assertions — at minimum that the website's routes cannot reach `/media/private/*` or the Django proxy | `apps/jobs/tests/test_private_media.py:432-449` | **Verified** | P1 |
| F-TST-5 | No test covers the systemd units, linger, subuid or the port sysctl. These are deployment facts a test suite cannot see; they belong in a provisioning checklist with explicit verification commands | — | **Verified** (absence) | P2 |

---

## 4. Reusable as-is / needs modification / missing

### Reusable as-is for a website quote form

| Thing | Path | Note |
|---|---|---|
| `Contact` with `status=lead` | `apps/crm/models.py:60`, `:65` | `Status.LEAD` exists; no `Lead` model to revive |
| `LeadSource.WEBSITE` | `apps/crm/models.py:70` | The exact value a website submission wants |
| Duplicate detection | `apps/crm/duplicates.py:50` (`likely_duplicates`), `:91` (`reasons`) | Warns, never blocks; takes name/email/phone and needs no request |
| `Property` (service address) | `apps/crm/models.py:141` | Requires `street`, `city`, `state`, `postal_code` — all four, no defaults |
| `Task` (follow-up for the owner) | `apps/crm/models.py:231` | A general task needs only title, assignee, creator |
| Change-log writer | `apps/crm/audit.py:27` (`record`) | Explicit call, not a signal — a public create can record itself |
| Photo intake | `apps/jobs/photos.py:64` (`process_photo`) | Re-encodes, strips metadata, caps size/pixels/edge |
| Private media serving | `apps/jobs/media.py`; `Caddyfile:40-60` | Any photo a stranger uploads can be kept out of public reach by the same mechanism |

### Needs modification

| Thing | Path | Why |
|---|---|---|
| `ContactForm` | `apps/crm/forms.py:62-93` | A staff form: exposes `owner`, `is_active`, `tags`, `status`, `confirm_duplicate`. A public form must be a separate, narrow form rather than this one with fields excluded |
| `ContactCreateView` | `apps/crm/views.py:456-460` | `SalesRoleRequiredMixin` + `PermissionRequiredMixin`; a public view is new code, not a relaxation of this one |
| `Caddyfile` | `Caddyfile:16` | Second site block, second hostname variable (F-CAD-1) |
| `compose.prod.yml` | `:74-87` | A mount for the website's files into the Caddy container |
| `config/settings/production.py` | `:9-17` | If Django serves the form on the apex origin, the apex and `www` must join `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` — which is exactly what collides with `Caddyfile:16` reusing that variable |
| `docs/ADMIN_GUIDE.md` | `:10`, `:282-283` | An Ubuntu x86-64 procedure, including the port sysctl, linger and subuid checks |
| Proxy-config tests | `apps/jobs/tests/test_private_media.py:462-470` | Must supply the new hostname variable, or validation fails (F-CAD-3) |

### Missing entirely

- Any public POST endpoint, and any CSRF-on-public-origin test.
- Rate limiting that works across workers — needs a shared backend
  (a database cache table is the obvious one here; it needs no new
  service, unlike Redis).
- Spam controls (honeypot, minimum submit time, CAPTCHA decision).
- Outbound email of any kind (F-CRM-3).
- In-app user creation and password reset (F-CRM-1, F-CRM-2).
- Backup failure alerting (F-BAK-3).
- Uptime monitoring (nothing watches `/health/` today).
- The website itself: no `website/` directory, no static-site content.

---

## 5. The ten stated facts, checked

| # | Claim | Verdict |
|---|---|---|
| 1 | `Lead` retired; a lead is a `Contact` with `status=lead` and a `lead_source` | **Confirmed.** No `Lead` class in `apps/crm/models.py` (classes at `:16,50,60,141,231,337,389,447,488,526`); `Status.LEAD` at `:65`, `lead_source` at `:88`, `LeadSource.WEBSITE` at `:70` |
| 2 | DRF not installed; a REST API deliberately ruled out without a concrete need | **Confirmed.** `requirements.txt:1-5` is Django, psycopg2-binary, python-dotenv, gunicorn, Pillow; `docs/ROADMAP.md:365` records the deferral |
| 3 | Rootless Podman under a dedicated user's systemd user session, from `~/django-crm` | **Confirmed.** `systemd/crm.service:22-41`, `WorkingDirectory=%h/django-crm` at `:34`; ADR 0005 |
| 4 | Caddy runs inside `compose.prod.yml`; the Caddyfile takes one site address from `{$DJANGO_ALLOWED_HOSTS}`, and its comment says multiple hostnames break | **Confirmed.** `compose.prod.yml:64-87`; `Caddyfile:16` with the comment at `:7-15` |
| 5 | Nothing sets `net.ipv4.ip_unprivileged_port_start`, so rootless Caddy may be unable to bind 80/443 | **Confirmed**, and promoted to the top blocker. Repo-wide grep finds no occurrence |
| 6 | No in-app account creation (admin only) and no password-reset-by-email | **Confirmed.** `apps/users/urls.py:6-21`; no `PasswordReset*` view anywhere outside tests |
| 7 | No outbound email configured | **Confirmed.** No `EMAIL_BACKEND`, `EMAIL_HOST` or `DEFAULT_FROM_EMAIL` in `config/settings/*` |
| 8 | `scripts/restore.sh` has never run end to end | **Confirmed.** `docs/PROJECT_STATE.md` Known issues, unchanged |
| 9 | Pi/ARM64 references are comments plus `scripts/test-arm64.sh`; nothing in the build is ARM-only | **Confirmed.** `Containerfile:30`, `systemd/crm.service:38-39`, `scripts/deploy.sh:8` are comments; `Containerfile:6` has no `--platform` |
| 10 | Django's default cache is per-process locmem, so a naive rate limit would not be shared across three gunicorn workers | **Confirmed.** No `CACHES` setting exists; `Containerfile:35` runs `--workers 3` |

### Where the brief's premises had gone stale

- **"The pending Phase 20 verification."** Phase 20 is **complete and
  closed** — `docs/PROJECT_STATE.md` records it as DONE with its five
  PRs, and Phase 22 closed after it. There is no pending Phase 20
  verification. What *is* pending in that area is narrower and listed
  as F-CRM-4: a payment cannot be corrected in the app.
- **`docs/PRODUCTION_READINESS.md`'s MEDIUM list** still carries four
  `Deal`-related findings (`Deal.company` disagreement, `PROTECT` on
  `Deal.company`/`Deal.contact`). `Deal` was retired in ADR 0012, so
  those are moot rather than open. The HIGH item in that document — a
  possibly-stale `DJANGO_SETTINGS_MODULE` line in the real `.env` — is
  **still live and still only checkable by the owner**, and matters
  more on a VPS: that exact line made a production container boot with
  `DEBUG=True` once before (`.env.example:6-15`).
- **`docs/ADMIN_GUIDE.md`** is accurate but targets the wrong machine
  (F-VPS-6).

---

## 6. Test suite result

Run for this audit, on this workstation, against the project's real
PostgreSQL, at commit `38e9e31`:

```
python manage.py test
Ran 1354 tests in 815.412s
OK
```

**1,354 pass, nothing skipped.** The "nothing skipped" matters: the
proxy-config assertions in
`apps/jobs/tests/test_private_media.py:430-470` are guarded by
`@skipIf(not CADDY)`, and the `caddy` binary **is** installed here
(`/usr/bin/caddy`), so those tests genuinely exercised `caddy adapt`
and `caddy validate` against both Caddyfiles rather than being quietly
skipped. On a machine without Caddy the same green result would mean
less than it appears to — worth knowing before trusting a local run of
this suite as cover for a Caddyfile change.

What the suite does **not** prove, and no suite could: that the stack
starts on a rootless Ubuntu host (F-VPS-1 through F-VPS-5), that a
restore works (F-BAK-1), or that a backup failure would be noticed
(F-BAK-3).

---

## 7. Open questions for the owner

1. **Business email.** The domain has **no MX, SPF, DKIM or DMARC
   records at all** (§8), so no mail is deliverable to
   `@heffronexteriorservices.com` today. Where does business email live
   — a Gmail/Outlook address on another domain? This decides whether
   the DNS cutover has anything to preserve, and whether password
   resets can send from the business's own domain.
2. **The domain is registered *and* DNS-hosted at Wix** (§8).
   Cancelling Wix without first moving the registration or the DNS
   would take the domain's name servers with it. Does the owner want
   the registration transferred to another registrar before anything
   else happens?
3. **VPS provider and region**, so the provisioning steps can name
   real commands and the port sysctl can be verified on the real host.
4. **Who gets accounts in the CRM**, and how they are expected to
   receive their first password — this decides whether in-app user
   creation (F-CRM-1) needs email first (F-CRM-3) or can start with
   the owner setting passwords.
5. **Do photos need to come in from the website at launch?** The
   pipeline exists and is reusable (F-SEC-3); accepting uploads from
   strangers is a different risk posture from accepting them from
   staff.
6. **Is a CAPTCHA acceptable?** It is the one place a third-party
   dependency might be worth it, and it is the owner's call because it
   affects every real customer filling in the form.
7. **RevDek features actually used**, with the data to be exported for
   records before cancellation — needed for the gap analysis the next
   session owns, and the one gate that should block cancelling RevDek.

---

## 8. Appendix — external facts, verified 2026-10-27

Looked up live; recorded because the next session's DNS plan depends on
them and they are not in the repo.

```
Registrar:            Wix.com Ltd.
Created / expires:    2025-01-01 / 2028-01-01
Name servers:         ns6.wixdns.net, ns7.wixdns.net
SOA:                  ns6.wixdns.net. support.wix.com.
A (apex):             185.230.63.171, .186, .107   (Wix)
CNAME www:            cdn3.wixdns.net
MX:                   none
TXT (apex):           none
TXT _dmarc:           none
A crm:                does not exist
```

**Verified** by `whois` and `dig` against the authoritative servers and
again via `1.1.1.1`. Two consequences worth stating plainly: the
registrar and the DNS are both Wix, so **Wix cannot simply be
cancelled** — the registration or at least the DNS has to move first;
and there are **no email records to preserve**, which makes the cutover
simpler and tells us the business's email is not on this domain.

The Wix website's own content was **not** fetched for this audit. Wix
renders pages with JavaScript, so a plain fetch would not produce the
text and images the new site needs; the next session should treat the
copy, photos, reviews, logo and colours as owner-supplied inputs.
