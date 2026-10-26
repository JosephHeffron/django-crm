# 0014 — Retire team messaging (code only, tables kept)

## Context

The owner said on 2026-10-25: *"the entire inbox and messaging page is
no longer needed."*

They are one feature under two names. The sidebar's **Inbox** links to
`messaging:home`, which is the team-chat page: three channels
(`#general`, `#crew`, `#sales`) plus direct messages between users,
built in Phase 17 unit 3d and polished in Phase 18.5 unit 1.

Phase 21's entry asked for short polling, unread badges, and job and
contact references in the composer. The verification pass that preceded
this decision found the badges built and well asserted, the reference
*display* built and asserted, and **nothing in the app able to set a
reference** — the composer is a single body field, so the Django admin
was the only way in. Polling was never started; the module docstring
said so.

So the feature was half-finished and, by the owner's account, not used.
Carrying it means carrying its cost: one unread-count query on **every
page render for every logged-in user** (the context processor), channel
visibility rules duplicated in the customer timeline, and a quarter of
the navigation surface.

## Alternatives considered

- **Finish Phase 21 as written** (polling, composer references).
  Rejected by the owner: the pages are not wanted, so making them
  better is work with no reader.
- **Leave it in place and simply stop building on it.** Rejected: dead
  pages still have to be kept working — they appear in the access
  sweep, the navigation tests, the demo seed and the role bottom bars,
  and every page would still pay for the unread badge.
- **Delete the models, drop the tables.** Rejected, and deliberately
  offered to the owner rather than assumed. Dropping tables is
  irreversible, the install holds real conversations (50 messages, 7
  channels, 28 memberships here), and `docs/ROADMAP.md`'s Phase 24
  (customer texting over SMS) is still planned and builds on exactly
  these models — `Message.transport`, `direction`, `external_id` and
  `delivery_status` exist for it already.
- **Keep past messages on a customer's timeline as read-only text.**
  Offered and declined by the owner. It would have kept roughly half
  the messaging read path alive — including the channel visibility
  rules, which is the part that stops a direct message about a
  customer leaking to someone outside that conversation — to render
  entries that can no longer be opened.

## Decision

**Retire the code, keep the tables**, exactly as ADR 0012 did for Lead
and Deal.

Removed:
- the pages and their routes (`messaging/urls.py`, `views.py`,
  `forms.py`, `templates/messaging/`), and the `include` in
  `config/urls.py`;
- every entrance: the sidebar **Inbox** section, its unread badge, the
  **Inbox** tile in the dashboard's quick actions, the two "Unread
  messages" dashboard cards, and the **Message** button on a person's
  profile;
- the unread count from `apps/core/context_processors.py`, which ran
  for every logged-in user on every page;
- messages from a customer's timeline (`apps/crm/timeline.py`), the
  owner's choice;
- the team-chat half of the demo seed.

- `apps/messaging/services.py` in full, with the page tests
  (`test_views.py`, `test_services.py`). The first draft of this ADR
  kept the channel-visibility helpers on the grounds that Phase 24
  would want the rule. That was the argument this project rejects
  elsewhere: once the pages, the timeline and the seed stopped calling
  them, every function in that module had **no reader**, and dead code
  with a rationale attached is still dead code. The rule it encoded —
  `#sales` is Owner and sales reps, a direct channel is its two
  members, everything else is everyone — is written down here and in
  `docs/PERMISSIONS.md`, and the implementation is one `git show`
  away.

Kept:
- `apps.messaging.models` and every migration, so the tables and their
  rows stay. The app stays in `INSTALLED_APPS` — without it Django
  cannot see the tables and `makemigrations --check` would want to
  delete them. Verified: after this change `makemigrations --check`
  reports no changes, and the install's 7 channels, 50 messages and 28
  memberships are all still there.
- `apps/messaging/tests/test_models.py`, because the models remain.
- The `#general` / `#crew` / `#sales` channels seeded by
  `messaging/0002`. Reference data, still in the table.

The cleaner's phone bottom bar loses its Inbox slot and gains **Time
clock** — the comment above that map says it is "a cleaner's own day",
and clocking in is the thing they do most on a phone.

## Reason

The owner does not use it, and half of it was never finished. Keeping
the tables costs nothing and keeps the only irreversible step off the
table; Phase 24 has something to build on if customer texting is ever
wanted. Everything removed here is a page, a link or a query — all of
it reversible from git.

## Consequences

- **Every page gets one query cheaper** for logged-in users: the
  unread badge was an aggregate over a subquery per channel on every
  render.
- `Message.ref_job`, `ref_contact` and `ref_quote` now have **no
  reader at all**. They stay on the model for Phase 24, and
  `docs/DATABASE_DESIGN.md` says so, so the next person does not
  mistake them for live wiring.
- A customer's timeline loses an entry type. Jobs, quotes, notes and
  logged activities remain.
- `apps/messaging/tests/test_views.py` and `test_services.py` go
  entirely: they test pages and helpers that no longer exist. The
  model tests stay. The suite goes from 1,268 to 1,247.
- **One security assertion loses its subject.**
  `test_direct_messages_only_show_to_members` pinned the rule that
  kept the old timeline safe — a direct message about a customer,
  between two other people, must not appear on that customer's page.
  The leak is now impossible rather than prevented. The dangerous
  fixture is kept and the test rewritten to assert the message stays
  off the page for **everyone**, including a member of the
  conversation, so that a timeline which ever reads `ref_contact`
  again is caught.
- The access sweep's route list shrinks, which its own
  "covers the whole app" assertion will notice — it requires at least
  90 routes, and this removes three.
- Anyone with the Inbox bookmarked gets a 404. No redirect is added:
  there is nowhere to send them.
- `docs/USER_GUIDE.md` loses its Messages section, and the several
  places that mention team chat — the dashboard card list, the
  notifications section, the profile page — need revising with it.
- **Reversing this** is a `git revert` plus `python manage.py
  migrate`, which does nothing because no migration changes. That is
  the point of keeping the tables.

## Date

2026-10-25
