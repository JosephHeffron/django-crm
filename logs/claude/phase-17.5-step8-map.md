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

$ `manage.py test` — 724 tests, OK (696 before, 28 new). Both
  migrations reverse cleanly.
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

## Self-review (PR #122)

No review threads and nothing from Sourcery, so the diff was read by
hand. One real defect:

**The Map page loaded every property into memory to filter in Python**
— `[p for p in Property.objects.all() if p.needs_locating]` — which is
exactly what `CLAUDE.md`'s performance rule 2 forbids. The question is
now asked of the database: `Property.needing_location()` builds the
address in SQL and compares it with the snapshot taken when it was
placed, so the page counts and slices instead of fetching everything.
The classmethod lives beside `__str__`, because it mirrors it and the
two must not drift. `located_address` grew to 450 characters (migration
`crm/0009`) so a maximum-length address can hold its whole snapshot and
can't look permanently stale. Pins are capped at 500, with the page
saying how many are placed but not drawn.

Two tests of my own needed fixing before they were worth anything:
the first asserted the page's query count against *its own measurement*
of the page's query count, which can only pass; the second compared
query counts across two data sizes, which the old Python-side filter
would also have passed, since it was one query too. The test now checks
the thing that actually matters — that the question is a filtered,
sliceable queryset — and that the page counts and slices rather than
listing everything.

Re-verified in the browser under production settings: all 20 checks
again, zero CSP violations. The addresses placed for the check were
cleared afterwards.

## Git

Branch: `feature/restyle-map` (PR #122)
Commits: `42331c9` (the step), self-review fix to follow
Merged to `main`: pending

## Next

Step 9 — Reports.
