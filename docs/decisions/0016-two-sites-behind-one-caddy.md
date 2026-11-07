# 0016 — Two sites behind one Caddy

> **Amended 2026-11-06 by
> [ADR 0022](0022-caddy-on-the-host-network-for-real-client-addresses.md):**
> production Caddy now runs on the host network and proxies to
> `127.0.0.1:8000` instead of `web:8000`, so that it sees real visitor
> addresses. The site blocks and everything below are unchanged.

*(Number reserved for this decision by `docs/VPS_DEPLOYMENT_PLAN.md`'s
ADR table; the recommendation is its D7.)*

## Context

Phase 22.5 puts the CRM and the business's public website on one
x86-64 droplet (ADR 0015): the CRM on `crm.heffronexteriorservices.com`,
the website on the apex and `www`.

The production `Caddyfile` has one site block, addressed by
`{$DJANGO_ALLOWED_HOSTS}`, and its own comment said a second hostname
would need its own variable (`docs/VPS_AUDIT.md` F-CAD-1). Two facts
constrain the answer:

- **Only one process can own ports 80 and 443.** Whatever serves the
  website has to sit behind the same Caddy that terminates TLS for the
  CRM.
- **Headers are scoped per block for a reason.** Django's
  `SecurityMiddleware` and its CSP (ADR 0007) set headers on every
  proxied response. A site-wide `header` block in Caddy duplicated them
  — found by live testing in Phase 8 — so Caddy sets headers only on
  the responses it produces itself.

## Alternatives considered

- **Keep one variable and list every hostname in it.** Caddy would then
  serve the CRM on the apex as well — the opposite of what is wanted.
- **A second web server container for the website** (nginx, or a
  second Caddy). It cannot bind 443 alongside the first, so it ends up
  behind Caddy anyway, as one more image to patch.
- **Serve the website from Django.** Every public page view would take
  one of gunicorn's three workers, and a typo fix would need an image
  rebuild. Django is for the one page that needs it (`/book/`, unit 5).
- **A free static host** (GitHub Pages, Netlify, Cloudflare Pages).
  Cheap and fast, but the booking form would then post across origins,
  which needs an API, CORS and CSRF changes that the plan's D1 chose to
  avoid. It would also mean a second place to deploy and a second DNS
  arrangement.

## Decision

**Two site blocks in one Caddyfile, with Caddy-only hostname
variables.**

- `{$CRM_HOST}` addresses the CRM block, which is unchanged in
  behaviour: `/static/*`, `/media/private/*` refused, `/media/*`, then
  everything else to Django (`web:8000` when this was written;
  `127.0.0.1:8000` since ADR 0022).
- `{$WEBSITE_HOST} {$WEBSITE_WWW_HOST}` addresses the website block,
  with **one hostname per variable**. The plan had proposed a single
  space-separated `WEBSITE_HOSTS`. That breaks backups:
  `scripts/backup.sh` and `scripts/restore_offhost.sh` source `.env` as
  shell under `set -e`, and an unquoted `WEBSITE_HOSTS=a b` line runs
  `b` as a command. The backup then stops with exit 127 before it does
  anything. This was reproduced while writing this ADR, not inferred.
  Quoting the value would fix the shell but not compose: whether
  `env_file` strips the quotes depends on the podman-compose version,
  and if they are kept, Caddy receives one quoted, invalid address. Two
  variables with one name each avoid both problems.
  `WEBSITE_WWW_HOST` is optional, because Caddy substitutes `{$…}`
  before parsing and an empty value is simply no address.
- `DJANGO_ALLOWED_HOSTS` keeps its Django meaning only. Unit 5 adds the
  website hostnames to it when `/book/` starts reaching Django.
- **The two header sets are snippets**: `(secure_headers)` holds the
  three headers the CRM's file-serving blocks already set, and
  `(website_headers)` adds a Content-Security-Policy, HSTS and a
  Permissions-Policy for the website. Each `handle` block that serves a
  file imports one of them, so no proxied response is touched.
- **The website block contains no `reverse_proxy`.** Until unit 5, the
  public hostnames cannot reach any part of the CRM. A `caddy adapt`
  test asserts this, with an allow-list that unit 5 extends to exactly
  `/book/*`.
- The website block serves files from `/srv/website` (ADR 0017's
  mount). The `templates` directive is limited to `text/html`, so the
  pages can include the shared header and footer. `/partials/*` is
  refused because partials are fragments, not pages. Clean URLs come
  from `try_files {path} {path}.html`, and missing pages get the
  website's own `404.html` through `handle_errors`.
- **Website images live under `/assets/`, never `/media/`.** The
  private-media guard
  (`apps/jobs/tests/test_private_media.py`) checks every `/media/*`
  file server across every site block, and should keep doing so.
- Development: `Caddyfile.dev` serves the website on `www.localhost`
  (`tls internal`, the same 8443 port), alongside the CRM on
  `localhost`.

## Reason

One TLS terminator, one certificate store and one config file the
tests can adapt and inspect cover both sites. The CRM block's
behaviour is unchanged, which the existing private-media and header
tests continue to prove. The only new attack surface is a static file
server, and a test guarantees it reaches nothing else.

## Consequences

- **`CRM_HOST` and `WEBSITE_HOST` are required and have no default.**
  Per Caddy's documentation, an empty variable expands to no tokens at
  all. That leaves a block with no address, which Caddy either reads as
  global options or rejects, and both stop it from starting. So a
  missing value should stop Caddy rather than serve something
  unexpected. *This comes from the documentation and has not yet been
  observed on the droplet; confirm it in unit 3.*
- **Unit 3 needs a website hostname before the website is launched.**
  Set `WEBSITE_HOST` to the preview name
  `new.heffronexteriorservices.com`, leave `WEBSITE_WWW_HOST` unset,
  and add the `new` DNS record at the same time as `crm`. Both are
  subdomain records, so the apex stays untouched. Without that record,
  Caddy keeps retrying a certificate it cannot obtain. At the apex
  cutover (unit 6), `WEBSITE_HOST` becomes the apex and
  `WEBSITE_WWW_HOST` the `www` name.
- **A test sources `.env.example` the way `scripts/backup.sh` sources
  `.env`**, so a future example value with a space in it fails CI
  instead of failing the nightly backup.
- **The `templates` directive can read environment variables** (its
  `env` function), and the Caddy container receives the whole `.env`
  through `env_file`. Without a guard, a page containing
  `{{env "DJANGO_SECRET_KEY"}}` would publish the key. The website test
  suite therefore allows exactly one template action in a page, an
  `include` of a file under `/partials/`, and fails on anything else.
  Narrowing the Caddy container's environment to the two hostname
  variables would be better still. It is recorded as a follow-up
  rather than done here, because it changes how compose supplies the
  values and needs a live check this change could not make.
- **HSTS on the website hosts omits `includeSubDomains`.** The apex must
  not commit every future subdomain to HTTPS on the website's behalf.
  `crm.` already sends its own HSTS header from Django.
- `apps/jobs/tests/test_private_media.py` passes `CRM_HOST`,
  `WEBSITE_HOST` and `WEBSITE_WWW_HOST` when it runs `caddy validate`
  and `caddy adapt`, as
  audit F-CAD-3 required, so a missing variable no longer turns the
  private-media guard red for an unrelated reason.

## Date

2026-11-06
