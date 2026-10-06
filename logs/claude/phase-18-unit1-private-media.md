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
- Tests: `apps/jobs/tests/test_private_media.py` (16) — signed out,
  the crew member on the job, a crew member on a different job, the
  Owner, no role, an unknown photo, a missing file, an estimate photo,
  the headers, that the stored name is the UUID and never the uploaded
  filename, avatars, and **that both Caddyfiles still refuse the path**.

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

## Verification

$ `manage.py test` — 799 tests, OK (783 before, 16 new). No migrations:
  the Photo model has existed since Phase 17.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.

## Git

Branch: `feature/private-media`
Commit: pending
Merged to `main`: pending

## Next

Phase 18 unit 2 — uploading before and after photos from a phone.
