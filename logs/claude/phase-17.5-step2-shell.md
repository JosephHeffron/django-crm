# PHASE 17.5 STEP 2: APP SHELL

Started: 2026-09-30
Ended: 2026-09-30

## Objective

The restyle's app shell (ADR 0010): floating sidebar with flyout
groups, the top bar (search with a ⌘K command palette, Create menu,
refresh, dark-mode toggle, settings gear), the floating help button,
keyboard shortcuts, and the sidebar footer email links.

## Files created / changed

- `apps/core/navigation.py` — rewritten: `SECTIONS` (direct links
  Dashboard and Inbox; groups Customers, Crew, Job, Finance, each
  hidden when the person can open none of its links), the Create and
  gear menus, the per-role phone bottom bar, keyboard shortcuts; the
  longest matching view-name prefix marks the current link (Follow-ups
  beats Tasks). Contacts is now **Customers**; **Inbox** opens team
  Messages. Crew holds Team (Owner) and Finance holds Financials until
  steps 6–7 add their pages.
- `templates/base.html` + partials `_sidebar.html` (was `_nav.html`),
  `_topbar.html`, `_bottom_nav.html`, `_help.html`, `_palette.html`.
  Flyouts, Create, gear, and help are `<details>`, so they work
  without JavaScript.
- `static/js/nav.js` — drawer (unchanged behavior), one-open-at-a-time
  and close-on-outside-click/Escape for flyouts and menus, sidebar
  collapse remembered in a cookie the server reads (no flash), theme
  toggle (flips `<html data-theme>` in place, saves by fetch), command
  palette (filters every allowed page/action; sales roles also get live
  results), two-key shortcuts that follow the links rendered for this
  person (so they respect roles), "?" for help. Result rows are built
  with DOM methods, never HTML strings.
- `static/css/base.css` — shell rewritten (floating rounded sidebar,
  flyouts beside it on desktop and inline in the drawer, transparent
  top bar, pill search with ⌘K hint, dropdowns, palette dialog, help
  button, floating phone bottom bar, collapsed icon-only mode);
  `nojs.css` updated.
- `apps/users` — `UserProfile.theme` (system / light / dark) +
  migration `0005_userprofile_theme`; `ThemeView` (`/profile/theme/`,
  POST: 204 for the script, safe redirect for the form fallback).
- `apps/core/views.py` — `SearchSuggestView` (`/search/suggest/`, sales
  roles, JSON, top 8: jobs and estimates by number, customers,
  companies, tasks).
- `apps/core/context_processors.py` — saved theme (read, never
  created, on GET), collapsed-sidebar cookie, support email.
- `config/settings/base.py` + `.env.example` — `CRM_SUPPORT_EMAIL`
  (blank hides the links; never hard-coded in the public repo).
- Docs: `docs/USER_GUIDE.md` (Getting around), `docs/ADMIN_GUIDE.md`
  (support email).
- Tests: `apps/core/tests/test_navigation.py` rewritten — sidebar per
  role, the nav/access consistency check over every destination
  (sidebar and menus), current-link selection, search pill / Create /
  gear per role, bottom bar per role, role-filtered shortcuts, footer
  email on/off, collapse cookie, theme save/render/fetch/bad
  value/unsafe next/login, suggest JSON and cleaner refusal.

## Verification

$ `manage.py test` — 507 tests, OK.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright, interactive (light and dark, 1920×1080): flyout opens
  beside the sidebar; one at a time; outside click and Escape close it;
  gear and Create menus; theme toggle changes the page and survives a
  reload; collapse survives a reload; Ctrl+K palette with live results;
  palette Enter navigates; "g c" opens Customers; no overflow, no
  console errors. Phone (Cleaner): drawer with the Job group inline,
  bottom bar Dashboard / Scheduling / Inbox / Profile. JavaScript off:
  flyouts still open. All of it again under production settings —
  zero CSP violations (the theme and suggestion fetches are same-
  origin) — plus the step-1 page pass and the Phase 17 Financials and
  Messages/Profile passes.

## Errors

- Screenshot review: the top bar's menu button and the sidebar's close
  button showed on desktop, and the refresh/moon buttons on phones —
  the shared `.icon-btn` rule (declared later) overrode the shell's
  show/hide rules; selectors made more specific. "Log out" centered
  (button text alignment); gear-menu rows wrapped.
- The verification script raced the shortcut's navigation; it now
  waits for the URL.
- Owner sidebar link count in the new test was off by one (12, not 13).

## Git

Branch: `feature/restyle-shell`
Commit: pending
Merged to `main`: pending

## Next

Step 3 — Business Settings (name, logo with crop, contact details,
links) and currency, so the sidebar shows the business's own logo and
name.
