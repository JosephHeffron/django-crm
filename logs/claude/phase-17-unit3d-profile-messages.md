# PHASE 17 UNIT 3D: PROFILE AND MESSAGES

Started: 2026-09-29
Ended: 2026-09-29

## Objective

Last PR of Phase 17: Messages (team channels, direct messages, unread
counts, channel access by role) and Profile (stats per role, self-edit,
the Owner's team view). Completes "every page visible on seeded data".

## Files created / changed

- `apps/messaging/models.py` + migration `0003_channel_audience` —
  `Channel.audience` (everyone / sales); #sales becomes sales-only.
  Reversible (verified: unapply → reapply on the dev database).
- `apps/messaging/services.py` — `visible_channels()` (public by
  audience, direct by membership, archived excluded) is the single
  rule for lists, counts, pages, and the contact timeline;
  `channels_for()` (per-channel unread and last message as
  subqueries); `unread_count()` (the sum of the same per-channel
  figures, so badge and list agree); `mark_read()` (forward-only);
  `direct_channel()` (one channel per pair, `dm-<low>-<high>`,
  race-safe); `channel_title()`.
- `apps/messaging/views.py`, `forms.py`, `urls.py`, templates —
  `/messages/`, `/messages/c/<slug>/` (latest 50, older via
  `?before=`, post by form, opening marks read, job references linked
  only for people who can open the job, contact/quote references for
  sales roles), `/messages/dm/<username>/` (teammates with a role, not
  yourself). Unreadable channel → 404.
- `apps/users/stats.py`, `views.py`, `forms.py`, `profile_urls.py`,
  templates — `/profile/` (crew and/or sales stats over 30/90/365
  days), `/profile/edit/` (name, email, title, phone, calendar color),
  `/team/` and `/team/<username>/` (Owner). `roles.roles_for()` — many
  users' roles in one query (team list). Tone choices shared with the
  service form.
- Navigation — Messages (unread badge, "99+" cap, screen-reader text)
  and Profile for every role; bottom-bar items now per role (Cleaner:
  Dashboard, Calendar, Messages, Profile).
- `apps/crm/timeline.py` — uses `visible_channels()`.
- `seed_demo` — joins people only to channels they can read, creates
  DMs through `direct_channel()` (opening one in the app no longer
  starts a duplicate), message timestamps now follow posting order;
  reset removes DMs involving demo users.
- Docs: `docs/USER_GUIDE.md` (Messages, Profile and team, Cleaner's
  bottom bar), `docs/PERMISSIONS.md` (page rows, messaging rules),
  `docs/DATABASE_DESIGN.md` (audience, DM slug).
- Tests: `apps/messaging/tests/test_views.py`, `test_services.py`
  (updated for the audience rule), `apps/users/tests/test_profile.py`,
  navigation and seed tests updated.

## Decisions

- **Audience as a field**, not a hard-coded slug list — the Owner can
  make more channels later (admin) with the right audience.
- **Unopened channels count in full** toward unread (consistent
  everywhere; the badge caps at 99+).
- **Direct messages are private to their members, the Owner
  included.**
- A DM link creates the channel on first GET — idempotent (one per
  pair), so harmless as a link.
- Photo upload for profiles waits for the gated media view (Phase 18).

## Verification

$ `manage.py test` — 493 tests, OK (25 net new); 494 after the
  self-review's regression test.
$ `ruff` / `ruff format --check` / `bandit` (CI flags) /
  `makemigrations --check` — clean.
$ Dev database migrated and re-seeded; migration unapplied and
  reapplied cleanly.
$ Playwright: Owner, Sales Rep, Cleaner × phone and desktop × 10
  routes (messages home, three channels, a new DM, profile, 365-day
  profile, edit, team, a teammate) — Cleaner 404 on #sales, 403 on
  team pages; Sales Rep 403 on team pages. Under production settings:
  all checks passed, zero CSP violations. Screenshots reviewed.

## Errors

- A mixed-type `Coalesce` (FK id vs integer) 500'd the Messages page —
  explicit `output_field`.
- The unread badge counted only opened channels while the list counted
  unopened ones in full — `unread_count()` now sums the list's figures.
- Screenshot review: two "Jordan Price" DMs (the seed used its own
  slug format, so the app started a second channel) and out-of-order
  message times (the seed back-dated randomly) — both fixed in the
  seed, with regression assertions; "Sales Rep · Sales Rep" when a
  title equals the role — fixed, tested.
- The dev-server run flagged horizontal overflow on a Cleaner's #sales
  404 — that was Django's DEBUG technical 404 page; the real 404 page
  passes under production settings.

## Review

Sourcery skipped PR #104 (weekly budget exhausted), so a self-review of
the full diff. One defect, fixed in a follow-up commit on the PR with a
regression test that fails on the old code:

- The "people you can message" list only included members of a role
  group, but a superuser counts as Owner without one — so a superuser
  owner (the typical first account) couldn't be sent a direct message.
  Superusers are now included.

Also checked: every messaging entry point goes through
`visible_channels()` (archived and unreadable channels 404, including
on POST); anonymous → login and no-role → 403 before any channel
lookup; the per-page unread count ignores the list's prefetch;
profile editing is limited to the signed-in user; seed reset deletes
DMs involving demo users (documented).

## Git

Branch: `feature/profile-messages`
Commits: `dce2220` (feature), `12c411a` (self-review fix)
Merged to `main`: PR #104, merge commit `2ccc192`

## Next

Phase 17 close-out (PROJECT_STATE, CHANGELOG — Phase 17 is a meaningful
release), then Phase 18 — quotes and jobs workflow.
