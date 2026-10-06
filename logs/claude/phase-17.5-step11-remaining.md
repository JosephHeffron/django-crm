# PHASE 17.5 STEP 11: THE REST, AND A RESPONSIVE PASS

Started: 2026-10-06
Ended: 2026-10-06

## Objective

The last step of the restyle: bring the pages the earlier steps didn't
touch up to the same standard, and sweep every page at phone and desktop
width, in both themes, as each role, to find what's actually broken
rather than what looks suspicious.

## The sweep

A script walks 40 routes as the Owner, a Sales Rep and a Cleaner, in
light and dark, at 390px and 1920px — **480 page loads** — and fails on
horizontal overflow, a missing heading, an unexpected status, a console
error or a CSP violation.

It found **one real defect**: the Activities page overflowed a phone by
119px, for the Owner and Sales Reps, in both themes. That page had never
been restyled — a bare table with no mobile handling, hand-rolled
pagination, a plain link for its action, and "No activities found." for
an empty state.

After the fixes the sweep is clean: **480 pages, zero problems**.

## Files changed

- `apps/crm/templates/crm/activity_list.html` — rebuilt: the shared page
  header with a real action button, a table that stacks on a phone with
  a label per cell, the shared pagination, and an empty state. This is
  the page the sweep caught.
- `apps/crm/templates/crm/company_list.html` — the same treatment; it
  had the same hand-rolled pagination and label-less table, and was one
  narrow column away from the same bug.
- `apps/crm/views.py` — both list views gain `PerPageMixin`, so their
  pagination matches every other list.
- Eight templates with a stray `<h1>` (search, company detail and form,
  activity form, task detail and form, both deactivate confirmations)
  now use the shared heading block.
- `static/css/base.css` — **`.page-header` and `.dash-hero` are now one
  rule**. They were near-duplicates that had drifted a couple of pixels
  apart, which is exactly the sort of difference nobody can name but
  everybody sees. Same for their action rows. Sixteen templates keep
  whichever class they had.
- Two tests updated for the new empty-state wording.

## Decisions

- **Four wide tables keep horizontal scroll rather than stacking.**
  `stack-mobile` reads each cell's `data-label`; those tables have none,
  so stacking them would have shown values with nothing saying what they
  were — worse than scrolling. They're already inside a scroll wrapper
  and the sweep found no overflow.
- **Lead and Deal pages were left alone.** Both models are removed in
  Phase 18, so restyling them is work that gets deleted. They render and
  don't overflow.
- **Unify the CSS rather than edit sixteen templates.** Same result,
  almost no risk.

## Verification

$ `manage.py test` — 783 tests, OK. No migrations.
$ `ruff` / `ruff format --check` / bandit (CI flags) /
  `makemigrations --check` — clean.
$ Playwright under production settings: 480 page loads (40 routes × 3
  roles × 2 themes × 2 widths), zero overflow, zero CSP violations, zero
  console errors, every page with a heading.

## Review (PR #127)

Sourcery reviewed step 10's code on this branch (step 11 was stacked on
it) and found nine issues. All nine were real; all are fixed here, each
with a test. Two of them were the kind that costs data or locks a person
out:

1. **(Critical) Undo could overwrite a newer edit.** It compared the
   record it had fetched earlier, then wrote inside a transaction — a
   gap an edit could land in and be lost, which is the one outcome undo
   exists to avoid. The row is now locked and re-read inside the
   transaction before anything is compared.
2. **(High) Turning off someone's sign-in was a one-way door.** The team
   list and the member page both filtered to active users, so the person
   vanished from the only page that could turn it back on. Both now
   include them, marked.
3. **(High) An Owner could take away their own access.** The GET
   redirects you to your own profile; the POST didn't, so you could
   strip your own role with no way back in.
4. **(High) Undo of a lifecycle field would have lied.** Putting a
   lead's status back to "qualified" would say the conversion never
   happened while the contact, company and quote it created still
   exist. Those fields are now refused by name, with the reason.
5. **(High) Two owners saving a role at once** could leave somebody
   holding two, and **(Medium)** a failure between the two writes could
   leave half a change. Both are now one transaction with the row
   locked.
6. **(Medium) Undo left a stale "updated" time** — `auto_now` only fires
   when the field is in `update_fields`.
7. **(Medium) The activity log fetched one record per row** to ask
   whether it could be undone; the generic relation is prefetched now.
8. **(Medium) A changelog note that wrapped lost everything after its
   first line.**

## Git

Branch: `feature/restyle-remaining` (PR #127)
Commits: the step, plus the review fixes above
Merged to `main`: pending

## Next

Phase 17.5 is complete. Phase 18 — quotes and jobs workflow — picks up
what the restyle deliberately left: turning an accepted estimate into a
job in one click, and drag-to-reschedule with a keyboard alternative.
