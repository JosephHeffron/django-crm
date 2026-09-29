# PHASE 17 UNIT 1: DESIGN SYSTEM, APP SHELL, ROLES, PWA BASELINE

Started: 2026-09-28
Ended: 2026-09-29

## Objective

First of three units of Phase 17 ("Field-service foundation"), from the
plan the user approved on 2026-09-28 pivoting the CRM to their exterior
home-services company (`/home/BlueEyes/.claude/plans/gentle-hatching-wilkinson.md`).
This unit: record the architecture decisions first (per `CLAUDE.md`),
then a mobile-first app shell on a real design system, Owner / Sales
Rep / Cleaner roles enforced server-side, and an installable PWA
baseline. Units 2 (data model + seed) and 3 (all pages) follow.

## Files created / changed

- **Decisions / docs (written before code):**
  `docs/decisions/0008-roles-and-row-level-scoping.md`,
  `docs/decisions/0009-field-service-domain-model.md`,
  `docs/DATABASE_DESIGN.md` (new "Field-service domain (Phase 17)"
  section — the unit 2 schema, designed before implementing it),
  `docs/PERMISSIONS.md` (rewritten around roles; permission table,
  migration gotcha, and 403 notes kept), `docs/ROADMAP.md` (Phases
  17-25 re-sequenced; old 17-22 folded in and noted inline).
- **Roles:** `apps/users/roles.py` (Role enum, `user_role()` with
  per-instance cache, `RoleRequiredMixin` / `SalesRoleRequiredMixin` /
  `OwnerRequiredMixin`), `apps/users/models.py` (`UserProfile`),
  migrations `users/0001_initial` and `users/0002_roles` (creates the
  three groups, carries Staff's 11 permissions to Owner and Sales Rep,
  moves Staff members to Sales Rep, retires Staff — reversible).
- **Gating:** all 26 CRM view classes in `apps/crm/views.py` now use
  `SalesRoleRequiredMixin` (mechanical swap for `LoginRequiredMixin`);
  `SearchView` too. `DashboardView` branches: Owner/Sales see the
  existing business dashboard, Cleaners a schedule placeholder, no-role
  users a "no role assigned yet" notice.
- **Shell & navigation:** `apps/core/navigation.py` (single role-aware
  nav registry), `apps/core/context_processors.py` (brand name + nav),
  `templates/base.html` (sidebar ≥1024px, hamburger drawer below,
  phone bottom bar; one shared content block for shell and logged-out
  layouts), partials `_nav.html`, `_bottom_nav.html`, `_icons.html`
  (inline SVG sprite — CSP-safe), `_empty_state.html`; `403.html` and
  login restyled.
- **Design system:** `static/css/tokens.css` (new — light/dark tokens,
  ten service tones as classes), `static/css/base.css` (rewritten;
  every class existing templates use is kept), `static/css/nojs.css`
  (no-JS fallback), `static/js/nav.js` (drawer: focus handling, Escape,
  backdrop, Space on `role="button"` links, auto-close past 1024px).
- **PWA:** `apps/core/pwa.py` (manifest, precache list, content-hash
  cache version), `ManifestView` / `ServiceWorkerView` / `OfflineView`
  + routes, `apps/core/templates/core/sw.js`, `templates/offline.html`,
  `static/js/sw-register.js`, icons in `static/pwa/icons/`
  (SVG + 192/512/maskable/apple-touch PNGs), CSP `manifest-src` /
  `worker-src 'self'` in `config/settings/production.py`.
- **Settings:** `TIME_ZONE` now `America/New_York` (env
  `CRM_TIME_ZONE`), `CRM_BRAND_NAME` / `CRM_BRAND_SHORT_NAME` (env,
  default "Exterior CRM"), `app_shell` context processor.
- **Tests:** `apps/crm/tests/_helpers.py` (`grant_staff` →
  `grant_role`, ~45 call sites renamed), `apps/crm/tests/test_permissions.py`
  (rewritten for roles), `apps/core/tests/test_navigation.py`
  (rewritten), `apps/core/tests/test_dashboard.py` /
  `test_search.py` (grant a role in `setUp`), new
  `apps/users/tests/test_roles.py`, `apps/core/tests/test_pwa.py`.

## Commands

$ `python manage.py migrate` — applied `users.0001_initial`,
  `users.0002_roles` to the dev DB; groups: Owner (11 perms), Sales Rep
  (11 perms), Cleaner (0).

$ `python manage.py test` — first run after gating: 20 failures + 197
  errors, almost all `grant_staff()` looking up the retired Staff
  group; after the helper rename, 33, all in four modules encoding the
  old permission model; after rewriting those and adding new tests:
  **333 passed, 0 failures**.

$ `ruff check .` / `ruff format --check .` — clean after `ruff format`
  wrapped seven over-long test lines and `--fix` sorted one import.
