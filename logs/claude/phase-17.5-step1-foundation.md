# PHASE 17.5 STEP 1: RESTYLE FOUNDATION

Started: 2026-09-29
Ended: 2026-09-29

## Objective

First step of the UI restyle (ADR 0010): design decisions recorded,
the screenshot safety net, new design tokens, the Inter font, multi-
color icons, and the shared components every later step builds on —
all shown on an Owner-only style guide page.

## Decisions (with the user)

- Restyle before Phase 18; OpenStreetMap for the map; Contacts →
  Customers with a Customers flyout; Inbox → team Messages; build every
  gap that can be real; sidebar footer links → an email address from
  settings (never in the public repo).
- Reference screenshots contain real people's data: kept outside the
  repo (`~/design-reference/`), never transcribed; `.gitignore` safety
  net added. None were available for this step — built from the
  written spec.
- Numbered **Phase 17.5** instead of renumbering Phase 18+ (about 40
  references, including a migration and all Phase 17 logs, would
  otherwise go stale).

## Files created / changed

- `docs/decisions/0010-ui-restyle.md`, `0011-openstreetmap-map.md`;
  `docs/ROADMAP.md` (Phase 17.5 entry); `.gitignore` (screenshot
  patterns — no tracked file newly ignored).
- `static/css/tokens.css` — rewritten: new palette (light + dark,
  dark applied by OS preference or `<html data-theme>`), radii 8–60px,
  soft shadows, Inter `@font-face`, `.accent-*` classes, avatar colors.
  Existing variable names kept, so every page picks up the new look.
- `static/fonts/inter/` — Inter variable woff2 (latin, 48 KB) + OFL
  license, self-hosted (CSP font-src 'self'; no Google Fonts).
- `static/css/base.css` — existing components restyled in place
  (cards, stat cards, pill buttons, filled pill inputs with labels
  floated onto the border via `:has()`, chips, avatars, empty states,
  tab bar, tables with a pill header and total rows); new components
  (page banner, breadcrumb header, icon circles/buttons, segmented
  toggle, date chip, info banner, toggle row + switch, settings shell
  + section cards, field rows, hub cards, password checklist,
  collapsible release cards, pagination).
- `templates/partials/_icons.html` — 30 line icons and 14 multi-color
  nav icons; `_empty_state.html` (icon circle, optional text link);
  `_pagination.html` ("Showing x–y of N entries", numbered pages,
  per-page select); `_field.html` (one field in as_p shape, plain
  label).
- `apps/core/pagination.py` — `PerPageMixin` (10/25/50/100) on the six
  list pages that use the partial.
- `apps/core/templatetags/crm_format.py` — `elided_page_range`,
  `avatar_class` (CRC-based, stable), `initials`.
- `static/js/ui.js` — `select[data-autosubmit]` (no-JS fallback
  button); added to the PWA precache with the font.
- `apps/core/views.py` + `core/styleguide.html` — `/styleguide/`,
  Owner only, synthetic data.
- Theme colors in `base.html` and the manifest updated. (The app icon
  keeps the old blue until the logo upload in step 3.)
- Tests: style guide access/content, pagination (page size, bad
  values, kept filters), avatar/initials filters.

## Verification

$ WCAG AA check of 107 color pairs, light and dark — 0 failures after
  darkening the text shades of green and red.
$ `manage.py test` — 500 tests, OK.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright: Owner (style guide + 7 existing pages) and Cleaner (3
  pages) × light and dark × 390×844 and 1920×1080 — all 200, no
  horizontal overflow, Inter loaded, no console errors; screenshots
  reviewed. Same pass under production settings: zero CSP violations.

## Errors

- The pagination partial didn't `{% load %}` its filters (included
  templates don't inherit them) — caught by the new tests.
- Screenshot review: big values overflowed or wrapped mid-number in
  narrow stat cards (now scale to the card via container units and
  never wrap); floating labels ended in Django's ":" (field partial
  renders the plain label); the sidebar's Log out button picked up the
  new button shadow; sub-heading spacing.

## Review

Sourcery skipped PR #106 (its 7-day window still counted last week's
PRs), so a self-review of the full diff. One defect, fixed in a
follow-up commit on the PR: the floating label's background was white
on its top half (to blend into a white card), so on forms that sit
directly on the grey page — the task, company, and activity forms — a
white strip showed behind each label. The top half is now transparent
(checked on the task form and the style guide, light and dark).

Also checked: pagination edge cases (single page, ellipsis), the
same-origin font preload, the PWA precache hash, which buttons inherit
the new shadow (link and nav buttons opt out), container-query sizing,
and that the style guide is Owner-only.

## Git

Branch: `feature/restyle-foundation`
Commits: `66f3587` (feature), `83c80f8` (self-review fix)
Merged to `main`: PR #106, merge commit `0a93877`

## Next

Step 2 — the app shell: floating sidebar with flyouts (Customers,
Crew, Job, Finance), top bar (search pill with ⌘K palette, Create
menu, bell, moon toggle saved to the profile, settings gear), help
button, keyboard shortcuts, footer email links.
