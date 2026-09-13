# Usability review

Phase 5 unit 3 — a dedicated usability review pass, per the roadmap.
Unlike the CRUD units, this wasn't new-feature work: it's a review of
the existing interface, in the same spirit as `docs/DATABASE_REVIEW.md`
for the schema. Findings are ranked by severity; every finding below
was fixed in this same unit (see `logs/claude/phase-05-usability-review.md`
for the verification detail).

## Method

No visual browser tool was available in this environment (the
project's own `WebFetch` tool explicitly doesn't support `localhost`).
The review was grounded in two things instead:

1. **A real, authenticated walkthrough against the actual dev server**
   (`manage.py runserver`), not just the Django test client: logging in
   over real HTTP with `curl`, extracting real CSRF tokens, and
   inspecting the exact HTML the app sends — creating a Company,
   Contact, Lead, Deal, and Task through their real forms; converting
   a Lead; completing a Task; and reading the resulting pages exactly
   as delivered.
2. **A systematic re-read of every template** for accessibility basics
   (labelled form controls, semantic HTML), navigation completeness
   (a way back from every page), consistent feedback (flash messages),
   and terminology consistency.

This combination caught a real, previously-unnoticed bug (see HIGH,
below) that no amount of `assertContains`-based automated testing had
caught, because nothing had ever asserted on the *absence* of stray
text — a concrete demonstration of why this unit calls for an actual
rendered-page walkthrough rather than only extending the existing
Django-test-client suite.

## HIGH

### 1. Django template comments were leaking onto every Company/Contact/Lead/Deal detail page

`apps/crm/templates/crm/_activity_timeline.html` and
`_audit_history.html` both opened with a multi-line `{# ... #}`
comment. Django's `{# #}` comment tag does **not** support multi-line
content — empirically confirmed via `django.template.engines['django'].from_string()`
in isolation: a single-line `{# ... #}` is stripped correctly, but a
comment spanning a newline is rendered as literal text instead. Since
both partials are included on all four of Company/Contact/Lead/Deal's
detail pages, every one of those pages was showing raw template-source
text like "Reusable activity timeline. Expects `activities` (a
queryset, newest first — Activity's own default ordering) and..." to
real users, for as long as those two units have existed (Phase 4,
units 1 and 3).

No existing automated test caught this because every test that visited
these pages asserted that expected content (e.g. "No activity yet",
specific record names) *was* present — never that the leaked comment
text was *absent*. This is exactly the gap a browser-based/HTML-level
walkthrough is for.

**Status: FIXED.** Both comments converted to `{% comment %}
...{% endcomment %}` blocks, which do support multi-line content —
verified directly against Django's template engine before and after.
A repo-wide scan (`re.DOTALL` search across every `.html` template)
confirmed these were the only two multi-line `{# #}` comments in the
codebase. Regression tests added in
`apps/crm/tests/test_template_rendering.py`
(`TemplateCommentsAreNotLeakedTests`) assert the leaked text is absent
from all four detail pages.

## MEDIUM

### 2. Filter/search inputs had no accessible labels

Every list page's filter form (Companies, Contacts, Leads, Deals,
Tasks, Activities) and the global search page relied on `placeholder`
text alone for their search box, and had no label at all on their
`<select>` filter dropdowns — confirmed by fetching the real rendered
HTML for each. Placeholder-only inputs are a well-known accessibility
anti-pattern (the hint disappears once you start typing, and isn't a
substitute for an accessible name for every screen reader/browser
combination), and the `<select>` elements had no accessible name at
all. The one exception already found in the codebase — Deal's "Open
only" checkbox, wrapped in a real `<label>` — showed the existing
convention this should have followed everywhere.

**Status: FIXED.** Added visually-hidden (`.sr-only`) `<label>`
elements paired via `for`/`id` to every filter-form text input and
`<select>` across all six list templates and the search page. The nav
search box already had `aria-label="Search"`, which is an equally
valid accessible-name mechanism, so it was left as-is.

### 3. No way back from a Create/Edit form except the browser's own back button

All six Create/Edit form templates (Company, Contact, Lead, Deal,
Task, Activity) were just a heading, the form, and a Save button — no
link back to the record or list. This was inconsistent with the
Deactivate confirmation pages, which already have a "Cancel" link back
to the record.

**Status: FIXED.** Added a "Cancel" link to all six form templates: for
the five models with both Create and Update views, it goes to
`object.get_absolute_url` when editing or the model's list view when
creating. Activity has no Update view and no single natural "list"
context (it's usually created from a specific record's detail page via
a `?relation=<id>` query param), so `ActivityCreateView` gained a
`cancel_url` context value that reuses the same relation-priority logic
already used for `get_initial()`/`get_success_url()`, falling back to
`crm:activity_list` when no relation param is present.