$ `bandit -r apps config -q` — no findings. `pip-audit` — no known
  vulnerabilities. `manage.py check`, `makemigrations --check`,
  `check --deploy` (production settings) — no issues.

$ **Real-browser verification** (headless Chromium, Playwright in the
  scratchpad venv from Phase 16 — never a project dependency), dev
  server, throwaway users for Owner / Sales Rep / Cleaner / no role
  (deleted afterward):
  - 4 roles × 3 viewports (390×844 phone, 820×1180 tablet, 1280×800
    desktop) × 9 routes: every status as expected (Cleaner / no-role
    get 403 on the 7 customer pages, 200 on dashboard and password
    change), **no horizontal overflow anywhere**, no JS errors.
  - Drawer: starts closed on phone/tablet, opens from the bottom bar
    (phone) or top-bar button (tablet), sets `aria-expanded`, closes on
    Escape; sidebar visible and bottom bar hidden on desktop.
  - Screenshots reviewed: desktop and phone dashboards, phone drawer,
    Cleaner and no-role dashboards, dark-mode login and contacts.

$ **Production-settings pass** (same override module as Phase 16:
  real `production.py` except `SECURE_SSL_REDIRECT=False` for plain
  HTTP, `--insecure` for static files): **zero CSP violations** at
  phone and desktop widths; manifest fetched (`display: standalone`);
  service worker **activated** and controlling the page; with the
  network cut, navigating to `/contacts/` showed the offline page —
  confirming authenticated pages are never served from cache.

$ **Contrast check** (script over `tokens.css`): the first run found 3
  dark-mode failures — one `--color-primary` was serving both as link
  text on dark surfaces (needs to be light) and as a button fill under
  white text (needs to be dark). Split into `--color-link` /
  `--color-link-hover` for text and outlines; re-run: **all 52
  text/background pairs meet WCAG AA (≥ 4.5:1)** in light and dark.

## Tests

`python manage.py test` — 333 passed, 0 failures (304 existing, 29
new: roles, role-group migration forward/reverse, the nav/access
consistency matrix, shell rendering, PWA endpoints, production CSP).

## Decisions

- **Fail closed for users with no role** — they reach only the
  dashboard, which says a role is missing. Forgetting to assign a role
  must never expose customer data (ADR 0008).
- **403 for a disallowed page, 404 for an out-of-scope object** (the
  latter lands with job models in unit 2) — the page's existence isn't
  secret; a specific customer record is.
- **`PermissionRequiredMixin` kept under the role gate.** The old
  `LeadConvertRequiresBothPermissions` tests would otherwise have kept
  passing for the wrong reason (the role gate 403'ing first), so they
  now run as a Sales Rep whose group permissions are narrowed — a real
  scenario (the Owner editing the Sales Rep group in the admin).
- **Nav and access declared against the same role sets**, with a test
  that for every role checks every shown link opens and every hidden
  one is refused.
- **Service worker caches only the static shell + offline page, never
  pages** (shared crew phones). Cache version is a content hash of the
  precached files — identical across gunicorn workers, changes exactly
  when an asset changes; network-first for assets under `DEBUG` so CSS
  edits show immediately in development.
- **Icons as an inline SVG sprite** with `stroke`/`fill` set from the
  stylesheet — no inline `style=""`, which the production CSP forbids.
- **UserProfile photo deferred to unit 2** alongside Pillow and the
  login-gated media design, rather than creating a public-media path
  for staff photos now.

## Errors

- The verification harness's first pass flagged console "errors" for
  Cleaner / no-role users — these were the browser logging the
  *expected* 403 documents. Changed the harness to count those
  separately and assert the count matches the number of forbidden
  routes, so a real error can't hide among them.
- The first contrast run failed three dark-mode pairs (see Commands) —
  fixed by separating link and button-fill tokens.
- Two new tests initially failed for test-side reasons: the nav regex
  also matched the sidebar footer's "Change password" link, and the
  test client doesn't serve static files (checked with
  `staticfiles.finders` instead).

## Lessons learned

- When a new outer check is layered over an old one, tests of the old
  check can go on passing for the wrong reason — worth re-reading each
  existing boundary test and asking which layer now produces its
  result.
- A single "primary" color can't serve as both text on dark surfaces
  and a fill under white text; dark mode needs the two split.

## Git

Branch: `feature/field-service-shell`
Commit: `d5291cc` (implementation), `2cc1c22` (self-review fix — user/admin
docs still described the retired Staff group)
Merged to `main`: `77d2214` (PR #90 — CI green: `test` + `dependency-audit`;
Sourcery did not review: diff exceeded its 150,000-character limit, so a
deliberate self-review was done instead)

## Next

Phase 17 unit 2 — data model (`apps.jobs`, `apps.messaging`, crm
extensions), Lead → Contact / Deal → Quote data migration, follow-up
generator, `seed_demo`, Pillow.
