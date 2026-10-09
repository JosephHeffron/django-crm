# 0011 — Map on OpenStreetMap (Leaflet + Nominatim)

## Context

The restyle (ADR 0010) includes a Map page: customer and job locations
as pins, colored by status, on an interactive map. The CRM has no map
provider and stores addresses as text only (`crm.Property`). The owner
chose free OpenStreetMap over Google Maps.

Per `CLAUDE.md`, a new external dependency must state why it's needed,
its cost, security implications, and the simpler alternative.

## Alternatives considered

- **Google Maps.** Rejected by the owner: an API key and billing
  account, per-load cost, customer addresses sent to Google, and CSP
  exceptions for several Google domains. It does offer satellite
  imagery, which OpenStreetMap's free tiles don't.
- **No map; addresses as links to a maps site** (what job pages do
  today). The simpler alternative — kept as the fallback — but it can't
  show many customers at once, which is the page's purpose.
- **Self-hosted tile server.** Rejected: gigabytes of map data and a
  rendering stack on a Raspberry Pi, far beyond this project's scale.

## Decision

- **Leaflet** (BSD-2-Clause, ~40 KB gzipped) is vendored into
  `static/vendor/leaflet/` — loaded from our own origin like every other
  script, no CDN, no build step.
- **Map images** come from OpenStreetMap's public tile servers. The CSP
  gains exactly `img-src https://tile.openstreetmap.org` (and nothing
  else). The map shows the required "© OpenStreetMap contributors"
  attribution. Usage stays well inside the OSMF tile policy for a
  handful of staff users.
- **Addresses → coordinates** through OSM's Nominatim service, called
  **server-side**, one request per new or changed address, at most one
  per second, with a descriptive User-Agent (Nominatim policy). Results
  are stored on the property (latitude/longitude and when they were
  looked up), so each address is sent once, not on every page view.
- **Manual placement** is always possible: an address Nominatim can't
  find, or places the owner would rather not send, can be pinned by
  tapping the map.

## Consequences

- **Privacy:** service addresses (not names or contact details) are
  sent to the OpenStreetMap Foundation's servers once each for lookup,
  and staff browsers fetch map tiles from OSM, which reveals the areas
  being viewed. Documented in `docs/PERMISSIONS.md` / the user guide.
- **Availability:** the Map page needs internet access; the rest of the
  app does not. If tiles or lookup are unavailable, the page says so
  and pins already geocoded still list.
- **No satellite view** on the free service.
- **Security:** Leaflet is pinned by version and checksum in the repo;
  updates are deliberate, like any dependency.

## Date

2026-09-29

## Addendum — demo addresses, and the pin-drop that was missing

**Date: 2026-10-07 (Phase 18.5 unit 3).**

Two things this decision described turned out not to be true of the
running app, and both are corrected rather than quietly edited above.

### The demo data could never be looked up

The seed composed addresses from invented streets in invented towns
("119 Pine Ln, Cedar Hills, NY 14526") and pre-placed them at random
coordinates near Rochester, with the stated reasoning that looking up a
made-up address would find nothing and would send it to a public
service for no reason. That reasoning was sound as far as it went, and
the consequence was that the Map page's lookup **could only ever fail
on demo data**, which read as the map being broken. It was reported as
exactly that.

Reversed deliberately: the seed now uses **real roads in real towns**
with the real postcodes already in use — Pittsford, Penfield, Fairport,
Webster and Rochester — with **arbitrary house numbers**.

The privacy line that matters: these are public thoroughfares, not
dwellings. The numbers are invented and are not checked against any
real address, so no seeded row says where any real household lives,
which keeps the project's synthetic-data-only rule. Nominatim resolves
"<road>, <town>, NY <postcode>" to the road whether or not that number
exists on it, which is all a demonstration needs.

Two invariants hold, and are tested:

- **seeding never touches the network.** Each town carries its own
  approximate centre, committed in the seed, and properties are placed
  from that. A test patches both `geocoding.lookup` and the opener and
  asserts neither is called.
- **a few addresses are left unplaced**, so the "Still to place" list,
  the "Look it up" button and the pin-drop form all have something to
  show. Every address used to be pre-placed, which left that half of
  the page permanently empty.

### The pin-drop was promised but unreachable

This decision says an address Nominatim cannot find "can be pinned by
tapping the map", and the Map page has told the user so since Phase
17.5. `geocoding.place_by_hand` and the view's lat/lng branch both
worked, and both were tested — but **nothing in the interface ever
submitted them**. The promise was unkeepable for about a week.

Now built, in two layers:

- **the baseline needs no JavaScript**: two real coordinate fields and
  a submit button, next to "Look it up";
- **the enhancement** fills them in when the map is clicked
  (`static/js/map.js`), writing into those same fields. Whichever
  address was last touched is the one a click fills, so a page with
  several is not ambiguous.

Browser-side geocoding remains impossible by design: `connect-src` is
`'self'`, so lookups stay on the server at one request a second.

Also added in the same unit: a search box, and "Look it up again" for
an address already placed — correcting a street after it was pinned
would otherwise keep the old location for ever.
