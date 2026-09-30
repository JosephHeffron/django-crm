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
