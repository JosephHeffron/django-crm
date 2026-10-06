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
  filename, avatars, that a storage fault is not disguised as a
  missing photo, and **that both Caddyfiles still refuse the path
  — asserted against `caddy adapt`, the configuration Caddy actually
  runs, not the text of the file** (see the two review findings below
  for why that distinction cost three attempts).

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
- **The proxy test asserts the adapted config, not the file's text.**
  Two earlier versions searched the text and were both worthless: the
  first passed while every private photo was served, and the second
  would have passed with the block commented out. Worth a pinned
  binary in CI because this is the one control between a customer's
  job photos and anyone with the URL.

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

The fix is a `handle_path /media/private/* { respond 404 }` block in
both files.

**And the reason I first gave for why that works was also wrong.** I
wrote that `handle_path` blocks match in written order. They don't:
`caddy adapt` on the real file shows `/media/private/*` sorted ahead of
`/static/*`, which is not where it sits in the file. Tested directly by
moving the private block *below* `handle_path /media/*` and adapting
again — it still came out first. Caddy orders handle/handle_path blocks
by **path specificity**, so the longer, more specific path wins
wherever it is written. The code comments in both Caddyfiles now say
that, and say not to rely on their position in the file.

Re-verified against a copy of the real Caddyfile:

| request | result |
| --- | --- |
| private photo | 404, empty body |
| private avatar | 404 |
| `/media/private/../private/x.jpg` | 404 |
| public logo | 200, served |
| any other path | reached the app |

## Review finding, second round — the rewritten test was still weak

Sourcery then pointed out that the rewritten test still only searched
the file's text, so **commenting the block out would leave the text in
place and pass every assertion** while the general handler served
private media. Correct, and it is the same error a third time: reading
intent instead of behaviour.

The guards now run `caddy adapt` and assert on the configuration Caddy
will actually use — route order, and that the private route ends in a
`static_response` with no `file_server` or `reverse_proxy`. A
commented-out block simply isn't in that output. A comment-stripping
text check stays as a weaker guard that needs no binary, and the
stripper has its own test.

Mutation-checked, four ways the control could break:

| mutation | result |
| --- | --- |
| the original `respond` matcher form | fails |
| the block commented out | fails |
| the block deleted | fails |
| the block serving files instead of answering | fails |
| the real config | passes |

**Skipping is the remaining hole**, since the strong guards need the
`caddy` binary. CI now installs it (pinned 2.11.7, SHA-512 verified,
same approach as `static/vendor/leaflet/`), and a test fails when `CI`
is set but the binary is absent — so a broken install is loud instead
of three quiet skips. Verified by running the suite with `CI=1` and
Caddy removed from `PATH`: it fails with "CI must install caddy or the
proxy guards do not run".

Sourcery's second, medium finding was also right: two success tests
asserted only a 200, so an empty response would have passed as photo
delivery. They now assert the JPEG bytes, via one helper so a bare
status check doesn't creep back. Mutation-checked by making the view
return an empty body — four tests fail where two used to pass.

## Review finding, third round — a broken volume looked like a missing photo

`send_private_file` caught `OSError` and returned 404. Sourcery pointed
out that this covers permission errors and I/O errors, so a
misconfigured media volume would show every photo as "not found" to
every user, with nothing in the logs saying otherwise. Only
`FileNotFoundError` means the file is genuinely gone; the rest are
server faults and now propagate, so they're a 500 and get recorded.

**Correction, from a later round:** I first wrote that this also covers
"a volume that isn't mounted". It doesn't. An unmounted or
empty-mounted volume raises `FileNotFoundError`, because `ENOENT` is
exactly what the filesystem reports, so it is indistinguishable from a
deleted file at this level and still returns 404. The comment in
`media.py`, the changelog entry and this log were corrected to say so.

**And then closed, in PR #132.** The distinction that actually matters
isn't the error number, it's one file versus all of them: if the
*directory* the photos live in doesn't exist, the volume is unmounted
or mounted empty and every private file is about to return 404, which
is a server fault. So a missing directory raises and a missing file
returns 404 and is logged.

Review caught one more thing on that fix, and it was right: asking
`storage.exists()` for the parent "directory" is meaningless on object
storage, which has no directories and answers no for every prefix — so
on such a backend **every** missing photo would have become a 500. The
check is now gated on the storage having a real local path
(`storage.path()`, which object storage answers with
`NotImplementedError`), which is also the only kind of storage that can
have an unmounted volume in the first place. Anything that can't be
asked gets the benefit of the doubt.

Mutation-checked both ways: removing the directory check fails the
unmounted-volume test, and going back to `storage.exists()` fails the
object-storage tests with exactly the 500 the review predicted.

Two notes on the tests, since both were mistakes of the same family as
the Caddy ones:

- one was hollow as first written — it left the file in place, so
  `open()` succeeded and the check never ran. It deletes the file
  first now;
- the object-storage case was first written by patching
  `storage.path`, which also broke `storage.open`, so the test failed
  for the wrong reason. It uses a small fake `Storage` instead, which
  is closer to the thing being described.
  The unmounted-volume case needs no mock at all: it removes the real
  directory under `MEDIA_ROOT`.

Mutation-checked: restoring the broad `except OSError` fails the two
new tests (a permission error and a read error).

## Review finding, fourth round — two of three were wrong