### 4. The nav gave no indication of which section you were currently in

Confirmed via the real rendered HTML: the nav's seven links had no
active/current styling or `aria-current` attribute, so there was no way
to tell at a glance which section you were in — a basic orientation
cue missing from every page.

**Status: FIXED.** Added `aria-current="page"` (the standards-correct
attribute for exactly this) to the matching nav link, computed from
`request.resolver_match.url_name` (e.g. `"company"` `in` the url_name
lights up "Companies" for `company_list`/`company_detail`/etc.), plus
a small CSS rule to make it visually distinct. Verified no false
matches across the seven sections' actual URL names.

## LOW

### 5. Flash messages had no `role="status"` for assistive technology

The `{% if messages %}` block in `templates/base.html` was a plain
`<ul>` — readable on page load by a screen reader traversing the page
linearly, but not marked as a live/status region, which is the
standard, low-cost way to make this kind of transient feedback
reliably discoverable.

**Status: FIXED.** Added `role="status"` to the messages `<ul>`.

### 6. Data tables had no horizontal-scroll handling for narrow viewports

`static/css/base.css` has no fixed large pixel widths (so nothing
outright breaks at phone width), but the six templates using
`.data-table` (five list pages plus the dashboard's pipeline-by-stage
table) had no wrapping strategy for a table wider than a narrow
screen — it would either overflow the viewport or force the whole page
to scroll horizontally, rather than just the table.

**Status: FIXED.** Wrapped every `.data-table` in a `<div
class="table-responsive">` (`overflow-x: auto`) rather than putting
`overflow`/`display: block` on the table element itself, which would
have broken the table's own column-alignment layout.

## Deferred (not fixed this unit)

- **Dashboard has no quick "Add X" shortcuts** — the quick-stat links
  go to filtered list views, not directly to a Create form. A genuine
  nice-to-have, not a blocker; revisit if it comes up as a real
  friction point once the app has real day-to-day users.
- **No currency formatting on `Deal.value`** — raw numeric display
  everywhere a value is shown. This isn't a new finding — it's the
  same "no currency field, single-currency assumed" decision already
  documented in `docs/DATABASE_DESIGN.md`'s "Decisions that
  intentionally avoid overengineering" section from Phase 2, re-noted
  here only because a usability pass is exactly where it would
  otherwise be raised. Nothing new to do unless multi-currency becomes
  a real requirement.

## Checked and confirmed NOT a bug

- **The 404 page shows Django's own technical debug page, not the
  custom `404.html`**, when hit against the local dev server. Verified
  this is expected: `config/settings/development.py` sets `DEBUG =
  True`, and Django only renders custom error templates when `DEBUG =
  False`. The custom `404.html`/`500.html` templates (Phase 3) are
  already covered by `apps/core/tests/test_error_pages.py`, which
  exercises them the correct way (via Django's test client with `DEBUG`
  overridden) rather than by hitting the dev server directly.

## What's solid

- Every detail page (Company/Contact/Lead/Deal/Task/Lead-conversion)
  has a consistent "← Back to list" link at the top — this review
  checked all of them, not just a sample.
- Cross-record linking is thorough and consistent: a Company's detail
  page lists its Contacts and Deals with working links; a Contact's
  lists its Deals and Tasks; a converted Lead links to the
  Company/Contact/Deal it produced; a Task links to its Contact/Deal.
  Verified end-to-end via the real walkthrough (create → convert →
  follow every resulting link), not just spot-checked.
- Django's own `.as_p()` form rendering already gives every actual
  Create/Edit form field a proper `<label for="...">` — the labelling
  gap (finding #2) was specific to the hand-written filter forms, not
  the record forms themselves.
- Empty-state messages ("No companies found.", "No activity yet.",
  etc.) are present and consistent everywhere a list or timeline could
  be empty.
- CSRF protection is correctly wired on every form that mutates state,
  including the one-click Task-complete action and the logout button.
- The Activity timeline and Audit history sections, exercised together
  during the real walkthrough (create a Lead → convert it → watch the
  timeline show "status: new → converted"), are genuinely useful in
  practice, not just in test assertions.

## Recommendation

The interface is functionally solid; every finding from this review —
including the one real, previously-invisible bug — was fixed within
this same unit, with regression tests added for the two most
significant ones (the comment leak, and the Cancel-link/`cancel_url`
behavior). **Phase 5 (Search, dashboard, usability) is now fully
complete.**
