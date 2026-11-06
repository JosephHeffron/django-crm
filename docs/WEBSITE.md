# The public website

The business's public site, replacing Wix. It lives in `website/` in
this repository and is served by the same Caddy as the CRM, on its own
hostnames. Decisions: [ADR 0016](decisions/0016-two-sites-behind-one-caddy.md)
(two sites behind one Caddy) and
[ADR 0017](decisions/0017-the-website-lives-in-this-repository.md)
(the website lives here). Plan: `docs/VPS_DEPLOYMENT_PLAN.md`, Phase 4.

## The one rule

**This repository is public. Everything in `website/` is published the
moment it is committed, and stays in the history after it is deleted.**

Photos show the business's own work, published on purpose. A
customer's name, address, house number, street sign, car plate or face
never goes in this folder, and nor does a screenshot of the CRM. The
tests catch the mechanical part (file types, metadata, size). Only a
person can catch a house number in the corner of a photo.

## What is there

```
website/
  index.html  services.html  gallery.html  about.html  contact.html
  404.html    robots.txt     sitemap.xml
  partials/header.html  partials/footer.html   one copy each, shared by every page
  assets/css/site.css                          the only stylesheet
  assets/js/site.js                            highlights the current page; optional
```

- Pages are plain HTML. Each includes the shared header and footer with
  `{{include "/partials/header.html"}}`, which Caddy fills in when it
  serves the page. That is the **only** `{{ }}` allowed in a page, and
  the partials may contain none at all. A test fails on anything else,
  because Caddy's template engine can also read the server's secrets.
- Links are written as `/services`, never `services.html` and never
  relative. Caddy serves `services.html` for `/services`.
- Colours are the variables at the top of `site.css`. They are neutral
  stand-ins until the real logo and colours arrive.
- No inline `<script>`, `<style>` or `style="…"`. The site's security
  policy blocks them, and a test fails on them.

## What the owner needs to supply

Everything still missing is marked `data-placeholder` in the HTML and
shows on the page as a dashed orange box reading **To supply** or **To
confirm**. To list what is left:

```sh
grep -rn data-placeholder website/
```

**The apex cutover (Phase 22.5 unit 6) waits until that prints
nothing.**

| What | Where it goes | Notes |
|---|---|---|
| Phone number | contact page, and add it to the footer | |
| Hours | contact page | When you answer the phone |
| Service area | contact page, footer | Towns, county or ZIP codes |
| Email to publish | contact page, footer | Currently `heffronexteriorservices@gmail.com`; confirm or replace |
| "Why customers choose us" | home page | Two or three sentences, in your words |
| Service details | services page | One line per service on what is included. The services listed come from the CRM's service catalog; remove any you do not offer publicly |
| About-us story | about page | Who runs it, when and why it started |
| Photos | gallery | Original files, not screenshots. See *Adding a photo* |
| Reviews | home page | Decide how they are credited first; see *Reviews* |
| Logo and colours | `site.css`, header | An SVG logo if you have one, plus a favicon |

All the other wording is a draft written from the service catalog.
Change anything that does not sound like the business.

## Decisions still open

1. **Reviews.** The rule above keeps customers' names out of this
   folder, and a review is normally credited to a name. Options:
   (a) no name, just the town; (b) first name and last initial, only
   for reviews the customer already posted publicly themselves; (c) no
   copied reviews at all, just a link to the Google reviews page.
   Record the choice here before any review is committed.
2. **Apex or `www`.** Canonical URLs, `sitemap.xml` and `robots.txt`
   currently name `https://heffronexteriorservices.com` (the apex). If
   the Wix site has been indexed under `www.`, keeping `www` as the
   main name protects existing search ranking. Check what Google shows
   for the business, then change the one origin used in those files
   (and `SITE_ORIGIN` in `apps/core/tests/test_website.py`).
3. **Old Wix URLs.** After the cutover, any link to a Wix page path
   that no longer exists lands on the new 404 page, which points
   visitors home. Redirects for the important old URLs can be added in
   the Caddyfile once they are known.

## Adding a photo

Phones write the GPS position into every photo they take, and committed
files skip the upload pipeline that strips it for the CRM. Resize the
photo and strip its metadata first. This does what `apps/jobs/photos.py`
does to an uploaded photo: it rotates the image upright, caps the long
edge at 2000 px, and saves a JPEG with no metadata:

```sh
python3 -c '
import sys
from PIL import Image, ImageOps
src, dst = sys.argv[1], sys.argv[2]
with Image.open(src) as image:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((2000, 2000), Image.Resampling.LANCZOS)
    image.save(dst, "JPEG", quality=82, optimize=True, progressive=True)
' ~/Pictures/original.jpg website/assets/img/gutters-before.jpg
```

Then add it to the page with a description in `alt` (a test requires
the attribute):

```html
<img src="/assets/img/gutters-before.jpg" alt="Gutters full of leaves before cleaning" width="1500" height="2000">
```

`make test` (or CI) fails if a file over 1 MiB, a file with metadata,
or a file type that is not a web asset lands in `website/`.

## Previewing it

- **On your own machine, without containers:** the pages need Caddy to
  fill in the header and footer, so opening a file directly shows
  `{{include …}}` as text. Use the dev stack:
  `podman-compose -f compose.dev.yml up -d`, then open
  `https://www.localhost:8443/`. The CRM stays on
  `https://localhost:8443/`. Both use Caddy's local certificate, so the
  browser warns once.
- **On the droplet, before the apex moves:** set `WEBSITE_HOST` to
  `new.heffronexteriorservices.com` in `.env` and add that DNS record
  alongside `crm` (ADR 0016). The preview then has a real certificate.
  Every page's canonical URL points at the apex, so the preview is not
  indexed as the site.

## Deploying a change

The website is bind-mounted from the checkout, so it deploys with the
CRM, through the same `scripts/deploy.sh` and the same rollback. There
is no build step: Caddy reads the files straight from the checkout. A
website-only fast path that skips the CRM's image rebuild is planned
(plan D6.4).

## Before the apex cutover

- `grep -rn data-placeholder website/` prints nothing.
- The decisions above are made.
- `LocalBusiness` structured data is added to the home page, with the
  real name, phone, area and URL. It was deliberately left out until the
  real values exist.
- An Open Graph image (`og:image`) and a favicon exist.
- The preview has been checked on a phone and a laptop.
