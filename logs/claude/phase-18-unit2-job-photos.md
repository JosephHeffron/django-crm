# PHASE 18 UNIT 2: JOB AND ESTIMATE PHOTOS

Started: 2026-10-08
Ended: 2026-10-08

(Written during the Phase 18 close-out, from PR #148 and the commit.
Unit 2 merged without its own log at the time.)

## Objective

Unit 1 built the serving side — a login-gated view that checks whether
you may see the job a photo belongs to — and nothing uploaded or
displayed one. This adds before/after photos on a job and reference
photos on an estimate, through a file input carrying `capture`, which
opens the camera on a phone and is ignored on a desktop.

## The part that is not about uploading

Every photo is decoded and re-encoded before storage, so what is kept
is a JPEG this code produced and **never the bytes the phone sent**.

That strips the GPS coordinates a phone writes into a photo of a
customer's house — their home address, in a file staff can open.
**ADR 0009 promised that stripping and nothing had implemented it.**

Orientation is applied first, because which way up the photo goes lives
in the metadata about to be discarded. The long edge is capped at
2000px: a Raspberry Pi serving these off an SD card does not want 12MB
originals.

Measured on a real upload: 3200×2400 with metadata became 2000×1500
with none.

## Files created / changed

- `apps/jobs/photos.py` — `process_photo()`. Size ceiling, format
  allowlist (JPEG/PNG/WEBP), pixel-bomb ceiling, HEIC refused by name
  and by detected format, then re-encode.
- The job and estimate pages, the upload and removal views, and the
  change-log calls for both.

## HEIC

Refused, with a sentence naming the iPhone setting to change. No
`pillow-heif`: iOS normally hands web uploads over as JPEG, and the
alternative is a new dependency shipping to the Pi to cover a case that
rarely arrives.

**That needed a correction I had not expected.** Django's form
`ImageField` validates with Pillow *before* any `clean_image` runs, and
answers a HEIC with "Upload a valid image. The file you uploaded was
either not an image or a corrupted image." That is wrong — it is a
perfectly good photograph — and it made the message in `photos.py`
unreachable. The form takes a plain `FileField` now so `process_photo`
owns validation; it already checked more than `ImageField` does.

## Removing

Whoever added a photo can remove it, and so can the Owner. The file
goes with the row rather than lingering, which is why this is a real
delete and not the `is_active` flag used for customers.

Another crew member on the same job cannot remove it, and somebody who
cannot see the job gets a **404 rather than a 403**, so they do not
learn the photo exists. Both adding and removing are recorded in the
change log.

## Verification

| check | result |
| --- | --- |
| Full suite | 1034 pass, 33 new |
| Browser pass under production settings, job and estimate pages, two widths | zero policy violations, no sideways scroll |
| A real 3200×2400 upload at phone width | stored 2000×1500, served through the gated view, caption shown |
| The file input | asks for the camera (`capture="environment"`) |
| A crew member not on the job fetching the image | 404 |
| Removing | cleared the tile and the file |

Mutation-checked on the three that fail silently: carrying the original
metadata through fails two tests, skipping the downscale fails one,
dropping the removal permission fails one. The first matters most,
because a photo quietly keeping a customer's coordinates looks
identical on every page.

No migrations: the `Photo` model has existed since Phase 17.

## Commit

PR #148.
