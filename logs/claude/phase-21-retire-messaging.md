# PHASE 21: PWA POLISH — AND MESSAGING RETIRED INSTEAD

Started: 2026-10-25
Ended: 2026-10-25

PR #176 and this close-out.
ADR: `docs/decisions/0014-retire-team-messaging-code-only.md`.

## The verification pass, before any code

Five items in the entry. Measured rather than assumed, as the last four
phases taught:

| Item | What was true |
|---|---|
| Short polling for new messages | **Not built.** `apps/messaging/views.py`'s own docstring said *"Automatic updates (short polling) arrive in Phase 21."* |
| Unread badges | **Built, well asserted.** Four mutations — counting read messages, counting your own, counting channels you cannot read, and never moving the read marker — all caught. |
| Job/contact references in the composer | **Half built.** `Message.ref_job`/`ref_contact`/`ref_quote` existed and the *display* was real and tested. **Nothing in the app could set one**: the composer was a single `body` field, so the Django admin was the only way in. |
| Offline fallback | **Built**, three behaviours unasserted (below). |
| Install experience | **Built, asserted** — manifest fields, icons present on disk, brand, CSP allowances. |

11 mutations: 7 caught first time, 1 was a no-op of my own, 3 found
real gaps.

## The three PWA gaps, and why the tests missed them

Each existing test was close enough to look like cover:

- `test_precaches_the_shell_and_offline_page` asserted the
  `OFFLINE_URL` **constant exists** and that `PRECACHE` matched the
  list. Neither says the offline page is put *in* the cache — so
  dropping it from `cache.addAll` left the whole suite green and the
  app with **no offline fallback at all**, which is the one thing a
  service worker is for.
- `test_version_is_a_stable_content_hash` and
  `test_brand_change_rolls_the_cache` test `pwa.asset_version()`
  itself. Nothing checked that the cache **name** uses it, so pinning
  the name to a constant passed — and a stale shell would survive
  every deploy.
- Nothing asserted the `activate` handler's cleanup, so neutering the
  filter passed and a device would accumulate one cache per release.

All three are guarded, each by the test written for it.

## Then the phase changed

The owner said the inbox and messaging pages were no longer needed.
That makes the first three items moot: there is no composer to add
references to and no page to poll.

Two decisions were put to the owner rather than assumed, because they
change what gets built:

1. **Past messages on a customer's timeline** — removed with the
   feature. An entry that cannot be opened is a dead end, and keeping
   them meant keeping the channel-visibility rules alive to render
   them safely.
2. **Phase 24 (customer texting)** — stays planned, tables kept. The
   third option offered was deleting the models and dropping the
   tables; it was offered explicitly rather than assumed away, and
   declined.

## Retired code-only, tables kept

The shape ADR 0012 used for Lead and Deal. Removed: the pages and
routes, the sidebar **Inbox** section, the unread badge, the Inbox
quick-action tile, both "Unread messages" dashboard cards, the
**Message** button on a profile, the timeline entries,
`apps/messaging/services.py`, and the team-chat half of the demo seed.

Kept: `models.py`, every migration, the three channels seeded by
`messaging/0002`, and `test_models.py`.

Verified rather than asserted: after the change `makemigrations
--check` reports no changes, and the install's **7 channels, 50
messages and 28 memberships** are all still there.

**Every page is one query cheaper** for logged-in users. The unread
badge was an aggregate over a per-channel subquery, run by the context
processor on every render.

A cleaner's phone bottom bar gained **Time clock** where the Inbox was.
The map's own comment calls that bar "a cleaner's own day", and
clocking in is what they do most on a phone.

## I contradicted my own ADR, on purpose

The ADR's first draft kept `services.py`'s channel-visibility helpers
"because Phase 24 needs that rule". Once the pages, the timeline and
the seed stopped calling them, **every function in the module had no
reader** — and "a later phase might want this" is exactly the argument
this project rejects elsewhere, because git holds it.

So the module went, the rule it encoded is written into
`docs/PERMISSIONS.md` and the ADR in prose, and the ADR records the
change of mind rather than quietly reflecting the outcome. A decision
record that hides a reversal is worth less than one that shows it.

## A security assertion that lost its subject

`test_direct_messages_only_show_to_members` pinned the rule that made
the old timeline safe: a direct message about a customer, between two
other people, must not appear on that customer's page. It asserted the
other half too — that a member of the conversation *did* see it.

With messages out of the timeline the leak is **impossible rather than
prevented**, and the second half has no behaviour left to assert.
Deleting the test would have thrown away the useful part: its
dangerous fixture. It is now
`test_no_message_reaches_a_customer_page_whoever_wrote_it`, keeping the
DM-about-a-customer fixture and asserting the message stays off the
page for **everyone**, a member of the conversation included. If the
timeline ever reads `ref_contact` again, that is what notices.

## Ten tests encoded the removed feature

Named, because an inventory that does not add up is worse than none —
the first version of this list said "three" sidebar tests and then
counted the sidebar count guard again, giving twelve items for ten
failures:

1. `test_sales_rep` — the sidebar's link list
2. `test_cleaner_and_no_role` — the same, for a cleaner
3. `test_owner` — the owner's sidebar **count** guard (21 now, was 22)
4. `test_bottom_bar_per_role` — the cleaner's phone bar
5. `test_a_cleaner_gets_their_own_cards_and_no_money` — card labels
6. `test_quick_action_tiles_only_point_where_the_role_may_go`
7. `test_owner_sees_a_teammates_stats_and_own_page_redirects` — the
   profile's Message button
8. `test_populates_every_area_with_real_data` — the seed's team-chat
   assertions (its module also failed to import, since it pulled
   `direct_channel` from the deleted `services.py`)
9. `test_timeline_merges_every_kind_newest_first`
10. `test_direct_messages_only_show_to_members`

All rewritten rather than deleted where there was
still something true to assert — the seed test now asserts the
**absence** of messages and the presence of the three reference
channels, because a seed that quietly started filling an unreachable
table again is worth knowing about.

## Verification

```
python manage.py test        # 1,247 pass (1,268 before; the page tests
                             # went with the pages)
ruff check . && ruff format --check .
python manage.py makemigrations --check   # no changes: tables untouched
pre-commit run --all-files   # 10 hooks
```

Mutation-checked: the timeline reading `ref_contact` again, the seed
creating team chat again, and the cleaner's bottom bar losing its
fourth item — all caught.

## What is left

- Anyone with the Inbox bookmarked gets a 404. No redirect: there is
  nowhere to send them.
- `Message.ref_job`, `ref_contact` and `ref_quote` have **no reader
  in the application**; `MessageAdmin.raw_id_fields` still exposes
  them, so the Django admin is the one remaining way in. They stay for
  Phase 24; `docs/DATABASE_DESIGN.md` says so, so they are not
  mistaken for live wiring.
- Phase 24 (customer texting over SMS) still stands. `transport`,
  `direction`, `external_id` and `delivery_status` were added for it
  and are still on the model.
