# PHASE 03: CONTACTS CRUD

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Fourth unit of Phase 3: Contacts CRUD (list/detail/create/edit/
deactivate, search, filtering, pagination), following Companies CRUD's
pattern and its lesson — checked `docs/DATABASE_DESIGN.md` for
Contact's documented lifecycle before deciding delete-vs-deactivate,
rather than repeating unit 3's mistake.

## Files created / changed

- `apps/crm/forms.py` — `ContactForm`.
- `apps/crm/models.py` — `Contact.get_absolute_url()`.
- `apps/crm/views.py` — `ContactListView` (search across first/last
  name/email, active/inactive filter, company filter, pagination),
  `ContactDetailView` (shows linked Company, related Deals/Tasks),
  `ContactCreateView`, `ContactUpdateView`, `ContactDeactivateView`.
- `apps/crm/urls.py` — real routes replacing the `contact_list`
  placeholder.
- `apps/crm/templates/crm/contact_{list,detail,form,confirm_deactivate}.html`.
- `apps/crm/templates/crm/company_detail.html` — contact list entries
  now link to each contact's own detail page (previously plain text).
- `apps/crm/tests/test_contact_views.py` — new, 29 tests (26 initial +
  3 regression, across two commits — see Git).

## Commands

$ (manage.py shell, setup_test_environment + Client) full CRUD cycle:
  create (with/without company) → detail → search → company filter →
  update → deactivate → unauthenticated redirect, plus related
  deals/tasks shown on detail
Result: PASS, all steps — before any automated test existed.

$ python manage.py test
Result: FAILED first — one bug in my own test (`test_status_filter`
asserted on the literal word "Inactive", which always appears in the
filter `<select>` regardless of what's actually filtered). Fixed by
using names that don't collide with the filter UI's own text. PASS
after — 104 tests.

$ (manage.py shell, same approach as above, after review) reproduced
  three findings before fixing: invalid `?company=abc` → 500;
  `<option>` elements for company filter absent from rendered HTML;
  pagination links missing `&company=`
Result: all three confirmed real, then all three re-verified fixed —
see Errors.

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after one formatting fix each round; no real lint/security
findings this unit.

## Tests

`python manage.py test` — 107 passed, 0 failures (up from 78 after
Companies CRUD).

## Decisions

- Applied Companies CRUD's deactivate-not-delete pattern to Contact
  proactively, based on `Contact.is_active` existing for evidently the
  same reason as `Company.is_active` (though the design doc's rationale
  sentence is only spelled out for Company) — checked the design doc
  first this time instead of defaulting to a standard `DeleteView`.
- Contact search matches first name, last name, *or* email
  (`Q(...)|Q(...)|Q(...)`), not just name — email is a common way
  someone would look up a contact.
- Company detail's contact list now links to contact detail pages,
  closing a small gap left over from Companies CRUD (added before
  Contact detail views existed, so it could only show plain text then).

## Errors

- My own test bug (caught by running the suite, not by review):
  `test_status_filter` checked for the bare word "Inactive" in the
  response, which always appears in the filter `<select>`'s own option
  text regardless of which contacts are actually shown — so the
  assertion could never meaningfully fail. Fixed by using contact names
  that don't contain "active"/"inactive" as substrings.
- Automated review (`sourcery-ai`, PR #22) caught three real gaps in
  the `?company=` filter, all reproduced empirically before fixing (not
  taken on faith):
  1. The filter form had no company `<select>` control at all — the
     queryset supported `?company=<id>` from the start, but nothing in
     the UI could actually set it, making the feature unreachable
     through normal navigation.
  2. Pagination's Previous/Next links carried `q`/`status` but not
     `company`, so paging through a company-filtered list silently
     dropped the filter.
  3. `?company=abc` (non-numeric) reached `filter(company_id=company_id)`
     directly and raised an unhandled 500 (`ValueError` during
     PostgreSQL type coercion) — reproduced via the test client first,
     confirming the traceback before writing the fix.

## Lessons learned

- Implementing a filter's backend query logic and testing it via query
  parameters directly (as I did first) can pass every test while the
  filter remains completely unreachable through the actual UI — worth
  explicitly checking "is there a control that sets this parameter" as
  its own item, not assumed to follow from "the queryset handles it."
- A second unit in a row where automated review caught real gaps that
  neither my own manual smoke testing nor my own automated tests did —
  reinforces treating review findings as a distinct, necessary check
  rather than a formality after "tests already pass."
- Checking a prior phase's design doc before writing a view (this
  unit's opening decision, prompted by unit 3's mistake) worked as
  intended — no repeat of the hard-delete-vs-documented-invariant
  problem this time.

## Git

Branch: `feature/contacts-crud` (merged, deleted)
Commits: `d1f49bf` (initial CRUD), `5ae8ad5` (company-filter fixes,
from review)
Merged to `main`: `48fcda1` (squash merge, PR #22)

## Next

Phase 3 unit 5 — Leads and Deals workflows (per `docs/ROADMAP.md`'s
Phase 3 scope), the last unit before Phase 3 is fully complete. Then
the deferred Phase 2 review findings, before Phase 4.
