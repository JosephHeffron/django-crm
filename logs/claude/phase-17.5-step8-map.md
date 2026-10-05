# PHASE 17.5 STEP 8: MAP

Started: 2026-10-05
Ended: 2026-10-05

## Objective

The Map page the restyle calls for (ADR 0010), on OpenStreetMap
(ADR 0011): customer addresses as pins, with Leaflet vendored and
Nominatim for turning addresses into coordinates.

## Files created / changed

- `static/vendor/leaflet/` — Leaflet 1.9.4 (BSD-2-Clause) checked in:
  `leaflet.js`, `leaflet.css` and the marker images its CSS references,
  with a README giving the source, licence, SHA-256 of every file, and
  how to update. Served from this origin like everything else; the
  production CSP allows scripts and styles from `'self'` only, and
  there's no build step to fetch anything.
- `apps/crm/models.py` + migration `crm/0008_property_latitude_…` —
  `Property` gains latitude?, longitude?, located_at? and
  `located_address`, the address as it read when it was placed, so an
  edit re-opens the lookup without comparing field by field.
  `needs_locating` says whether it's worth asking.
- `apps/crm/geocoding.py` — Nominatim, **server-side, one request a
  second, with a User-Agent that says who we are**, which is their usage
  policy. Only the address is sent: no name, no phone, no job. "We
  couldn't ask" (`LookupError_`) is kept distinct from "it isn't there"
  (a plain None), because treating an outage as a missing address would
  quietly strand it. `place_by_hand()` sets a pin with no request at
  all.
- `apps/crm/management/commands/locate_properties.py` — the batch, with
  `--limit` and `--redo`. A command rather than something a page waits
  on, because one request a second is not a page's business.
- `apps/jobs/views.py` — `MapView` (Owner and Sales Reps) and
  `PropertyLocateView` (POST only: it writes, and the lookup leaves this
  server). **Nothing is looked up while the page renders.**
- `apps/jobs/templates/jobs/map.html` + `static/js/map.js` — the map,
  pins colored by whether a job is booked there this week, popups built
  as DOM nodes rather than HTML strings (names and addresses are
  people's data, and `textContent` can't become markup), the required
  "© OpenStreetMap contributors" attribution, and the same addresses
  listed below so nothing is reachable only by pointing at it.
- `config/settings/production.py` — `img-src` gains exactly
  `https://tile.openstreetmap.org`, named rather than wildcarded.
- `seed_demo` — demo addresses are placed with local coordinates
  scattered around Rochester. They're invented streets, so looking them
  up would find nothing and would send made-up addresses to a public
  service for no reason.
- Docs: USER_GUIDE (what the map shows, and exactly what is sent to
  whom), ADMIN_GUIDE (the command, the two things that reach the
  internet, and that Leaflet is vendored so Dependabot can't see it),
  PERMISSIONS, DATABASE_DESIGN.
- Tests: `apps/crm/tests/test_map.py` (25) — a found address stored with
  what it was looked up from, only the address being sent, the
  User-Agent, "not found" versus "couldn't reach", a reply we don't
  understand, an edit re-opening the lookup, a hand-dropped pin, the
  command's four outcomes, the page's pins and list, a cleaner refused,
  and **that rendering the page calls nothing**.

## Decisions

- **One request per second, from the server, never on a page.** The Map
  page lists what still needs placing; the Owner asks for it, or the
  command works through them. A slow third party delays nobody.
- **Checksums in the repo.** Dependabot can't see vendored files, so
  updating Leaflet is a deliberate step with the sums recorded in the
  same commit.
- **The tile host is named exactly** in the CSP. A wildcard would let
  any image source in, and the map needs one host.

## Verification

$ `manage.py test` — 721 tests, OK (696 before, 25 new). The migration
  reverses cleanly.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright under production settings, 20 checks, **zero CSP
  violations**: the map drawing 12 pins from 15 OpenStreetMap tiles with
  the attribution shown; every script and stylesheet served from this
  origin and none from a CDN; a pin opening with its customer and
  address; the same addresses listed below; looking one address up for
  real through the page and reporting what happened; a Cleaner refused
  and shown no Map link; a Sales Rep allowed; phone light and dark
  without overflow. The addresses placed for the check were cleared
  afterwards.

## Errors

- **`opener=urlopen` as a default argument made the network
  unsubstitutable.** A default is captured when the function is defined,
  so `mock.patch` on this module's `urlopen` did nothing — and four
  tests that believed they had stubbed the network were calling the real
  Nominatim. Now resolved at call time. Worth remembering: a test that
  silently reaches a third party is worse than one that fails.
- The check script's `request.post` can't carry CSRF the way a form post
  does (the same trap as step 7), so the hand-placed pin is covered by a
  unit test and the browser check clicks the real "Look it up" form
  instead — one request, inside Nominatim's policy, against an invented
  demo address rather than a customer's.

## Git

Branch: `feature/restyle-map`
Commit: pending
Merged to `main`: pending

## Next

Step 9 — Reports.
