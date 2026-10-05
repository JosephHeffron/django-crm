# Leaflet 1.9.4 (vendored)

Served from this origin like every other script and stylesheet: the
production CSP allows scripts and styles from `'self'` only, and
`CLAUDE.md` rules out a build step, so these files are checked in
rather than fetched from a CDN (ADR 0011).

- Source: https://unpkg.com/leaflet@1.9.4/dist/
- Licence: BSD-2-Clause (see https://github.com/Leaflet/Leaflet)
- Files: `leaflet.js`, `leaflet.css`, `images/` (the marker and layers
  sprites `leaflet.css` references by relative path)

## Checksums

Verify after any update, and record the new ones here:

```
db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a  leaflet.js
a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6  leaflet.css
066daca850d8ffbef007af00b06eac0015728dee279c51f3cb6c716df7c42edf  images/layers-2x.png
1dbbe9d028e292f36fcba8f8b3a28d5e8932754fc2215b9ac69e4cdecf5107c6  images/layers.png
00179c4c1ee830d3a108412ae0d294f55776cfeb085c60129a39aa6fc4ae2528  images/marker-icon-2x.png
574c3a5cca85f4114085b6841596d62f00d7c892c7b03f28cbfa301deb1dc437  images/marker-icon.png
264f5c640339f042dd729062cfc04c17f8ea0f29882b538e3848ed8f10edb4da  images/marker-shadow.png
```

Check them with, from this directory:

```
sha256sum -c <<'SUMS'
db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a  leaflet.js
a7837102824184820dfa198d1ebcd109ff6d0ff9a2672a074b9a1b4d147d04c6  leaflet.css
SUMS
```

## Updating

Download the new version's `dist/` files, replace these, re-run the
checksums above, and record them here in the same commit. Nothing
updates automatically — Dependabot doesn't see vendored files.
