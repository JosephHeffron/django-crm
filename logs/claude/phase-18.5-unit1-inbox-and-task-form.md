# Phase 18.5 unit 1 — the inbox, the task form, and name sorting

Phase 18.5 is a set of twelve items the owner reported after testing
the running app. They cut across Phases 18, 19 and 21, so they are
tracked as their own numbered group rather than folded into any of
them. Full plan and unit breakdown: the six-unit sequence recorded in
`docs/PROJECT_STATE.md`'s "Next".

This unit covers items 1, 2, 3 and 5, plus a live security-policy
violation found while working.

## Three of the twelve were not what they looked like

Worth recording, because two of them needed no code at all.

- **"The Deal dropdown is blank."** Not a rendering fault. Phase 17
  folded every Lead and Deal into Contacts and Quotes, so the table
  holds **0 rows against 29 estimates** and the field could only ever
  render `---------`.
- **"Customer names are not alphabetical."** They were already sorted,
  by surname, while being displayed "Daniel Adams" — so the visible
  text read as random first names. The sort was right and the display
  disagreed with it.
- **"The map is not working."** Deferred to unit 4, but diagnosed here:
  the seeded addresses are invented, so `119 Pine Ln, Cedar Hills, NY
  14526` has no real-world referent and OpenStreetMap is correct to
  refuse it. The geocoder works.

## What changed

- `apps/messaging/views.py` — the message list reads newest-first. The
  query already ordered that way and the view reversed it in Python, so
  this is mostly a deletion. Two things moved with it, both load-bearing:
  the `#latest` anchor the send redirect lands on goes on the **first**
  message, and the paging cursor comes from the **last** row on the
  page, because "older than" now means older than the bottom.
- `apps/messaging/templates/messaging/channel.html` — the box to write
  in sits above the messages, "Older messages" below them.
- `apps/crm/forms.py` — `TaskForm` asks for the estimate, not the
  retired deal. New `ContactChoiceField` and `contact_choices()`,
  shared with the job and estimate forms.
- `apps/jobs/forms.py` — `JobForm.contact` and `QuoteForm.contact` use
  it. They were the only two foreign keys left on Django's defaults.
- `apps/crm/templates/crm/task_form.html` — restyled to the house
  pattern. It was still a raw `{{ form.as_p }}` page the Phase 17.5
  restyle skipped.
- `apps/crm/templates/crm/task_detail.html` — the actions row uses
  `.cluster`; the estimate row falls back to a legacy deal.
- Tests: 845 total, 26 new.

## Decisions

- **Swap the form field now, leave the model alone.** Removing Deal is
  Phase 18 unit 5 and pulls in six other call sites plus
  `undo.LIFECYCLE_FIELDS`. The reported bug is a dead form field, and
  the replacement already holds the data. A task that still names a
  deal keeps it, and the detail page still shows it.
- **Display surname first rather than sorting by first name.** Keeps
  households grouped, and standard for a customer list.
- **Hide deactivated customers from new records, keep them on records
  that name one.** Dropping them outright would blank the field and
  make an old job unsavable. Same escape hatch the line formsets use
  for retired services.
- **Ordering stays pk-based.** Unread counts are a pk high-water mark,
  so timestamp ordering would desync from `mark_read`.

## The security fix, and why no sweep caught it

`task_detail.html` carried the project's only inline style attribute.
The production policy sets `style-src 'self' 'nonce-…'` with no
`unsafe-inline`, so it was blocked — the Mark complete button dropped
onto its own line in production and nowhere else.

I had reported a clean 480-page policy sweep earlier in this work. That
was honest but incomplete, and the gap is worth naming: the sweep's
route list held only list and "new" pages, **no detail pages at all**,
and the offending markup sits behind `{% if task.status == "pending" %}`.
So the one state that renders it was never rendered.

Two things now close that:

- `apps/core/tests/test_template_hygiene.py` walks every template and
  fails on an inline style attribute, a `<style>` element, an inline
  `<script>` or an event-handler attribute. `production.py`'s
  "grep-confirmed" claim is enforced rather than asserted in a comment.
- the browser route list leads with a pending task detail page.

## Review — five real findings, and the worst was my own fix

- **The CSS fix did not work.** `.inline-form` already existed further
  down `base.css` with `display: flex`, so the rule I added above it
  never applied. A duplicate class name, and a latent hazard for
  `followup_list.html`, which uses the existing one. Replaced with
  `.cluster`, so there is no new CSS at all.

  And my browser pass had asserted zero policy violations, not layout,
  so an ineffective style change looked clean. That pass now measures
  where the two controls sit. It also caught my own first attempt at
  that check reaching for the sidebar's Log out button instead of this
  one — the same selector trap as earlier in the project.
- **Replacing the Deal row hid the link** on a task naming only a deal,
  contradicting what my commit message claimed. The row falls back now,
  and the test renders the page instead of checking a database field,
  which is what let it through.
- **A task could name one customer and another customer's estimate.**
  Added the guard `JobForm` already applies to addresses.
- **The hygiene patterns were narrower than they looked** — lowercase
  `style="` only, no spaces, double quote only; handlers only when
  quoted; no `<style>` element at all. Widened, and they now have a
  test of their own asserting both what they match and what they
  correctly ignore.
- **One of my tests was vacuous**: the estimate sorting check created a
  single customer, so "sorted" was true whatever the code did.

One finding did not hold: that the form leaks other reps' estimates.
`quotes_for` returns every quote for any sales role by design, like
`contacts_for`, and the form is sales-only. The queryset now goes
through that helper anyway, so the form follows the rule instead of
restating it.

## Verification

$ `manage.py test` — 845 tests, OK (819 before).
$ `ruff` / `ruff format --check` / `makemigrations --check` — clean. No
  migrations: nothing schema-level changed.
$ Browser pass under production settings — 13 pages × 3 roles × 2
  widths, **zero policy violations**, no sideways scroll. Measured in
  the page rather than inferred: the compose box above the list, the
  newest message first with dates descending, `#latest` on the first
  message, customers sorted and reading "Adams, Daniel", no deal field,
  29 estimates offered, and Edit and Mark complete on the same row.
$ Mutation-checked: reinstating the Python reversal, taking the paging
  cursor from the wrong end, reintroducing the inline style, dropping
  the mismatch guard, and hiding the legacy deal each fail named tests.

## Git

Branch: `fix/inbox-order-and-task-form`
Commits: `b7584ce` (the unit), `2e831d9` (the review fixes).
PR: #133. Merged to `main` as `314a09c`.

## Next

Unit 2 — task context and the address filter (items 4 and 8). The Tasks
hub has no customer filter to carry into its "Add task" button, so that
comes first. The address filter must use a `pk__in` subquery, not a
join: joining `properties` multiplies customer rows and corrupts the
paginator count, which looks correct on page one.
