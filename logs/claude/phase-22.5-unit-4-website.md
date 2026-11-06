# PHASE 22.5 UNIT 4: THE WEBSITE SCAFFOLD

Started: 2026-11-06
Ended:   2026-11-06 (scaffold; owner content outstanding)

## The thing worth reading

**The plan's design for the website hostnames would have stopped
every nightly backup.** `docs/VPS_DEPLOYMENT_PLAN.md` D7 called for one
Caddy variable, `WEBSITE_HOSTS`, holding the apex and `www` separated
by a space. `scripts/backup.sh` (and `restore_offhost.sh`) read `.env`
with `set -a; . "$REPO_DIR/.env"` under `set -e`. In shell,
`WEBSITE_HOSTS=example.com www.example.com` is not an assignment of two
words. It is a command, `www.example.com`, run with a temporary
variable, and the command does not exist:

```
$ sh -c 'set -eu; set -a; . /tmp/envtest; echo reached end'
sh: 2: /tmp/envtest: www.example.com: not found
exit=127
```

With no backup-failure alerting yet (unit 1, not started), that would
have been a silent stop on the first night after the website went in.
Quoting the value fixes the shell but not compose: whether `env_file`
strips quotes depends on the podman-compose version, and if it does
not, Caddy receives one quoted, invalid address. So the fix is
structural, not quoting: **`WEBSITE_HOST` and an optional
`WEBSITE_WWW_HOST`, one hostname each.** `EnvExampleTests` sources
`.env.example` the way the backup does, and it fails if the line comes
back (mutation 9 below).

The same habit that found it, checking how every consumer reads a file
rather than only the one being changed, is worth keeping. The plan was
written against the Caddyfile and compose. The backup script was the
third reader of `.env`, and nobody had looked at it.

## Objective

Unit 4 of Phase 22.5: the `website/` folder, the second Caddy site
block, the mount, and the guard that keeps private data out of a public
folder, so the owner's content has somewhere to go. Started ahead of
units 1-3 because none of it can reach the domain before unit 6, and
because unit 3's first Caddy start already needs a website hostname
(ADR 0016).

## Files created / changed

Created:
- `docs/decisions/0016-two-sites-behind-one-caddy.md`
- `docs/decisions/0017-the-website-lives-in-this-repository.md`
- `website/{index,services,gallery,about,contact,404}.html`,
  `website/robots.txt`, `website/sitemap.xml`
- `website/partials/{header,footer}.html`
- `website/assets/css/site.css`, `website/assets/js/site.js`
- `apps/core/tests/_caddy.py`: `CADDY`, `CADDY_ENV` and `adapt()`,
  shared so every test that adapts the production Caddyfile passes the
  same variables (audit F-CAD-3)
- `apps/core/tests/test_website.py`: 29 tests
- `docs/WEBSITE.md`: for the owner. What to supply, how to prepare a
  photo, how to preview, and the decisions still open

Changed:
- `Caddyfile`: two site blocks, `(secure_headers)` and
  `(website_headers)` snippets imported per handle block, and the CRM
  block's behaviour unchanged
- `Caddyfile.dev`: the same, with the website on `www.localhost`
- `compose.prod.yml`, `compose.dev.yml`: `./website:/srv/website:ro,Z`
- `.env.example`: `CRM_HOST`, `WEBSITE_HOST`, `#WEBSITE_WWW_HOST`
- `apps/jobs/tests/test_private_media.py`: `caddy validate` and
  `caddy adapt` now get `CRM_HOST`/`WEBSITE_HOST`/`WEBSITE_WWW_HOST`
  instead of `DJANGO_ALLOWED_HOSTS`. Without this, both existing guards
  fail on an empty site address
- `docs/ADMIN_GUIDE.md`, `docs/ARCHITECTURE.md`,
  `docs/VPS_DEPLOYMENT_PLAN.md` (D7 marked as changed when built; `new`
  DNS record added to Phase 3), `docs/ROADMAP.md`,
  `docs/PROJECT_STATE.md`, `CHANGELOG.md`

## What the website block does

```
{$WEBSITE_HOST} {$WEBSITE_WWW_HOST} {
	handle /partials/* { error 404 }                  fragments, not pages
	handle /assets/*   { root; file_server; import website_headers }
	handle             { root; try_files {path} {path}.html;
	                     templates { mime text/html }; file_server; import website_headers }
	handle_errors      { 404 → /404.html, through the same templates }
}
```

