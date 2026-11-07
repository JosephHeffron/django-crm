# 0017 — The website lives in this repository

*(Number reserved for this decision by `docs/VPS_DEPLOYMENT_PLAN.md`'s
ADR table; the recommendation is its D6.)*

## Context

Heffron Exterior Services is replacing its Wix site. The new site is a
handful of static pages: home, services, about, gallery and contact.
Unit 5 adds one dynamic page, `/book/`, which Django renders and which
has to look like the rest of the site.

**This repository is public.** Anything committed to it is published,
and stays in the history after a later deletion.

## Alternatives considered

- **A second repository.** Separate history and separate permissions,
  but also two deploy paths, two backups, and no way for `/book/` to
  share the header, footer and stylesheet without keeping a copy that
  drifts.
- **A static-site generator** (Hugo, Eleventy, Jekyll). Layouts and
  includes are what it offers, but it adds a build step and a toolchain
  on the workstation, in CI and in the deploy path, for six pages.
  Caddy's built-in `templates` directive does the one thing needed,
  including a shared header and footer, with no build at all.
- **A CMS** (WordPress or similar). A database, a language runtime, a
  plugin ecosystem and a steady stream of security updates, to edit
  copy that changes a few times a year.

## Decision

**A top-level `website/` folder of hand-written HTML, CSS and minimal
JavaScript.**

- **Layout:** pages at the top of `website/`; `partials/header.html`
  and `partials/footer.html` hold the only copy of each;
  `assets/css/site.css` is the only stylesheet; `assets/js/site.js` is
  optional and progressive; images go in `assets/img/`.
- **Shared partials, one copy.** The static pages include them through
  Caddy's `templates` (`{{include "/partials/header.html"}}`). In
  unit 5, Django adds `website/` to `TEMPLATES["DIRS"]` and includes
  the same files. The partials contain **no template syntax of either
  flavour**, so each engine sees plain HTML. A test enforces this.
- **Mounted read-only into Caddy**, in `compose.prod.yml` *and*
  `compose.dev.yml` (`./website:/srv/website:ro,Z`), so a dev stack can
  serve the site for review and the proxy tests check real configs.
- **Deployed like code.** `scripts/deploy.sh` checks out a ref, and the
  bind mount makes the content live immediately. The plan's
  `--website-only` fast path (D6.4) is a later optimisation, not a
  prerequisite.
- **A guard test, `apps/core/tests/test_website.py`, runs in the normal
  suite on every PR.** It fails on:
  1. any file whose extension is not on a short allow-list (`.html
     .css .js .svg .png .jpg .jpeg .webp .woff2 .ico .txt .xml
     .webmanifest`), which stops a `.csv` of customers, a `.pdf`
     invoice, an `.sql` dump or a stray `.env`;
  2. any file over 1 MiB;
  3. any raster image carrying EXIF or XMP metadata. A photo taken at a
     customer's house carries the address in its GPS tags, and
     committed files bypass the upload pipeline that strips them
     (ADR 0009, `apps/jobs/photos.py`);
  4. any SVG containing a `<script>` element or an inline event handler;
  5. any template syntax in a partial, and any template action in a
     page other than an `include` of an existing partial (ADR 0016
     explains why: `templates` can read Caddy's environment);
  6. any internal link or asset reference that does not resolve to a
     file in `website/`;
  7. a page missing a title, a meta description, a `lang`, exactly one
     `<h1>`, the shared header and footer, or `alt` text on an image.

**The rule a test cannot express, stated here so it is on record:**
photos in `website/` show *the business's own work*, published on
purpose. A customer's name, address, or anything else that identifies
them never goes in this folder. The gallery shows work, not clients,
and screenshots of the CRM never go in it.

## Reason

One repository means one deploy, one history, one backup and one CI
gate, and the booking page can share the site's look without a second
copy. The alternatives each add something to run, update or keep in
sync, and none solves a problem this site has.

## Consequences

- **A copy change is a pull request.** That is slower than a CMS, and
  arguably correct for a public site: it is reviewed, it is in the
  history, and it can be reverted.
- **Website-only PRs run the full suite** until the CI fast path from
  the plan's D6.5 lands. That costs time, not correctness, because the
  guard is part of the suite either way. The fast path must keep the
  required check names reporting, and must not short-circuit when
  `website/partials/**` changes, since Django will read those files.
- **The guard catches mechanics, not judgement.** A correctly stripped
  photo of a customer's house with the house number visible passes
  every test. The rule above, and review, are what catch that.
- **Reviews collide with the rule.** A review is credited to a
  customer, but the rule keeps customers' names out of this folder. How
  reviews are credited is the owner's decision, recorded in
  `docs/WEBSITE.md` before any review is committed. The rule stands
  until then.
- **Placeholder content is marked with `data-placeholder`** and outlined
  on the page, so it cannot go unnoticed on the preview hostname.
  `docs/WEBSITE.md` lists what the owner needs to supply, and the
  apex cutover (unit 6) waits until `grep -rn data-placeholder website/`
  returns nothing.
- Business structured data (`LocalBusiness` JSON-LD) waits for the real
  address and phone number. Publishing invented values is worse than
  publishing none.

## Date

2026-11-06
