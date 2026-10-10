# Phase 18.5 unit 6 — a Save button at the top of every form

Item 12, and the last of the six.

## What it is

A long form meant scrolling to the bottom to save it. Every record form
now carries a Save button in its page header as well.

The button sits outside the `<form>` element and reaches it through the
HTML `form` attribute. That is the project's first use of that
attribute, and it is the whole reason this needed no JavaScript and no
change to the production Content-Security-Policy: it is plain markup.

- `templates/partials/_save_button.html` (new) — takes `form_id` and an
  optional `label`.
- Fourteen record-form templates: each `<form>` gained an `id`, and
  each header gained a `.page-actions` slot with the include.
- **Nine of the fourteen had no header block at all** — a bare `<h1>`
  inside `.settings-shell` — and gained the existing
  `.page-header`/`.page-actions` pair. No new CSS anywhere.
- Tests: `apps/core/tests/test_save_at_the_top.py`, 13 of them.

## Decisions

- **The HTML `form` attribute, not a moved `<form>` or a sticky bar.**
  Wrapping the header markup inside the form would avoid the `id`, but
  it moves markup on fourteen templates including two with formsets,
  and is ambiguous on any page with more than one form. A sticky bar
  was declined explicitly: the owner asked for a header button that
  scrolls away normally, and the project has only two `position:
  sticky` rules, both structural.
- **Three settings pages are left out**, each hosting several
  independent forms where one header Save could not say which it saves:
  business settings, monthly goals, and the profile page. They are
  *listed* in the test rather than omitted, so the directory sweep
  reports a genuinely new form template instead of silently tolerating
  these three.
- **No shared `_form_actions.html`.** The plan proposed unifying the
  three bottom-row conventions (`.cluster`, `.form-actions`,
  `.section-card-actions`) at the same time. Left alone: it would
  double the diff for no user-visible change, and this unit is already
  wide. The inconsistency is cosmetic and can be its own chore.

## The detail that needed checking rather than assuming

The default submit button — the one the Enter key presses — is the
first in document order whose owner is that form. That is now the
header button on every one of these pages.

It changes nothing observable **only because** no submit button on
these pages carries `name` or `value`, so which one was "pressed"
cannot be told apart by the server.
`test_no_submit_button_carries_a_name` asserts that stays true, because
the day somebody adds a named submit button the ordering has to be
thought about again.

And it was confirmed in a browser, not reasoned about: pressing Enter
in a field still saved the record.

## Verification

$ `manage.py test` — full suite OK.
$ `ruff` / `ruff format --check` / `makemigrations --check` — clean. No
  migrations; this is templates, one partial and one test file.
$ Mutation-checked two ways, and the second is the one worth having:
  removing a header button fails two tests, and **changing the form
  name it points at by one letter** also fails two. A `form=` naming a
  form that does not exist fails completely silently — no error, no
  warning, the button simply never submits — so the id and the
  reference are checked against each other rather than each alone.
$ Browser pass under production settings, fourteen form pages at
  desktop and phone width, zero policy violations and no sideways
  scroll. On every page the button was asserted to be bound to its form
  (`button.form === form`), inside `.page-actions`, above the form and
  within 400px of the top. Then, for real: clicking the header Save on
  a new company saved it, and pressing Enter in a field saved another.
  Both verification records and their log rows were removed afterwards.

## One gap closed by self-review

No automated review: the reviewer's weekly budget went on the seed fix,
which earned it. Reviewing the diff myself found one hole in my own
verification — I had clicked the header Save on a simple card form, not
on the job form with its line-item formset, which is the one case where
a button outside the form could plausibly behave differently.

Checked in a browser: a job saved from the header button kept its line
item at the right quantity and price. The verification job was removed
afterwards.

## Git

Branch: `feature/save-at-the-top`

Two process notes, both mine. This work was first made on unit 5's
branch and then branched from unit 5 rather than from `main`, which
would have put unit 5's commit inside this pull request; both were
corrected before anything was committed. And the first version of the
test file was lost to a `cat >` with no heredoc attached, which
silently swallowed its own input and hung for eight minutes — the
rewrite is longer than the original.

## Next

Phase 18.5 is complete: all twelve reported items are done. Phase 18
units 2 to 5 remain (photo upload and display, accepted estimate to
job, calendar drag-to-reschedule, and removing the retired Lead and
Deal models).
