# PHASE 19 UNIT 3: NOTES

Started: 2026-10-12
Ended: 2026-10-12

## Objective

`NoteListView`'s docstring said "Adding and editing notes lands in
Phase 19" and the Django admin was the only way to write one. No
migration: `Note` has existed since Phase 17.

Two audiences, deliberately different.

## Sales and the owner, from the Tasks hub

An ordinary form — general, or about a customer or a job, with a pin.
Editing returns to the filtered list it came from, `next` validated
against this host so it cannot become an open redirect.

## A crew member, from the job they are standing at

The substantive half, and it closes a promise unkept since Phase 17.
`users/0004_field_service_permissions` grants cleaners `add_note` with
this comment:

> Crews update their own jobs (status, hours) and add photos/notes —
> **which jobs is enforced row-by-row in the views**.

The view that enforces it was never built. **A crew member has held
that permission for two phases and could reach no note interface at
all.** A granted-but-unreachable permission is invisible until somebody
goes looking; recorded in `docs/PERMISSIONS.md` so the next one is
easier to spot.

`JobNoteCreateView` is that view: POST-only, scoped through `jobs_for`,
so a crew member can note a job they are on and gets a **404, not a
403**, for one they are not. The note attaches to the **job, never the
customer** — a note about today's work is not a note on someone's
permanent record.

## The visibility decision

The owner chose that a crew member on a job sees notes about the
**customer** as well as the job: the more useful view at the house, and
the less private one. Asserted in both directions.

| | Crew member on the job |
|---|---|
| Notes about that job | visible |
| Notes about that customer | **visible** |
| Any other note | not shown |
| The notes list (every customer) | 403 |
| Editing a note, even their own | 403 |

Editing is refused because `add_note` is all they hold: they can leave
a note and cannot go back and change what it said.

**The mitigation matters more than the feature.** That choice makes a
rep's customer notes field-visible, and a rep writing one had no way to
know. `NoteForm` now says so on the form itself — "Crews working at
this customer's address can read notes about them, so keep commercial
detail out of these" — asserted in a test and confirmed rendered in a
browser. A hidden consequence became an informed one.

Customer notes are badged "about the customer" on the job page, so it
is clear which are about today's work.

## The same trap as unit 2

`Note` had no `get_absolute_url`, and the change log renders
`record.get_absolute_url` for every entry. Django resolves a missing
template attribute to the empty string silently, so recording notes
would have produced links that go nowhere. It now resolves to the job,
the customer, or the list, with three assertions for the three
branches.

**Both sweeps were updated before running this time**, not after the
full suite caught them — unit 2's lesson.

## Files created / changed

- `apps/crm/forms.py` — `NoteForm`, `JobNoteForm`.
- `apps/crm/views.py` — `NoteFormMixin`, create/update.
- `apps/jobs/views.py` — `JobNoteCreateView`; `JobDetailView` widened
  to job **and** customer notes.
- `apps/crm/models.py` — `Note.get_absolute_url`.
- `apps/crm/templates/crm/note_form.html` (new), `note_list.html`,
  `jobs/job_detail.html`.
- `apps/crm/tests/test_notes.py` (29).

## A latent flake CI found, unrelated to this unit

CI failed `test_a_pin_carries_the_next_job_booked_there` with
`0 != 1`, on a branch that had not touched the map.

The map shows Monday-to-Sunday of the current week. The test booked a
job at `now + 2 hours` — inside that window almost always, and outside
it for a two-hour slot once a week. CI ran at **2026-10-11 22:20 local,
a Sunday**: the job landed on Monday, in the next week.

Reproduced both ways before fixing: at that exact moment the old shape
yields 0 jobs; at the same time of night on a Wednesday it yields 1.
That is why it passed locally every time.

Pinned to a Wednesday, and the half nothing asserted was added — a job
nine days out must *not* be on the pin. Without it, pinning the clock
could mask a map that had stopped filtering by week at all.
Mutation-checked.

Swept the suite for the same shape: 18 tests book work relative to
`now`, and the rest are safe for concrete reasons — they compare only
query counts, follow the job's own date, or assert against an unbounded
window (`stats["upcoming"]` is `scheduled_start >= now`). This was the
only one at risk. **Second time-dependent failure this session**; the
first was the seed leaving Payroll empty before mid-morning.

## Verification

```
python manage.py test        # 1,137 pass, 29 new + 1 mirror assertion
ruff / format / check / makemigrations --check   # clean
```

Browser, production settings. As the owner: the warning renders, a hub
note saves, the header Save targets the form. As a crew member at
**phone width**: the job page shows both notes with the customer one
badged, a note can be written from the kerb, and `/tasks/notes/` still
answers 403. 9 steps, 0 failed, 0 CSP violations.

Mutation-checked: dropping `jobs_for` scoping is caught; narrowing the
job page back to job-only notes is caught by 2 tests.

## A merge worth noting

This branched off `main` before unit 2 landed, so merging the trunk
conflicted in three files — both units append to `forms.py` and to both
sweeps' registries. All three were union merges with both sides kept.
`forms.py` needed rebuilding by line index, because both sides ended
with the same two closing lines and git interleaved them. Confirmed
afterwards that the file parses, holds all four forms, and that all six
new routes are still registered in the access sweep — a route lost in a
conflict resolution is exactly what that sweep exists to catch, and a
botched merge could have removed the guard along with the thing it
guards.

## Commit

PR #156.
