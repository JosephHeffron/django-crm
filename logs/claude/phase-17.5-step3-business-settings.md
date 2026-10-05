# PHASE 17.5 STEP 3: BUSINESS SETTINGS AND CURRENCY

Started: 2026-10-05
Ended: 2026-10-05

## Objective

The Owner's Business Settings page (ADR 0010): business name, logo
with crop, contact details, website and social links, currency, and
data export — so the app shows the business's own name and logo, and
every amount its currency.

## Files created / changed

- `apps/core/models.py` + migration `core/0001_business_settings` —
  `BusinessSettings` (single row, CheckConstraint `id = 1`; `load()`
  returns unsaved defaults rather than writing on a read): name,
  logo, contact email/phone, currency (USD / CAD), updated_at.
  `BusinessLink`: platform (partial unique — one per main platform),
  label (required for "other"), url, position. Reversible (verified:
  unapply → reapply on the dev database).
- `apps/core/business.py` — `BusinessSettingsMiddleware` loads the row
  once per request (`request.business` + a context variable);
  `currency_symbol()` for the `money` filter, falling back to "$"
  outside a request without touching the database.
- `apps/core/branding.py` — every logo upload is validated (≤5 MB,
  JPEG/PNG/GIF/WebP, ≤40 megapixels — refuses decompression "bombs"),
  EXIF-rotated, cropped to the chosen square (or the center square),
  shrunk to ≤512px, and re-encoded as PNG with no metadata. The
  uploaded bytes are never stored.
- `apps/core/export.py` — streamed CSV/JSON of customers, companies,
  jobs, estimates, invoices, payments, expenses, team; formula cells
  (=, +, -, @, tab, CR) prefixed with an apostrophe (CSV injection);
  no password fields.
- `apps/core/forms.py`, `views.py`, `urls.py` — `/settings/business/`
  (Owner; one form + logo + links formset, saved atomically; a replaced
  or removed logo file is deleted after the save), `/settings/business/
  export/` (Owner), `/branding/logo/` (public, cacheable, versioned
  URL).
- `money` filter uses the business currency ("CA$" for CAD). Brand
  name/logo from the settings in the title, sidebar, top bar, sign-in
  page, and the PWA manifest; gear menu gains "Business settings".
- `templates/core/business_settings.html`, `_link_row.html`,
  `static/js/settings.js` (Add link; crop dialog — the picked file is
  decoded with `createImageBitmap` into a canvas, so the CSP needs no
  `blob:` exception; drag, arrow keys, size slider; only the square's
  coordinates are sent), CSS for the upload box, link rows, export row,
  crop dialog.
- Docs: USER_GUIDE (Business Settings), ADMIN_GUIDE (where the logo
  lives, backups), PERMISSIONS, DATABASE_DESIGN.
- Tests: `apps/core/tests/test_business_settings.py` (20) — access;
  reading never creates the row; saving and showing name/contact/
  currency everywhere incl. the manifest; CAD formatting; brand
  fallback; read-only owner name; crop, center crop, out-of-bounds
  fallback, re-encode without EXIF, ≤512px; rejection of non-images,
  wrong formats, >5 MB, and a 48-megapixel image; logo served /
  replaced (old file deleted) / removed; logo on the sign-in page;
  links (one per platform, labeled others, blank rows ignored,
  delete); every export in both formats, formula neutralizing, team
  export without passwords, bad parameters.

## Skipped (self-hosted)

Customer Tips (no online payments), Upgrade Plan, Stripe Connect.

## Verification

$ `manage.py test` — 527 tests, OK.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright (session scratchpad was cleared between sessions — the
  venv, production-settings config, and check scripts were rebuilt):
  pick a logo → crop dialog → resize and drag → apply → preview; add a
  website and an Other link; save; logo and name in the sidebar and on
  the sign-in page; CA$ on Financials; export download; phone light and
  dark without overflow; Sales Rep refused. Then a sweep of 19 pages ×
  3 roles × light/dark × phone/desktop. Both under production settings:
  zero CSP violations. The check's sample business settings were
  removed from the dev database afterwards; demo users' saved themes
  reset to "match device".

## Errors

- An error message with an apostrophe didn't match in a test (HTML
  escaping) — matched on another part of the message.
- Link-row labels ended in Django's ":" — rendered plainly.
- A no-JS note claimed a blank link row appears after saving while the
  formset offered none — now one blank row is always offered.

## Git

Branch: `feature/business-settings`
Commit: pending
Merged to `main`: pending

## Next

Step 4 — Dashboard to the reference layout (onboarding checklist,
greeting, overview cards with revenue charts, Add New Job, Jobs Today,
quick actions, goals) with notifications and goals models.
