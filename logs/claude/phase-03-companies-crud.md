# PHASE 03: COMPANIES CRUD

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Third unit of Phase 3: Companies CRUD (list/detail/create/edit/
deactivate, search, filtering, pagination), replacing the
`crm:company_list` placeholder with real views, per the roadmap and
Prompt 3.2. ("Delete" in Prompt 3.2's own wording — "delete where
permitted" — turned out to mean deactivate once
`docs/DATABASE_DESIGN.md`'s documented invariant was checked; see
Errors.)

## Files created / changed

- `apps/crm/forms.py` — new; `CompanyForm` (ModelForm, excludes
  `created_by`/timestamps).
- `apps/crm/views.py` — `CompanyListView` (search by name, active/
  inactive filter, pagination), `CompanyDetailView` (shows related
  Contacts/Deals), `CompanyCreateView`, `CompanyUpdateView`,
  `CompanyDeactivateView` (see Errors — this replaced an initial
  `CompanyDeleteView`).
- `apps/crm/models.py` — `Company.get_absolute_url()`.
- `apps/crm/urls.py` — real routes replacing the `company_list`
  `ComingSoonView` placeholder.
- `apps/crm/templates/crm/company_{list,detail,form,confirm_deactivate}.html`.
- `static/css/base.css` — table/filter-form/pagination/dl styling.
- `apps/crm/tests/test_company_views.py` — new, 24 tests (across two
  commits — see Git).

## Commands

$ (manage.py shell, setup_test_environment + Client) full CRUD cycle
  against the first-draft CompanyDeleteView (later superseded — see
  Errors): empty list → create → detail → search (match/no-match) →
  update → delete → unauthenticated redirect
Result: PASS, all steps — before any automated test existed.

$ (same approach) POST to delete a company that has a Deal, still
  against the first-draft CompanyDeleteView
Result: FAILED first — unhandled 500, `ProtectedError` propagating
uncaught (`Deal.company` is `on_delete=PROTECT`). See Errors. (This
whole delete-based flow was later replaced by deactivation.)

$ (same approach, after the deactivate rework) POST to
  CompanyDeactivateView for a company that has a Deal
Result: PASS — 302 to the detail page, `is_active` set to `False`, the
company row and its Deal both still exist. No exception at all this
time, since deactivation never calls `.delete()` and so never touches
the `PROTECT` constraint that caused the original 500.

$ python manage.py test
Result: PASS — 77 tests after the first commit (25 new), then 78 after
the deactivate rework (net +1, since one delete-specific test became
two deactivate-specific tests plus removed the now-obsolete
ProtectedError test).

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after two small fixes (a `Client()` API quirk unrelated to
lint; an actual `E501` line-length violation in the second commit's new
test, fixed).

## Tests

`python manage.py test` — 78 passed, 0 failures.

## Decisions

- `CompanyForm` excludes `created_by` (set from `request.user` in
  `CompanyCreateView.form_valid`) and timestamps — only fields a human
  should actually edit are on the form.
- `Company.get_absolute_url()` added so Create/Update views redirect to
  the detail page using Django's default `CreateView`/`UpdateView`
  behavior, rather than hardcoding `success_url` on each view.
- Company "removal" from the CRM UI is deactivation
  (`is_active = False`), not deletion — see Errors below for why this
  wasn't the first draft.

## Errors

- Manual smoke testing (before any automated test existed) caught a
  real bug: `CompanyDeleteView` (first draft) called `.delete()`
  directly; deleting a company with any `Deal` attached raised an
  unhandled 500, since `Deal.company` is `on_delete=PROTECT`
  (`docs/DATABASE_DESIGN.md` finding #6, known since the schema
  review). First fix: catch `ProtectedError`, show a friendly message.
  Verified working via the test client.
- Automated review (`sourcery-ai`, PR #20) caught something the manual
  smoke test and the first fix both missed: `docs/DATABASE_DESIGN.md`
  explicitly documents "companies are never hard-deleted from the UI" —
  `is_active` is the intended soft-removal mechanism. The
  `CompanyDeleteView` I'd built (even with the `ProtectedError` fix)
  directly contradicted that documented invariant for every company
  *without* deal history, where the delete would have succeeded and
  actually removed the row, cascading its activities and orphaning its
  contacts' company reference. Confirmed by re-reading the design doc's
  own field table. Fixed by replacing the whole delete flow with
  `CompanyDeactivateView` (`is_active = False`, never calls `.delete()`
  at all) — which also made the earlier `ProtectedError` handling moot,
  since deactivation never touches the constraint that caused it.
- One test-writing mistake of my own, caught while debugging a failure
  I initially assumed was an application bug: `assertRedirects()`
  follows the redirect target by default to verify it returns 200,
  which silently consumed the one-time cookie-based Django message
  before my own explicit follow-up `GET` could see it. Fixed with
  `fetch_redirect_response=False`. (This test was later replaced
  entirely by the deactivate rework, but the lesson stands.)

## Lessons learned

- A design decision recorded in a docs file during an earlier phase
  (`docs/DATABASE_DESIGN.md`'s "never hard-deleted from the UI") is easy
  to silently violate weeks/phases later when building the actual view
  that touches that model — worth explicitly re-checking the relevant
  design doc section before writing a delete/remove view, not just
  relying on memory of what was decided.
- `assertRedirects()`'s default behavior of following the redirect can
  interact badly with one-time-read state (Django messages, similar
  patterns) — worth knowing `fetch_redirect_response=False` exists
  before spending time debugging what looks like an application bug but
  is actually the test's own assertion consuming the state under test.
- Two review-caught findings in this unit, on top of one caught purely
  by manual smoke testing before any review — reinforces that neither
  manual testing nor automated review alone would have caught both
  issues; the combination did.

## Git

Branch: `feature/companies-crud` (merged, deleted)
Commits: `498a0ac` (initial CRUD + ProtectedError fix),
`ea0db05` (deactivate rework, from review)
Merged to `main`: `aa246cb` (squash merge, PR #20)

## Next

Phase 3 unit 4 — Contacts CRUD, following the same pattern
(list/detail/create/edit/delete-or-deactivate, search, filtering,
pagination) — and checking `docs/DATABASE_DESIGN.md` for Contact's own
documented lifecycle before assuming hard-delete is appropriate there
either.
