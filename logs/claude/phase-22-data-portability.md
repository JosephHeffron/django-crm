# PHASE 22: DATA PORTABILITY AND BULK OPERATIONS

Started: 2026-10-26
Ended: 2026-10-27

PRs #179 (duplicate detection), #180 (customer search box), #181 (bulk
actions), #182 (CSV import), #184 (CodeRabbit configuration), and this
close-out. No ADR: nothing here changed the architecture.

## The entry, and what was true of it

Four items: *"CSV import/export, bulk actions on list views, saved
filters, duplicate detection on Contact create."* The verification pass
ran before any code, as the last five phases have taught:

| Item | What was true |
|---|---|
| CSV **export** | **Built** (`apps/core/export.py`, eight datasets, Business Settings). Mutation-checked rather than assumed: 5 caught, **2 real gaps** |
| CSV **import** | Not built at all |
| Bulk actions | Not built; no list view had a checkbox |
| Saved filters | Not built |
| Duplicate detection | Not built; `Contact` has no uniqueness constraint, deliberately |

The two export gaps are in #179: its JSON writer and its attachment
header could both be broken with the whole suite green.

## What the owner changed

Two decisions came from the owner mid-phase, and both changed the work:

1. **A search box for the customer dropdown** when creating a job —
   asked for alongside "add all", and built as unit 2 (#180). Not on
   the roadmap; the owner had hit it in use, which is the better
   signal.
2. **Saved filters: not wanted.** Said plainly on 2026-10-27 before
   anything was built. Nothing was removed, so there is nothing for an
   ADR to record; the roadmap entry carries the decision and its date.
   The design that was about to be built is in this session's
   transcript if it is ever wanted: a `SavedFilter` row holding a view
   key plus whitelisted parameter values, never a path, so a saved view
   could not become an open redirect or a way round the page-size
   limit.

## Unit 1 — ask before adding somebody already on the books (#179)

Warns, never blocks, and the tests hold that: every test that asserts a
warning also asserts the save goes through once confirmed. Two people
really do share a name and a couple really do share a phone number, so
a check that refused the second record would be worse than the
occasional duplicate — which is also why `Contact` has no uniqueness
constraint.

Three independent signals: the same first **and** last name (either
alone matches half a book of business), the same email, or the same last
ten digits of a phone number. Deactivated customers are included on
purpose: "you deactivated them last year" is exactly what somebody
re-adding them needs to hear.

## Unit 2 — a search box for the customer dropdown (#180)

The owner's own request. Progressive enhancement in the house style:
the box is server-rendered `hidden` and `static/js/picker.js` unhides
it, so with the script blocked the page is exactly what it was.

**Sourcery found a real bug after CI was green** — the fourth time that
has happened in this project. The box sits *inside* the job form, so
pressing Enter while narrowing the list submitted the form and saved a
half-written job. Fixed, and verified in a browser with a check written
so it could not pass vacuously: the form is filled in **validly**,
Enter must leave the page where it is, and then the same form submitted
on purpose must save. Without that second half, a merely invalid form
would look identical to the fix working.

**One of its four findings was simply wrong**, and worth recording
because it was marked High: that `STATIC_URL` is not root-relative and
no script has ever loaded in production. Django applies the script
prefix, which took one command to show —
`settings.STATIC_URL` is `/static/` and `{% static 'js/lines.js' %}`
returns `/static/js/lines.js`. The same claim would have meant every
stylesheet and script in the app was broken.

## Unit 3 — one action on a page of records (#181)

Tick boxes on the customer and task lists with a bar above them: add or
remove a tag, deactivate, reactivate; mark complete, cancel. Ordinary
POST forms, so it all works with the script blocked —
`static/js/bulk.js` only adds "tick everyone on this page", which is
why that header box is also rendered `hidden` and revealed by script.
Verified both ways in a browser, the second pass with JavaScript
switched off.

Three rules, each the obvious way to get this wrong:

- **The count has to be true.** "Deactivated 20 customers" when 17 were
  already inactive is a lie the owner would act on, so every action
  skips records already in the state asked for and says how many.
- **Only a pending task is touched** — the rule the single-task button
  already enforced. It matters more here: a ticked page of twenty is
  exactly where a cancelled one hides.
- **The same change-log entry the single view writes**, so a bulk
  deactivation stays undoable from that customer's own page and their
  history reads the same whichever way it happened.

`_sync_task_completed_at` and `_apply_task_completion` moved to
`apps/crm/completion.py` and are aliased back under their old private
names — a pure move, as `apps/crm/audit.py` was in Phase 18.5 unit 5 —
so bulk completion goes through the same rule rather than a second copy
of it. That is what makes completing a follow-up from the list still
reset the customer's repeat-service clock.

### Twelve review findings, and what became of them

Seven fixed, four declined, one answered with a caveat:

- **A crafted id was a 500.** `"²".isdigit()` is `True` and `int("²")`
  raises, so `selected=²` crashed the endpoint. The best catch of the
  phase, and not something a human reviewer would have found either.
  `isdecimal()` is the predicate that matches what `int()` accepts.
- **Two Applies at once could both act.** Each write now re-reads its
  rows with `select_for_update()` inside the transaction that changes
  them, ordered by primary key so overlapping requests queue rather
  than deadlock. The likely trigger is not two people but one
  double-click.
- **A completion is stamped with now**, not whatever date the row
  carried; **a bulk tag change writes the customer row too**, because
  the edit form saves tags and the row together; the selection cap is
  reached on ids before any row is materialised; and two test gaps
  (the task checkbox's value, CSRF on both endpoints) were fair.
- **Declined:** acting only on the current page (neither list is
  row-scoped, so an id outside it is not a record the sender could not
  reach); a duplicate follow-up (**impossible** — `Task` has a partial
  unique constraint whose own comment says so); an ADR for the module
  split (`audit.py` set the precedent: docstring and phase log); and a
  test-fixture password, which is the convention in every test module
  here.

**The row lock survived its own mutation**, and that is recorded rather
than smoothed over: removing `select_for_update()` fails no test,
because observing it needs two concurrent transactions and a threaded
test that deadlocked would hang CI rather than fail it. The two
`select_for_update()` call sites already in this codebase have no such
test either. The lock is reasoned, not asserted.

## Unit 4 — saved filters

Not built. The owner said they were not needed before any code existed;
see "What the owner changed" above. The number is kept so the units
match the order they were planned in.

## Unit 5 — a customer list from a spreadsheet (#182)

The other half of Export Data, reading the same column names it writes,
so export → edit in Excel → import back works without renaming
anything. Addresses are the exception: the export writes one formatted
string, which cannot be split back into a street and a town reliably,
so import takes `street`, `city`, `state`, `postal_code` — all four or
none, because `Property` requires all four and nothing in this app
supplies a default for any of them.

Four rules, each a way an import can quietly do damage: it **creates
and never updates**; a bad row is **skipped with its line number**, not
fatal; it is **one transaction**; and it **invents nothing** — an
unfamiliar company or tag is reported and the customer imported without
it, so a typo cannot become a tag on the books forever.

**The export's own guard had to be undone.** `export.py` writes a
leading apostrophe before any cell starting with `=`, `+`, `-` or `@`
so a spreadsheet cannot execute a customer's name. Importing that file
back would have created a customer named `'=Smith`. Stripped only when
a formula character follows, so `'t Hooft` survives.

Nothing is geocoded by an import: placing an address is always an
explicit action (ADR 0011), so imported addresses arrive unplaced and
the report says so.

### The reviewer changed mid-unit

Sourcery's weekly review budget — 250,000 diff characters — ran out, so
#182 had no second reader. The owner had the CodeRabbit extension; the
GitHub app went on, and it **found four issues, all four real**:

- **A refresh could import the file twice.** Measured before it was
  believed, because the duplicate check looked like it already covered
  it: a plain re-post went 1 customer → 1, but with "import them
  anyway" ticked it went 1 → 2. A real import now spends a one-time
  ticket held in the session.
- **The row form was laxer than its column.** A 263-character email
  passed validation and raised `DataError` at the write — inside the
  single transaction that meant one bad row took down the whole file
  with a 500. Fixed with the column's limit, and with a test that
  compares **every** field against its column so the next gap of the
  kind is caught rather than found.
- **`csv.Error` reached the page as a 500.** Reachable well inside the
  2 MB cap, because `csv` refuses any single cell over 128 KB.
- **Business Settings promised more than it did**: "checks the file
  before anything is saved" is only true while the box stays ticked.

On the double-import, one part of the advice was **not** taken, and
said so on the PR: a session ticket does not hold under genuinely
simultaneous posts, which would need a database row to lock. For a page
one person uses once or twice a year, the ticket covers what actually
happens — refresh, back button, a second click — and the limit is
written into the view's docstring instead.

`.coderabbit.yaml` (#184) came out of its first run reporting "No
configuration file from this repository applied". Seven path
instructions now tell a reviewer the things that make correct code here
look wrong: `pk__in` subqueries, the change log being explicit calls
rather than signals, `on_delete` holding only through the ORM, 404 not
403, the CSP, and no script being able to read the CSRF token. Every
key was validated against the live schema.

## Five tests that could not fail for their stated reason

The phase's recurring defect, and every one was mine:

1. **Cancelling clears a completion date** — a pending task has none to
   begin with, so the assertion held however the code behaved. Now it
   plants a stale `completed_at` first.
2. **A byte-order mark** was stripped twice, by `utf-8-sig` *and* by the
   header normaliser, so breaking either left the test green. One
   mechanism now, with a comment saying why the second went.
3. **"An ordinary apostrophe is left alone"** used `O'Pat`, where the
   apostrophe is in the middle — it never exercised the leading-
   apostrophe rule at all. Now `'t Hooft`.
4. **A choice label** was tested with `"Customer"`, which differs from
   `"customer"` only by case, so matching the label looked tested when
   only the value was being matched. Now also `"Yard sign"` →
   `yard_sign`.
5. **The `csv.Error` fix** was half-tested: the regression test put the
   oversized cell on a data row, so the row-loop guard was covering the
   header guard's test too, and deleting the header guard failed
   nothing.

Every one was found by mutation testing, not by reading. The shape is
always the same: **a fixture where two explanations give the same
result.**

## Harness bugs, as usual

- A mutation written as `if value[:1] == "'" or False:` is a no-op —
  the condition is unchanged — so it "survived" and meant nothing. I
  wrote it myself while re-pointing an anchor. Caught by printing the
  mutant text back and reading it before the run, which is the only
  thing that catches this class: the harness cannot tell a no-op from a
  real change.
- The browser pass "failed" because `form button[type=submit]` matched
  the **nav's logout form**, which comes first in the DOM — the same
  trap this harness hit in Phase 19. Selectors are scoped to the form
  under test.

## Verification

```
python manage.py test                     # see below
ruff check . && ruff format --check .
python manage.py makemigrations --check   # no changes: no model changes this phase
```

Test counts as measured, each on its own branch before the others
merged, left as measured rather than back-dated: **1,264** (#179),
**1,297** (#181), **1,345** then **1,354** (#182). Phase 22 added no
migration: duplicate detection, bulk actions and import all work on the
existing schema.

Mutation harnesses: 9 (duplicates), 3 (picker), 19 (bulk actions), 33
(import) — **64 in all**, every one caught except the row lock
described above.

Browser passes under production settings and the real CSP for each
unit, including one with JavaScript disabled, and a report-page check at
390 px. Throwaway records only, removed afterwards and verified gone.

## What is left

- **Saved filters** are not built and not wanted. The roadmap says so
  with the date.
- **The row lock in `apps/crm/bulk.py` has no test.** Reasoned, not
  asserted; see above.
- **`Contact.updated_at` has no reader in the app.** The bulk path now
  writes it for consistency with the edit form, but nothing displays
  it — worth knowing before trusting it as a last-modified figure.
- Importing **does not update** existing customers by email match, and
  deliberately so. If that is ever wanted it is a decision with an ADR,
  not an option on the form.
