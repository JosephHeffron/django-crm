# Production configuration review

Phase 8 unit 2 — a review of the complete assembled production stack
now that Caddy (unit 1) exists: `config/settings/{base,production}.py`,
`Containerfile`, `scripts/entrypoint.sh`, `compose.prod.yml`,
`Caddyfile`, and `.env.example`. Same format as
`docs/DATABASE_REVIEW.md`/`docs/SECURITY_REVIEW.md`/
`docs/USABILITY_REVIEW.md`: findings ranked by severity, checked
empirically, fixed where the fix is safe and contained, deferred (with
reasoning) where it isn't.

## Method

- `manage.py check --deploy` re-run fresh against
  `config.settings.production` with a realistic, properly random
  throwaway `DJANGO_SECRET_KEY` (an intentionally short one first, to
  confirm the checker actually flags that — then a real one, to isolate
  genuine findings from an artifact of a deliberately weak test key).
- Read every file in scope end to end: `config/settings/base.py`,
  `config/settings/production.py`, `config/settings/development.py`,
  `config/wsgi.py`/`config/asgi.py`, `manage.py`, `Containerfile`,
  `scripts/entrypoint.sh`, `.containerignore`, `compose.prod.yml`,
  `Caddyfile`, `.env.example`.
- Traced how each environment variable actually reaches each container
  at runtime (image `ENV` vs. compose `env_file:` vs. compose
  `environment:` vs. `manage.py`/`wsgi.py`'s own `setdefault` fallback),
  rather than assuming the documented intent matches the actual
  precedence — this is what surfaced this unit's one HIGH finding.
- Live `podman run` checks against the actual built production image
  (`localhost/django-crm:latest`), reading back real settings values
  (`DEBUG`, `SECURE_SSL_REDIRECT`) from inside a running Python process,
  not inferred from reading the settings files alone.
- Re-confirmed (rather than re-assumed) findings already empirically
  verified during Phase 8 unit 1's own live testing — `X-Forwarded-
  Proto` recognition and Caddy→Django Host-header forwarding against
  `ALLOWED_HOSTS` — cited here rather than re-run, since nothing in
  this unit changed either mechanism.
- Checked for any inline `<script>`/`<style>` or external resource
  references across `templates/` and `static/` to assess whether a
  Content-Security-Policy header could be added safely.

## HIGH

### 1. `.env.example`'s `DJANGO_SETTINGS_MODULE` line silently downgraded production to `DEBUG=True`

`.env.example` set `DJANGO_SETTINGS_MODULE=config.settings.development`
unconditionally — correct for native dev, but both `compose.prod.yml`
and `compose.dev.yml`'s `web` service load `.env` via `env_file:`, and
an env var from `env_file:` overrides the image's own baked-in `ENV`
(confirmed live: `podman run --env-file` with this var set wins over
the `Containerfile`'s `ENV DJANGO_SETTINGS_MODULE=config.settings.
production`). A real deployer following the documented "copy
`.env.example` to `.env`, fill in real values" procedure has no reason
to touch this line — it carries no `change-me` placeholder, unlike
`DJANGO_SECRET_KEY`/`POSTGRES_PASSWORD` — so it would very plausibly
survive into a real `.env` untouched.

**Confirmed live, not just reasoned through**: ran the actual built
production image with an env file matching `.env.example` verbatim
(placeholders filled, this line untouched) — the container loaded
`config.settings.development`, with `DEBUG=True` and
`SECURE_SSL_REDIRECT=False`. A real deployment in this state would be
DEBUG-mode-reachable at a real public domain through Caddy: full
tracebacks with source and local variables on any unhandled exception,
none of `production.py`'s hardening (HSTS, secure cookies, SSL
redirect) in effect, and `ALLOWED_HOSTS` restricted to
`localhost`/`127.0.0.1` (`development.py`'s value) rather than the real
domain — which would most likely present as every real request getting
Django's own `DisallowedHost` debug page, itself an information
disclosure.

This gap wasn't caught by Phase 7/8 unit 1's own live verification
because that verification used a hand-written throwaway env file that
already had `DJANGO_SETTINGS_MODULE=config.settings.production` set
correctly — it never exercised the actual documented "copy
`.env.example`" procedure a real deployer would follow.

**Status: FIXED.** Removed the line from `.env.example` entirely,
replaced with a comment explaining why. `manage.py`/`wsgi.py`/`asgi.py`
already `os.environ.setdefault("DJANGO_SETTINGS_MODULE",
"config.settings.development")` — correct for native dev on its own,
with nothing in `.env` to override it. The `Containerfile`'s `ENV
DJANGO_SETTINGS_MODULE=config.settings.production` is now no longer
overridden by `env_file: .env`, since `.env` no longer mentions the
var at all. Re-verified live against the actual fixed file (copied
`.env.example` verbatim, placeholders filled, same as a real deployer
would do): the production image now correctly loads
`config.settings.production`, `DEBUG=False`,
`SECURE_SSL_REDIRECT=True`.

**Action item — not something this review can do**: this project's
policy is to never read or touch the real, already-existing local
`.env` file. If it was created before this fix (i.e., copied from an
earlier version of `.env.example`), it may still contain the old
`DJANGO_SETTINGS_MODULE=config.settings.development` line. Worth
checking by hand and removing it if present — otherwise this exact
issue would resurface the moment that real `.env` is used with
`compose.prod.yml`.

## MEDIUM

### 2. No Content-Security-Policy header

Still not set anywhere — `docs/SECURITY_REVIEW.md` (Phase 6) deferred
this with the reasoning that Caddy (Phase 8) would be the natural place
for it. Caddy now exists, and the app is a genuinely easy CSP target:
no `.js` files anywhere in `static/` or `templates/`, no external
resource references (`grep`-confirmed), and no inline `<script>`
anywhere in this project's own templates. The one wrinkle is Django's
**built-in admin** (`/admin/`, actively used — `apps/crm/admin.py`
registers all six models with standard `ModelAdmin`, no custom JS): its
templates include inline `<script>` blocks (e.g. a JSON-data script tag
in the base admin template) whose interaction with a strict
`script-src` CSP (with or without `'unsafe-inline'`) can only be
reliably confirmed by watching a real browser's console for CSP
violations — something this review's available tooling (`curl`,
HTTP-status-only checks) cannot do. `curl` can confirm a page returns
`200`, but not whether the browser silently blocked an inline script
and broke a widget (a date picker, a related-object popup) with no
HTTP-visible symptom.

**Status: still deferred**, not fixed — same conclusion as
`docs/SECURITY_REVIEW.md`, updated reasoning: the blocker is no longer
"which layer should own this" (Caddy, clearly, now that it exists) but
"this needs verification in an actual browser against the admin
interface specifically," which isn't something this review can
honestly claim to have done with the tools available in this
environment. Revisit when a real browser check is possible, rather
than shipping a CSP based on an assumption about Django admin's inline
script tags.

### 3. Caddy's container runs as root (the official image's default)

`podman run --entrypoint sh caddy:2.11.4-alpine -c whoami` → `root`.
Caddy's official image ships no non-root variant. Binding host ports
80/443 is part of why (low ports traditionally require root inside a
rootful runtime) — though this project's actual deployment is rootless
Podman throughout, where the container's "root" is already mapped to
an unprivileged host UID via user namespaces, meaningfully narrowing
the real-world blast radius of running as root *inside* the container
compared to a rootful setup.

**Status: not fixed, documented as an accepted trade-off** — building
a custom non-root Caddy image just to drop this would be new
infrastructure complexity (a maintained custom image, kept in sync
with upstream Caddy releases) for a risk already substantially reduced
by the rootless Podman deployment model this project already commits
to. Revisit only if a concrete requirement (e.g., a hardening
checklist mandating non-root for every container regardless of runtime
isolation) demonstrates this specific mitigation is actually needed.

## LOW

### 4. `SECURE_HSTS_PRELOAD = True` is a long-term commitment, not yet acted on

Setting the header is not the same as being on the browser preload
list — that requires a manual, largely irreversible submission at
`hstspreload.org` once a real domain is live. Not a bug: the header is
correctly configured per Django/Google's own guidance for a site that
intends to go that route eventually. **Informational only** — worth
the eventual deployer knowing this is a deliberate one-way door before
submitting, not something to action now with no real domain yet.

### 5. No documented plan for Let's Encrypt's rate limits during initial deployment

`Caddyfile` uses real automatic HTTPS with no staging/test CA
configured. Let's Encrypt's production CA has weekly-per-domain rate
limits that repeated failed attempts (DNS not yet propagated, a
config typo) can exhaust, causing real certificate requests to be
locked out for the remainder of that window. **Deferred, not fixed**:
this is an operational/runbook concern for the actual first deployment
(Phase 9/10), not a config defect today — worth a one-line note in
whatever deployment runbook Phase 10 or 14 produces (Caddy supports an
`acme_ca` staging endpoint override for exactly this purpose), not a
change to `Caddyfile` itself right now.

## Checked and confirmed solid (not just assumed)

- `manage.py check --deploy` against `config.settings.production`,
  re-run fresh with a realistic random `DJANGO_SECRET_KEY`, reports
  **zero issues** — unchanged from Phase 6, confirms Phase 7/8's
  additions introduced no regression here.
- `DEBUG = False` is hardcoded in `production.py` itself, not read from
  an environment variable — the HIGH finding above was about which
  *settings module* loads, not about `DEBUG` being flippable by a bad
  env value within `production.py` alone; that part was never at risk.
- Caddy's `X-Forwarded-Proto` is correctly recognized by Django's
  `SECURE_PROXY_SSL_HEADER` — verified live during Phase 8 unit 1 (see
  `logs/claude/phase-08-caddy-https.md`), not re-run here since nothing
  in this unit touched either side of that mechanism.
- Caddy's default Host-header forwarding correctly reaches Django's
  `ALLOWED_HOSTS` check — implicitly proven by unit 1's successful
  `302` responses through the proxy (a mismatch would have produced
  Django's `DisallowedHost` `400`, not a clean login redirect).
- No secrets are ever baked into the image — `.containerignore`
  excludes both `.env` and `.env.example` from the build context; the
  only way secrets reach the `web`/`caddy` containers is via
  `env_file: .env` at container-start time.
- `web` runs as a non-root user (uid 1000) — re-confirmed present in
  `Containerfile` (`useradd --uid 1000 django` / `USER django`),
  originally verified live via `podman exec ... whoami` in Phase 7.
- Caddy's admin API (port 2019, unauthenticated by default) is **not**
  published to the host in either compose file — only 80/443
  (production) / 8080/8443 (dev) are, confirmed against both files'
  `ports:` blocks and the running containers' actual port mappings
  during unit 1's live verification.
- Named volumes (`postgres_data`, `static_files`, `media_files`,
  `caddy_data`, `caddy_config`) give each piece of persistent state its
  own correctly-scoped storage — no bind mounts of writable
  application data into the containers, only the read-only `Caddyfile`
  and read-only `static_files`/`media_files` mounts into `caddy`.
- `entrypoint.sh` runs `migrate`/`collectstatic` on every container
  start, with `set -e` (a failed migration stops the container rather
  than starting gunicorn against a half-migrated database) — safe for
  this project's single-`web`-replica deployment model; idempotent on
  a restart where no new migrations exist.

## Recommendation

One real HIGH finding, found and fixed in this unit: `.env.example`'s
`DJANGO_SETTINGS_MODULE` line could have silently put a real production
deployment into `DEBUG=True` — confirmed live against the actual built
image, both broken and then fixed. Two MEDIUM items remain genuinely
deferred with reasoning (CSP needs a real-browser check this
environment can't perform; Caddy-as-root is a documented, substantially
mitigated trade-off, not a silent gap). Two LOW items are purely
informational for a future real deployment. Everything else in the
assembled stack — proxy header trust, Host-header/ALLOWED_HOSTS
matching, secret handling, non-root Django, admin-API exposure, volume
scoping — was checked directly (not assumed) and confirmed solid.
