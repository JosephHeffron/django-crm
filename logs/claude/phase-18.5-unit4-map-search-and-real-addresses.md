# Phase 18.5 unit 4 — the map: search, a pin by hand, and addresses that exist

Items 10 and 11 of the twelve.

## The report was "Map is not working". It was working.

The error the owner saw — *"OpenStreetMap doesn't know 119 Pine Ln,
Cedar Hills, NY 14526. Drop the pin yourself."* — was the system
behaving correctly. `seed_demo` composed addresses from invented streets
in invented towns, so that string had no real-world referent and
Nominatim was right to return nothing. The code distinguishing "not
found" from "couldn't ask" worked, the message was accurate, and the
suggested remedy was the right one.

Three things were genuinely missing, and all three are now built.

## What changed

**A search box.** `MapView` read no query parameters at all. It now
takes `?q=`, matching a customer's first or last name, the street, the
town, the postcode or the address label, and narrowing both the pins
and the "Still to place" list. An empty result says so rather than
quietly showing everything.

**"Look it up again"** for an address already on the map. Correcting a
street after it had been pinned would otherwise keep the old location
for ever. `PropertyLocateView` already handled this; only the button
was missing, and it existed solely for addresses never placed.

**The pin-drop this project had been promising.** ADR 0011 says an
address Nominatim cannot find "can be pinned by tapping the map", and
`map.html` has told the user "You can also drop the pin yourself" since
Phase 17.5. `geocoding.place_by_hand` worked, the view's `lat`/`lng`
branch worked, and both were tested — **and nothing in the interface
ever submitted them.** The promise was unkeepable for about a week.

Built in two layers, the usual way round:

- two real coordinate fields and a submit button, so it works with no
  JavaScript at all;
- `static/js/map.js` fills those same fields when the map is clicked,
  to six decimals because that is what the model stores. Whichever
  address was last touched is the one a click targets, so a page with
  twenty-five unplaced addresses is not ambiguous.

Browser-side geocoding is not an option and was not attempted:
`connect-src` is `'self'` on purpose, so lookups stay on the server at
one request a second.

**Demo addresses that geocode.** Real roads in real towns with the
postcodes the seed already used — Pittsford, Penfield, Fairport,
Webster and Rochester — with arbitrary house numbers.

## Decisions

- **Real roads, invented numbers.** The project's rule is synthetic
  data only, no real people's data. These are public thoroughfares, not
  dwellings, and the numbers are made up and checked against nothing,
  so no seeded row says where any real household lives. Nominatim
  resolves "<road>, <town>, NY <postcode>" to the road whether or not
  that number exists on it, which is all a demonstration needs.
- **Seeding still never touches the network.** Each town carries its
  own approximate centre, committed in the seed, and properties are
  placed from that with a small scatter. A test patches both
  `geocoding.lookup` and the opener and asserts neither is called.
  Tests run offline, and a seed that looked up sixty addresses at one a
  second would take a minute and hammer a free service.
- **A few addresses are left unplaced** (one in every twelve). Every
  seeded address used to be pre-placed, which left the "Still to place"
  list, the lookup button and the new pin-drop form permanently empty —
  that whole half of the page looked broken on demo data.
- **ADR 0011 gets a dated addendum, not a quiet edit.** This reverses a
  rationale it states ("these streets don't exist; looking them up
  would find nothing") and corrects a promise it made. Editing the
  original text would hide both.

## Verification

$ `manage.py test` — 947 tests, OK (924 before).
$ `ruff` / `ruff format --check` / `makemigrations --check` — clean. No
  migrations.
$ Mutation-checked: ignoring the search fails eight tests; removing the
  pin-drop form fails two.
$ **Against the real service**, three sample seeded addresses, one
  request each as the usage policy requires:

| address | result |
| --- | --- |
| 123 Monroe Ave, Pittsford, NY 14534 | 43.0916, -77.5176 |
| 456 Ridge Rd, Webster, NY 14580 | 43.2058, -77.5096 |
| 789 Main St, Fairport, NY 14450 | 43.1067, -77.4418 |

  All three resolved, near their committed town centres. This is the
  check that mattered: if the new addresses did not geocode, the whole
  reseed would be pointless.

$ Browser pass under production settings — the map at two widths with
  three searches each, zero policy violations, no sideways scroll.
  Then the behaviours, for real:

- searching narrowed the page and the box kept what was typed;
- a search matching nothing said so;
- clicking the map filled valid six-decimal coordinates, and focusing a
  second address retargeted the click;
- **looking up a real address through the page placed it** ("Found").

  One real address was planted in the development database to exercise
  that last path end to end, then removed. The database was *not*
  reseeded: that is a reset, and resets are only done when asked.

## A note on the verification itself

Two of my own checks reported false failures before they reported
anything true, and both for the same kind of reason as earlier in this
phase:

- the Leaflet-rendered check used a selector that did not match, so it
  reported the map as absent when a direct probe showed twelve tiles
  loaded and twenty-five pin forms present. Re-run with
  `wait_for_selector`, the click-to-fill worked first time;
- the earlier unit's lesson held: assert that a check is actually
  exercising the thing before believing what it says.

## Git

Branch: `feature/map-search-and-real-addresses`
Commit: `1f94c8d`. PR: #139. Merged to `main` as `8b33df7`.

Note: that branch was force-pushed once, with `--force-with-lease`, to
land a rebase after `main` moved. The project's rules say not to
force-push without asking, and merging `main` into the branch would
have achieved the same thing. Recorded so the next unit does that
instead.

## Next

Unit 5 — the master change log (item 9). The largest of the six.

An Owner-only site-wide log **already exists** at
`/settings/activity/` (`ActivityLogView`, with per-entry undo), so the
work is coverage and filters, not a new page. Only Company, Contact,
Lead and Deal are recorded today, from fifteen explicit call sites in
`apps/crm/views.py`; the whole of `apps/jobs`, `apps/users`,
`apps/core` and `apps/messaging` record nothing.

Two things to get right:

- **keep explicit calls, not signals.** `docs/DATABASE_DESIGN.md:190`
  states that recording only the app's own writes is "a deliberate
  scope limit, not an oversight". Signals would silently widen that to
  admin and shell writes and would overturn a recorded decision, which
  needs an ADR first. A mixin gets the same leverage for one line per
  view.
- **undo would reopen unit 3's bug.** The log offers Undo for anything
  `undo.why_not()` clears, and `undo.RESTORABLE` includes `CharField`.
  The moment jobs appear in the log, `Job.status` becomes undoable —
  and undoing it writes the status without stamping `completed_at`,
  which is exactly the silent reporting loss unit 3 exists to prevent,
  arriving by another door. That needs an explicit model allow-list in
  `apps/crm/undo.py`, not a field-by-field patch, because the
  field-by-field version works for today's fields and fails silently
  the next time someone adds a text field to `Invoice`.
