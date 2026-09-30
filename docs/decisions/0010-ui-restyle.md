# 0010 — UI restyle to a rounded "field service" design (Phase 17.5)

## Context

With Phase 17 every page exists, but the owner wants the look, layout,
and navigation to match a reference field-service CRM they supplied as
screenshots: a floating rounded sidebar with flyout submenus, a top bar
(search palette, Create menu, notifications, dark-mode toggle, settings
gear), heavily rounded cards and pill buttons, colorful stat cards, and
settings pages built from rounded section cards. It is a front-end
restyle and restructure, not a rewrite: data models, routes, roles, and
business logic stay.

The reference is a commercial product. Its name, logo, and copy are not
used. Its screenshots contain real people's data, so they are kept
outside the repository (which is public) and never transcribed into
code, fixtures, tests, or docs.

## Alternatives considered

- **Adopt a CSS framework (Tailwind) or a component library.** Rejected:
  Tailwind needs a Node build step the project doesn't have
  (ADR 0003: server-rendered pages, no JS toolchain), and component
  libraries assume a JS framework. The existing token-based CSS already
  expresses the design.
- **Load Inter from Google Fonts.** Rejected: the production CSP allows
  fonts only from `'self'`, and every page view would be reported to a
  third party. Inter is OFL-licensed, so it is bundled (one variable
  woff2, latin subset, ~48 KB).
- **Keep dark mode OS-only.** Rejected: the design has an explicit
  toggle. The choice is saved on the user's profile (so it follows them
  across devices) and applied server-side as `<html data-theme>` — no
  flash of the wrong theme and no browser storage.

## Decision

- **Tokens** (`static/css/tokens.css`) take the new palette, radii
  (8 → 60px), soft shadows, Inter, accent classes (`.accent-*`), and
  avatar colors. Text colors are adjusted where the sampled color is
  too pale for small text (WCAG AA 4.5:1, checked for 107 pairs in
  light and dark); the vivid shades remain for fills, icons, and bars.
- **Shared components** are CSS classes plus small template partials,
  built once and shown together on an Owner-only style guide page
  (`/styleguide/`): stat cards (plain / tinted / outlined / curved
  accent arc), data tables with a pill header and total rows, empty
  states, segmented toggles, date-range chips, filled pill inputs with
  labels floated onto the border (CSS `:has()`, degrading to a label
  above the field), switches and toggle rows, settings shell and
  section cards, hub cards, chips, avatars, pagination with page size,
  password checklist, collapsible release cards, multi-color nav icons.
- **Navigation** (step 2): Contacts becomes **Customers**; a Customers
  flyout holds Customers, Companies, Follow-ups, Tasks, Notes, and
  Activities; **Inbox** opens team Messages until customer texting
  exists. Roles still decide what each person sees (ADR 0008).
- **Gaps are built, not faked.** Screens needing data the CRM lacks get
  real models (business settings, notifications, goals, time clock, pay
  rates, indicators, map pins…) or a clear "not available yet" state —
  never hard-coded numbers. Screens that only make sense for a
  subscription product (plans, billing, referrals, Stripe, tips,
  branches) are skipped.
- Still no inline styles or inline scripts: anything dynamic is a
  class, and behavior lives in small vanilla JS files.

## Consequences

- Every existing page changes appearance as soon as the tokens and
  components land; later steps restructure layouts page by page.
- More new models over the phase than a pure restyle would imply, each
  with its own migration and tests.
- The phase is numbered 17.5 so existing "Phase 18+" references in
  code and logs stay correct.

## Date

2026-09-29