No `reverse_proxy`. Unit 5 adds `handle /book/*` and extends
`ALLOWED_PROXY_PATHS` in the test, the only place that allow-list
lives. `website_headers` adds a CSP of `default-src 'self'` (the site
has no inline script or style, and a test keeps it that way), HSTS
without `includeSubDomains`, and a Permissions-Policy. It is imported
per block rather than site-wide, so the Django-rendered `/book/` page
will keep its own CSP (ADR 0007) instead of receiving two.

**A risk found in the design and closed by a test:** Caddy's
`templates` directive has an `env` function, and the Caddy container
receives the whole `.env` through `env_file`. A page containing
`{{env "DJANGO_SECRET_KEY"}}` would publish the key. A page may now
contain exactly one kind of template action, `{{include
"/partials/<name>.html"}}`, and anything else fails
`test_a_page_may_only_include_partials`. Narrowing the Caddy
container's environment to its three hostname variables would be
better still. It is left as a follow-up because it changes how compose
supplies the values, which needs a live `podman-compose` check this
session could not make.

## Commands

$ git clone --depth 1 https://github.com/JosephHeffron/django-crm
Result: PASS. `main` at `55650a3` (#203, 2026-11-04).

$ python3 -c "import django" / which caddy
Result: neither available, and package installs were blocked in this
session. **So the Django suite and every `caddy adapt`/`validate` test
were not run here.** CI runs both, since it installs a pinned,
checksummed Caddy for exactly these tests.

$ sh -c 'set -eu; set -a; . /tmp/envtest; ...'   (WEBSITE_HOSTS=a b)
Result: exit 127, `www.example.com: not found`. This is the finding at
the top.

$ ruff check apps/ && ruff format --check apps/
Result: PASS (196 files). Local ruff is 0.16.9; the repo pins 0.17.3,
and CI's lint step is authoritative.

$ PYTHONPATH=/tmp/djstub:. python3 -m unittest -v apps.core.tests.test_website
Result: 23 passed, 6 skipped (the Caddy class). The stub supplies only
`django.conf.settings.BASE_DIR` and `django.test.SimpleTestCase =
unittest.TestCase`, which is all these tests use. Python 3.13 and
Pillow 12.3 here, against 3.12 and 13.0 in CI.

Mutation run: each line planted one bad input in a copy of `website/`
and `.env.example`, then reran the module. Each was caught by exactly
the intended test:

| # | Planted | Failed |
|---|---|---|
| 1 | `customers.csv` | `test_only_allow_listed_file_types` |
| 2 | JPEG with GPS EXIF in `assets/img/` | `test_no_image_carries_metadata` |
| 3 | `{{env "DJANGO_SECRET_KEY"}}` in a page | `test_a_page_may_only_include_partials` |
| 4 | `{% url %}` in a partial | `test_partials_contain_no_template_syntax` |
| 5 | `/servics` in the footer | `test_internal_links_resolve` (every page) |
| 6 | `style=` attribute | `test_nothing_inline_that_the_csp_would_block` |
| 7 | a page dropped from `sitemap.xml` | `test_the_sitemap_lists_every_page_and_nothing_else` |
| 8 | `/services#gutter` (no such id) | `test_internal_links_resolve` |
| 9 | `WEBSITE_HOSTS=a.com www.a.com` | `test_env_example_sources_as_shell` |
| 10 | relative `href="contact"` | `test_internal_links_resolve` |
| 11 | a 1.1 MB file | `test_no_file_is_over_the_size_cap` |

Rendered in Chrome (headless, Playwright) through a small local server
that does what the website block does: inlines the partials, serves
clean URLs, refuses `/partials/`, serves `404.html` for a miss, and
sends the same CSP. Every page at 390px and 1280px wide: 200 (404 for
the miss), the current page highlighted by `site.js`, no horizontal
overflow, and no console errors apart from the browser's own
`/favicon.ico` request. **No CSP violations.** This found two layout
faults, both fixed: `.wrap.prose` sections sat centred, out of line
with the rest of the page, and the phone header wrapped the quote
button under the business name.

Colour contrast, computed with the WCAG formula: every text/background
pair is AA or better. The lowest is the placeholder label at 4.73:1.

The photo-preparation command in `docs/WEBSITE.md` was run on a
4000×3000 JPEG carrying GPS and an orientation tag. Output: 1500×2000
(rotated), no EXIF, no XMP, 969 KB on a deliberately incompressible
noise image.

## Tests

`apps/core/tests/test_website.py`, 29 tests:
- **Content guard (ADR 0017):** extension allow-list, 1 MiB cap, no
  EXIF/XMP on raster images, no script in SVGs, nothing under `media/`,
  plus two tests that feed the metadata check a GPS-tagged and an
  XMP-tagged JPEG.
- **Templates:** partials free of `{{`, `{%` and `{#`; pages limited to
  includes of partials; includes name real files; header and footer
  exactly once; plus a test that feeds the check a leak, a
  non-partial include and a trim-marker include.
- **Pages:** `lang`, title, description, viewport, one `<h1>`, the one
  stylesheet and one `<main>`; `alt` on every image; nothing inline the
  CSP would block; every internal link and fragment resolves, using
  root-relative URLs only, because unit 5 renders the partials at
  `/book/`; canonical and `og:url` name their own page; the 404 page is
  `noindex`; the sitemap lists exactly the indexable pages; robots.txt
  names the sitemap.
- **Caddy, from `caddy adapt` (skips without the binary; CI has it):**
  website hostnames reach no `reverse_proxy` outside the allow-list;
  the CRM hostname still does; the website serves only
  `/srv/website`; `/partials/*` is refused; `templates` runs on
  `text/html` only; every website file-serving block sets a CSP and
  `nosniff`. Each negative assertion has a positive twin using the same
  walker. If the walker misreads the adapted JSON and finds nothing,
  the twin fails, so the negative cannot pass vacuously.
- **`.env.example`:** sources cleanly as shell under `set -e`, and
  defines `CRM_HOST` and `WEBSITE_HOST`.

**The Caddy class is the least certain code in this change.** The
walkers assume the shape of `caddy adapt` output (host-matched
top-level routes, subroutes per `handle`, `vars` for `root`,
`mime_types` on `templates`, error routes under
`servers.*.errors.routes`). That shape was written from knowledge of
Caddy, not observed in this session. The positive twins mean a wrong
assumption shows up as a red test rather than a false green. Expect
CI's first run to be the real check, and possibly one round of
adjustment.

## Decisions
- ADR 0016: two site blocks, Caddy-only hostname variables, header
  snippets per block, and no proxy from the website hostnames.
- ADR 0017: `website/` in this repository, shared partials, a
  read-only mount, the guard, and the no-customers rule in words.
- One hostname per variable, which departs from the plan's D7, for the
  backup reason above.
- Canonical origin is the apex, `https://heffronexteriorservices.com`.
  **Open for the owner** (`docs/WEBSITE.md`): if Wix is indexed under
  `www`, switch it.
- No `LocalBusiness` structured data until real values exist.
  Invented values are worse than none.
- The services listed are the CRM's seeded catalog
  (`jobs/0002_seed_service_catalog`), without prices. Every sentence of
  copy is a draft.

## Errors
- First desktop render: the `wrap prose` sections sat centred, out of
  line with everything else. `.prose { max-width }` narrowed the
  container itself, and `wrap` centred it. Fixed by limiting
  `.prose > *` instead.
- First phone render: the business name and the quote button did not
  fit on one row at 390px, so the button wrapped onto its own line.
  Fixed with smaller header type and gaps below 48rem.

## Git
Branch: `feature/website-scaffold`
Commit: the single commit on that branch, made after the owner approved
its message on 2026-11-06. No hash here: a commit cannot name itself,
and `git log` answers it properly.

## Lessons learned
- **Check every reader of a file you add a line to.** `.env` has three
  readers: Django, compose and the shell scripts. The plan checked two.
- **A config feature can be a data-exposure path.** `templates` is
  harmless until it meets an environment full of secrets. Note what a
  directive can *read*, not only what it is used for.
- **Rendering found what parsing did not.** Every page test passed
  while two layouts were visibly wrong. The screenshot step is cheap
  enough to keep.

## Next
1. CI on the PR: the first real run of the Caddy tests and the full
   suite. Adjust the adapt walkers if their assumed JSON shape is off.
2. Owner content, tracked by `grep -rn data-placeholder website/`.
3. Plan D6.5 (CI fast path for website-only PRs) and D6.4
   (`deploy.sh --website-only`), each its own PR.
4. Unit 1's remaining items (deployment guide, backup alerting) before
   unit 3. The deployment guide should include the `new` DNS record
   and the three hostname variables.
