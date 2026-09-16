# PHASE 08: CADDY AND HTTPS (UNIT 1)

Started: 2026-09-16
Ended: 2026-09-16

## Objective

First of two Phase 8 units, per the roadmap: the Caddy container itself
— reverse proxy, HTTPS termination, static/media file serving, security
headers — matching `docs/ARCHITECTURE.md`'s "Container architecture"
section (Caddy is the only container reachable from outside the host;
Django never terminates HTTPS directly). Unit 2 will be a formal
production configuration review of the complete assembled stack.

## Files created / changed

- `Caddyfile` — new (root level, alongside the existing root-level
  `Containerfile`/`compose.*.yml`, not the nested `containers/`/
  `compose/` layout `docs/ARCHITECTURE.md` originally sketched — kept
  consistent with Phase 7's already-merged root-level placement rather
  than reorganizing). Production Caddyfile: `{$DJANGO_ALLOWED_HOSTS}`
  as the site address (reuses Django's own env var for the same piece
  of information — real automatic HTTPS via Let's Encrypt, no `tls
  internal`), `handle_path` + `file_server` for `/static/*` and
  `/media/*` (bypasses Django/gunicorn entirely), `reverse_proxy
  web:8000` for everything else, security headers scoped to just the
  two file-serving blocks (see Decisions).
- `Caddyfile.dev` — new. Same structure, `localhost` + `tls internal`
  (Caddy's own local CA) instead of real ACME, since there's no public
  domain to test against locally.
- `compose.prod.yml` / `compose.dev.yml` — added the `caddy` service
  (image `caddy:2.11.4-alpine`, confirmed via `skopeo inspect --raw`
  to support `linux/arm64/v8` for the eventual Raspberry Pi 5 target)
  to both, wired to `web` via `depends_on: condition: service_healthy`
  and to the existing `static_files`/`media_files` named volumes
  (read-only). New `caddy_data`/`caddy_config` volumes for Caddy's own
  certificate/state storage. `compose.dev.yml`'s `web` no longer
  publishes a host port — Caddy is now the intended entry point, same
  as production; requests reach it through the real path being tested,
  not a shortcut around it.

## Commands

$ `podman-compose -f <file> config` — schema-validated both compose
  files before any real `up`, per the lesson from Phase 7 unit 2. Both
  passed cleanly.

$ Full live verification of the 3-container stack (`db`+`web`+`caddy`)
  against a throwaway `.env.compose-verify` (never the real local
  `.env`) and a throwaway copy of `compose.dev.yml` pointed at it:
  - First `up` attempt: **`db` failed to start** — `bind: address
    already in use` on host port 5432. Root cause: this project's own
    native day-to-day dev workflow keeps a locally-installed
    PostgreSQL running on 5432 at all times (`systemctl status
    postgresql` confirmed it active). `compose.dev.yml`'s `db` port
    publish collided with it. Fixed by remapping to `5433:5432` in
    `compose.dev.yml`, with a comment explaining why.
  - Second attempt: `db`/`web` came up healthy, but **`caddy` crash-
    looped** — `open /etc/caddy/Caddyfile: permission denied` in its
    own logs. Root cause confirmed via `getenforce` (Enforcing) and
    `ls -laZ` on the host file (labeled `user_home_t`, not a
    container-accessible label) — the classic rootless-Podman +
    Fedora-SELinux bind-mount denial. Fixed by adding the `:Z` mount
    option to the Caddyfile bind mount in both compose files.
  - Third attempt: all three containers came up `healthy`/running,
    Caddy's logs showed a clean `tls internal` certificate obtained
    for `localhost`.
  - `curl -sI http://localhost:8080/` → `308` redirect to
    `https://localhost/` — HTTP→HTTPS redirect confirmed.
  - `curl -sk -I https://localhost:8443/` → `302` to
    `/accounts/login/?next=/` (a relative path — `redirect_to_login`'s
    signature, not `SecurityMiddleware`'s absolute-URL SSL redirect),
    with `server: gunicorn`, `via: 1.1 Caddy`, and critically
    **`strict-transport-security` present** — `SecurityMiddleware`
    only sets HSTS when it considers the request already secure. This
    is the direct, empirical confirmation that Caddy's `reverse_proxy`
    sets `X-Forwarded-Proto` correctly and that
    `config/settings/production.py`'s `SECURE_PROXY_SSL_HEADER`
    recognizes it — not assumed from Caddy's own documentation.
  - First pass at this same request showed every security header
    (`x-content-type-options`, `x-frame-options`, `referrer-policy`)
    **duplicated** — Caddy's site-wide `header` block was adding them
    on top of the ones Django's own `SecurityMiddleware` already sets
    (confirmed via `grep` on `config/settings/production.py`:
    `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS`, plus Django's
    default `SECURE_REFERRER_POLICY`). Fixed by moving the `header`
    block inside just the two `handle_path` blocks; re-verified —
    each header now appears exactly once on the proxied response.
  - `curl -sk -I https://localhost:8443/static/css/base.css` → `200`,
    `server: Caddy` (not proxied to gunicorn), all three security
    headers present exactly once — static file serving confirmed,
    bypassing Django entirely as designed, with headers still applied.
  - `curl -sk -I https://localhost:8443/media/nonexistent.jpg` → clean
    `404` (no media files exist yet in the app) — confirms the
    `file_server` block itself is structurally sound.
  - All throwaway containers, the built test image
    (`django-crm_web:latest`), named test volumes (`*_dev`), and the
    throwaway `.env.compose-verify`/compose-copy files were cleaned up
    afterward.

$ `manage.py check` / `ruff check .` / `ruff format --check .` /
  `pip-audit`
Result: PASS.

$ `bandit -r apps config -q` (scoped correctly — an initial `bandit -r
  .` accidentally scanned `.venv` too and produced misleading noise;
  re-ran matching this project's established scoping)
Result: pre-existing `B106` low-severity findings only, all in test
fixtures (`password="correct-horse-battery"` etc.) — unrelated to this
unit, not a regression.

$ `python manage.py test` (full suite)
Result: PASS — 296 tests (unchanged — infra work adds no Django test
cases; the live 3-container verification above is this unit's real
test).

## Tests

`python manage.py test` — 296 passed, 0 failures.

## Decisions

- Kept `Caddyfile`/`Caddyfile.dev` at repo root, matching Phase 7's
  already-merged root-level `Containerfile`/`compose.*.yml` placement,
  rather than the nested `containers/`/`compose/` layout
  `docs/ARCHITECTURE.md` originally sketched. Not reorganizing already-
  merged files for a doc-only inconsistency; `docs/ARCHITECTURE.md`'s
  example layout should be updated separately to reflect this (not yet
  done — flagged for a future small doc-only change).
- Security headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) are set by Caddy only for the two `handle_path`
  (static/media) blocks, not site-wide — Django's own
  `SecurityMiddleware` already sets the equivalent headers on every
  response it generates, so a site-wide Caddy header block would only
  duplicate them on the proxied path. Confirmed by live testing (see
  Commands), not assumed.
- `{$DJANGO_ALLOWED_HOSTS}` reused directly as Caddy's production site
  address rather than introducing a second env var — but this only
  works for a single hostname (Django's `ALLOWED_HOSTS` accepts a
  comma-separated list; a Caddyfile site address block expects space-
  separated addresses). Documented as a known limitation directly in
  `Caddyfile`; fine for this project's actual plan (one Pi, one
  domain, per `.env.example`), would need its own variable if that
  ever changes. Not empirically tested against a real multi-host value
  — reasoned through from Caddyfile syntax, not verified live, since
  the actual deployment plan doesn't call for it.
- `compose.dev.yml`'s `db` now publishes `5433:5432`, not `5432:5432`
  — this project's native dev workflow keeps a real local PostgreSQL on
  5432 at all times, and the compose dev stack needs to coexist with
  it, not replace it.
- Both compose files' Caddyfile bind mount uses the `:Z` SELinux label
  option — required for Fedora's enforcing SELinux to let the
  container read a host-mounted file at all; Podman's own named
  volumes don't need this since Podman labels those itself.

## Errors

Three real, substantive things found and fixed during this unit's own
live verification — not from an automated review (repo is private, so
Sourcery doesn't review it; this unit's live verification served the
same purpose):

1. **Host port 5432 collision** between `compose.dev.yml`'s `db`
   service and this project's own native, always-running local
   PostgreSQL. Caught by the container's own `bind: address already in
   use` error on the first real `up`, not guessed in advance.
2. **SELinux denial on the Caddyfile bind mount** — Fedora's enforcing
   SELinux blocked the container from reading `./Caddyfile.dev` because
   the host file carried an ordinary `user_home_t` label, not a
   container-accessible one. Caught from Caddy's own crash-loop logs
   (`permission denied`), confirmed via `getenforce`/`ls -laZ`, fixed
   with the standard `:Z` mount option.
3. **Duplicate security headers on the proxied path** — a site-wide
   Caddy `header` block duplicated headers Django's own
   `SecurityMiddleware` already sets, caught by actually inspecting the
   real response headers with `curl -I`, not by reading the Caddyfile
   and assuming it was fine.

## Lessons learned

- A dev machine's own pre-existing services (this project's native
  local PostgreSQL) are a real constraint on any compose stack meant
  to run alongside them, not just inside CI/production — worth
  checking `ss -ltnp`/`systemctl status` for port conflicts before
  assuming a compose file's port publishes are safe.
- Rootless Podman on Fedora needs `:z`/`:Z` on host bind mounts touched
  by SELinux-confined containers; Podman-managed named volumes don't
  need this. A "permission denied" reading a file that plain `ls -l`
  shows as readable is a strong signal to check `getenforce`/`-Z`
  output before assuming a UID/ownership problem.
- A reverse proxy's own security-header directives can silently
  duplicate headers the backend application middleware already sets —
  worth actually inspecting live response headers (`curl -I`), not
  just trusting that "Caddy sets X" and "Django sets X" are mutually
  exclusive facts from reading each tool's config in isolation.
- `bandit -r .` without the established `apps config` scoping picks up
  `.venv` and produces a wall of misleading noise — worth checking how
  a tool was invoked in a prior phase log before assuming a new command
  form is equivalent.

## Git

Branch: `feature/caddy-https-phase8`
Commit: `c4d7e91` (first committed accidentally directly to `main` —
caught immediately, fixed locally before any push: created the feature
branch at that commit, then reset local `main` back to
`origin/main` — a genuine Git Policy near-miss, not a real violation of
the remote, since nothing had been pushed yet)
Merged to `main`: `de93aec` (regular merge commit, PR #54 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live verification already served as the equivalent scrutiny)

## Next

Phase 8 unit 2 — a formal production configuration review of the
complete assembled stack (Django settings, `Containerfile`,
`compose.prod.yml`, `Caddyfile`), following the established
`docs/DATABASE_REVIEW.md`/`docs/USABILITY_REVIEW.md`/
`docs/SECURITY_REVIEW.md`/dependency-audit format. Phase 8 is not yet
complete — `docs/ROADMAP.md` stays unchecked until unit 2 also merges.