Worth recording that review is not always right, and that checking is
cheap either way:

- **"Avatar requests fail with a server error"** (High) — claimed
  `AvatarView` references an undefined `User`. It doesn't:
  `apps/users/views.py:29` binds `User = get_user_model()` at module
  level, and the avatar tests fetch a real picture and assert its JPEG
  bytes. No change.
- **"Private images download instead of display"** (Medium) — claimed
  `content_type=None` yields `application/octet-stream`. It doesn't:
  `FileResponse` guesses from the stored filename and the response
  really carried `image/jpeg` (printed it to be sure). But a follow-up
  round sharpened this into something real, below.
- **"Storage read errors truncate images"** (Medium) — true, and
  accepted. `FileResponse` streams, so a read error after the headers
  are out truncates the body rather than becoming a 500. Reading the
  file into memory first narrows that window without closing it, and
  costs memory on every request to catch a disk fault that `open()`
  already catches in the common cases. `Content-Length` is sent, so a
  short body is detectable rather than silently wrong, and a test
  asserts it matches the body. The module docstring records both
  limits and why.

## Review finding, fifth round — the content type came from the host

Sourcery's HEIC variant of the content-type point is the one that
actually bites, and it changed my mind. `FileResponse` guesses via
`mimetypes`, which reads the **host's** MIME database. That differs
between this Fedora workstation, the Ubuntu CI runner and the Pi — and
with `nosniff`, the type we send is the type the browser uses. So the
same photo could display on one machine and download on another, for
no reason visible in the code.

`ALLOWED_PHOTO_SUFFIXES` does permit `.heic`, so that path is
reachable, not hypothetical.

`media.py` now decides the type itself from a small explicit map, and a
test asserts the answer doesn't change when `mimetypes.types_map` is
emptied. Mutation-checked: going back to letting `FileResponse` guess
fails that test — and *only* that test, because this host happens to
know `.heic`, which is the whole point.

One test ties `CONTENT_TYPES` to `ALLOWED_PHOTO_SUFFIXES`, so adding an
upload format without adding its type fails rather than quietly serving
`application/octet-stream`.

**For unit 2 (phone uploads):** Pillow 12.3.0 here has no HEIF support
registered, so an `ImageField` form upload of a HEIC file is rejected
at validation — only `objects.create()` can store one. iPhones shoot
HEIC by default. Unit 2 has to decide between relying on iOS converting
to JPEG on upload (which Safari generally does for file inputs) and
adding `pillow-heif`, a new dependency that CLAUDE.md requires be
justified. Also note most desktop browsers can't render HEIC even when
correctly labelled, so storing it unconverted would hurt the Owner
viewing photos on a laptop. Recorded here so it isn't discovered late.

The repeat of the streaming-truncation point is answered on the PR and
unchanged: accepted, with the reasoning recorded.

## Verification

$ `manage.py test` — 819 tests, OK (783 before, 36 new). No migrations:
  the Photo model has existed since Phase 17.
$ Caddy, twice: once proving the original fix broken (200 + file body),
  once proving the current one works (the table above). Both runs used a
  copy of the real Caddyfile, not a simplified reproduction.
$ `caddy validate` on both files — "Valid configuration".
$ `CI=1` with Caddy off `PATH` — fails, as intended.
$ Browser check under production settings (Playwright, Chromium,
  synthetic photos on a demo job, sessions minted rather than using any
  real password):

| as | result |
| --- | --- |
| the crew member assigned to the job | 200, `image/jpeg`, 9,987 bytes |
| a crew member not on the job | 404 |
| the Owner | 200, `image/jpeg` |
| signed out | 302 to sign-in |
| a teammate on an avatar | 200 |
| `/media/private/photos/<uuid>.jpg` directly | 404 |

  Both the photo and the avatar render at their real 900×600 in an
  `<img>` on an ordinary app page, with **zero** CSP violations — the
  way unit 2 will show them. Headers as intended: `inline`, `nosniff`,
  `private, max-age=0, no-store`, `same-origin`.

  One thing worth knowing: *navigating straight to a photo URL* does
  log CSP violations, six of them. They come from Chromium's own
  image-viewer document, which our response's CSP header also applies
  to, so its inline styles are blocked. The image still displays; only
  the viewer's own background styling is lost. Not changed — dropping
  CSP from media responses to tidy up a browser's internal page would
  weaken a real defence for nothing. Recorded so it isn't mistaken for
  a regression later.

  The synthetic photos, the avatar and the minted sessions were removed
  afterwards; the dev database is as it was.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.

## Git

Branch: `feature/private-media`
Commits: `465db96` (the view and the first, broken proxy fix),
`66408fa` (the proxy fix that works), `2e2692c` (assert the adapted
config; Caddy in CI), `6045eac` (storage faults surface),
`626cdc2` + `804e6d2` (content-type tests), `51b601a` (decide the
content type here), `c552a61` (browser verification).
PR: #130. Merged to `main` as `958fa6b`.

## Next

Phase 18 unit 2 — uploading before and after photos from a phone.
Nothing displays photos yet; this unit built only the serving side.
Read the HEIC note under the fifth review round first: Pillow here
can't open HEIC, iPhones shoot it by default, and most desktop browsers
can't render it even when labelled right. That's a dependency decision
for unit 2, not a detail.
