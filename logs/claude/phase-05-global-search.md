# PHASE 05: GLOBAL SEARCH (UNIT 1)

Started: 2026-09-12
Ended: 2026-09-12

## Objective

First unit of Phase 5, per the roadmap: global search across CRM
objects, replacing the `core:search` `ComingSoonView` placeholder.

## Files created / changed

- `apps/core/views.py` — `_search()` helper (queries
  Company/Contact/Lead/Deal/Task, each capped at 20 results, each
  ordered by its own natural key plus `pk` as a tiebreaker);
  `SearchView`. Removed `ComingSoonView` — with Search now real, no CRM
  section uses it any more, so it (and its purpose) is gone, not just
  unused.
- `apps/core/urls.py` — `core:search` now points at `SearchView`.
- `apps/core/templates/core/search.html` — search form + grouped
  results by type; `apps/core/templates/core/coming_soon.html`
  deleted.
- `templates/base.html` — replaced the plain "Search" nav link with an
  inline GET search form.
- `static/css/base.css` — minimal `.nav-search` styling.
- `apps/core/tests/test_search.py` — 12 tests.

## Commands

$ (manage.py shell, setup_test_environment + Client) full flow:
  unauthenticated redirect → empty query renders the form with no
  results section → cross-model matches (company name, contact
  name/email, lead name/company_name, deal title, task title) →
  case-insensitivity → no-match message → per-model cap verified at
  exactly 20 real `<li>` results (not just a substring count, which
  was initially thrown off by the query string echoed into the search
  box's own `value` attribute) → nav search box present on the
  dashboard.
Result: PASS, every step — before any automated test existed.

$ python manage.py test apps.core.tests.test_search
Result: PASS — 11/11 initially, 12/12 after the post-review ordering
fix added one more.

$ python manage.py test apps.core.tests.test_navigation
Result: PASS — confirmed removing `ComingSoonView` didn't break the
existing nav-link tests (the dashboard link and reachability checks
still pass, since they check the URL and page content, not the view
class behind it).

$ python manage.py test (full suite)
Result: PASS — 238 tests at merge time, 239 after the ordering fix (up
from 227 before this unit).

$ manage.py check / makemigrations --check --dry-run
Result: PASS — no schema changes this unit.

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after one formatting-only fix (`apps/core/views.py`); no
real findings from the tools themselves.

## Tests

`python manage.py test` — 239 passed, 0 failures.

## Review episode (before merge)

The user pasted an external code review of this PR's diff (title
"feat: add global CRM search") with one overall comment and one inline
suggestion. Per this project's standing discipline — verify every
finding empirically before accepting or dismissing it — both were
checked against the actual repository state, not taken at face value:

- **"SearchView references core/search.html, but this PR does not add
  that template"** — checked `git show --stat` against the actual
  commit and the file on disk: the template was there from the start
  (66 lines, committed). The review had run against a stale or
  incomplete diff; the branch wasn't even pushed to GitHub yet at that
  point, so it could not have been generated from the real PR. Flagged
  to the user as incorrect rather than "fixed."
- **"Add deterministic ordering or relevance ranking before applying
  the per-model limit"** — checked the actual SQL each queryset
  generates (`str(qs.query)`): every model's `Meta.ordering` already
  produces an `ORDER BY` (Company by `name`, Contact by
  `last_name, first_name`, Lead/Deal by `-created_at`, Task by
  `due_date`), so the premise ("no ordering") was overstated. But the
  narrower, real gap survived scrutiny: none of those orderings have a
  tiebreaker, so rows sharing the same sort-key value (several tasks
  with no due date, in particular) have no guaranteed relative order —
  meaning which ones land inside the `[:20]` cap could vary between
  otherwise-identical requests. Fixed by adding `pk` as a secondary
  sort key to all five queries, with a regression test
  (`test_tied_results_are_ordered_by_pk_as_a_tiebreaker`) that asserts
  the returned pks match `sorted()` order for a set of fully-tied
  rows — written to actually fail without the fix, not just re-run the
  same request twice (an earlier draft of the test compared two
  identical requests' HTML, which would likely have passed even
  without the fix, since Postgres tends to return the same physical
  order for back-to-back identical queries in the same session; the
  final version instead asserts the fix's actual effect).

Since the branch hadn't been pushed yet, the fix was folded into the
same local commit via `git commit --amend` rather than added as a
separate commit — no shared history was rewritten.

## Decisions

- Capping each category at 20 results rather than paginating each of
  five querysets separately — simpler, and per CLAUDE.md's Performance
  Rules ("don't optimize speculative problems without measurements"),
  a five-way-simultaneous-search hitting that cap in practice should
  prompt a narrower query, not a pagination UI for global search.
- Activity is excluded from search scope — it has no detail page of
  its own (its detail page is the timeline on whichever record it's
  attached to), so a search result for one would have nowhere sensible
  to link to. Same reasoning already used for `AuditLogEntry`'s scope
  in Phase 4.
- `ComingSoonView` and its template were deleted outright rather than
  left in place "in case a future section needs it" — every current
  CRM nav section now has a real view, so it was genuinely dead code,
  not speculative removal.

## Errors

None found via manual smoke testing or the automated CI/tooling checks.
One real bug-adjacent gap (ordering-under-ties) found via the pasted
external review and confirmed by inspecting actual generated SQL — see
Review episode above. Sourcery itself was rate-limited on this PR (as
it was for the previous two Phase 4 units), so its own findings weren't
a factor either way; the pasted review took its place this time.

## Lessons learned

- The habit from Phase 4 (Tasks) of never accepting *or* dismissing an
  external review finding without reproducing it — established there
  for Sourcery findings — turned out to matter just as much for a
  review from an unfamiliar source: the "missing template" claim was
  simply wrong, and would have been an odd, confusing "fix" (there is
  nothing to add) if taken at face value.
- A regression test for "the results are stable" needs to actually
  distinguish the fixed behavior from the buggy one — comparing two
  requests' output isn't enough if both are likely to return the same
  (undefined-but-incidentally-stable) order anyway; asserting against
  a known-correct order (`sorted(pk)`) is what actually exercises the
  fix.

## Git

Branch: `feature/global-search` (merged, deleted)
Commit: `7a1e4cc` (amended locally pre-push to fold in the
ordering fix — branch was never pushed until after amending)
Merged to `main`: `45c9a06` (regular merge commit, PR #36 — CI green;
Sourcery rate-limited, no findings from it; the pasted external review
was addressed as described above)

## Next

Phase 5 unit 2 — operational dashboard (the `core:index` page currently
just says "Signed in as {{ user.username }}", per Phase 3's
placeholder — build it out with real at-a-glance CRM data).
