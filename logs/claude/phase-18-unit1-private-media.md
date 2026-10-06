# PHASE 18 UNIT 1: PRIVATE MEDIA

Started: 2026-10-06
Ended: 2026-10-06

## Objective

Phase 18 needs photo upload, and photos were always meant to be
login-gated: both upload paths have said since Phase 17 that files under
`media/private/` are "served only through the login-gated view". That
view didn't exist, and Caddy served the whole of `media/` straight from
disk — so a profile picture was readable by anyone with its URL, and a
job photo would have been the moment the first one was uploaded.

This unit builds the view and closes the hole, before anything starts
writing photos.

## Files created / changed

- `apps/jobs/media.py` — `send_private_file()` and `PhotoView`. Two
  rules: you have to be signed in, and you have to be allowed to see the
  job or estimate the photo belongs to, through the same `jobs_for()` /
  `quotes_for()` scoping every other view uses. **Out of scope is a 404,
  never a 403** — a 403 would confirm the photo exists. A row whose file
  has gone (a restore that missed the media volume) is a 404 too, which
  is the truth.
- `apps/users/views.py` — `AvatarView`, the same thing for a profile
  picture. Anyone with a role may see a teammate's; a signed-out visitor
  may not.
- Responses carry `nosniff`, `Content-Disposition: inline`, and
  `Cache-Control: private, no-store`, so a shared cache can't keep a
  copy that another person's request is served from.
- `Caddyfile`, `Caddyfile.dev` — `/media/private/*` now answers 404.
  Everything else under `media/` (the business logo) stays public on
  purpose.
- Docs: ADMIN_GUIDE (what's private, that the 404 must stay, and the
  cost), PERMISSIONS (two rows).
- Tests: `apps/jobs/tests/test_private_media.py` (18) — signed out,
  the crew member on the job, a crew member on a different job, the
  Owner, no role, an unknown photo, a missing file, an estimate photo,
  the headers, that the stored name is the UUID and never the uploaded
  filename, avatars, and **that both Caddyfiles still refuse the path
  with a handler placed ahead of the one that serves files** (see the
  review finding below for why the ordering, not the mere presence, is
  what's asserted).

## Decisions

- **Django reads the file; no internal redirect.** Handing it to the web
  server with `X-Accel-Redirect`-style config is faster, but it's a
  second code path that can only be tested on the real machine. At this
  size — a handful of staff, a few photos a job — reading it through
  Django is the right trade, and the admin guide records what the
  upgrade would be and that it needs testing on hardware first.
- **A test reads the Caddyfiles.** The whole point of the view is that
  the proxy doesn't serve these files; a config change that undid it
  would otherwise pass every test in the suite.
- **The proxy test asserts the ordering, not the strings.** The first
  version only checked that `/media/private/*` and a `respond 404`
  appeared somewhere in each file. That passed against a config which
  served every private photo — see below.

## Review finding — the first fix did not work

Sourcery, reviewing PR #130, said the broad `/media/*` `handle_path`
would run before the `respond @private 404` matcher written above it,
so an existing private file would still be served. I could not settle
that from memory, so I ran it: a real Caddy instance against a copy of
this repo's actual Caddyfile, with the address pointed at a local port,
the roots at a scratch directory holding a planted file, and
`reverse_proxy` pointed at a stub.

**Sourcery was right.** `GET /media/private/photos/secret.jpg` returned
`200` and the file's contents. Caddy sorts directives into its own
order rather than running them top to bottom, and `handle_path` sorts
ahead of `respond`, so the matcher never ran.

Two things were wrong, and the second is the worse one:

1. the config change did not do what it said, so private media stayed
   publicly readable on the deployed host;
2. **the test I wrote to guard it passed anyway**, because it only
   grepped for strings. A test that cannot fail when the thing it
   guards is broken is worse than no test, because it buys confidence
   it has not earned.

The fix is an ordered `handle_path /media/private/* { respond 404 }`
block placed before `handle_path /media/*` in both files. `handle_path`
blocks *are* matched in written order relative to each other, which is
what makes this work where the matcher didn't.

Re-verified against a copy of the real Caddyfile:

| request | result |
| --- | --- |
| private photo | 404, empty body |
| private avatar | 404 |
| `/media/private/../private/x.jpg` | 404 |
| public logo | 200, served |
| any other path | reached the app |

The rewritten test asserts the shape that matters: a `handle_path` for
the private path, before the general one, containing `respond 404` and
no `file_server`. Checked by mutation — restoring the matcher form
makes all three assertions fail; the fixed config passes them.

## Verification

$ `manage.py test` — 801 tests, OK (783 before, 18 new). No migrations:
  the Photo model has existed since Phase 17.
$ Caddy, twice: once proving the original fix broken (200 + file body),
  once proving the current one works (the table above). Both runs used a
  copy of the real Caddyfile, not a simplified reproduction.
$ `caddy validate` on both files — "Valid configuration".
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.

## Git

Branch: `feature/private-media`
Commit: pending
Merged to `main`: pending

## Next

Phase 18 unit 2 — uploading before and after photos from a phone.
