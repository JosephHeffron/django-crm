# PHASE 03: LEADS AND DEALS WORKFLOWS (UNIT 5 — FINAL PHASE 3 UNIT)

Started: 2026-09-11
Ended: 2026-09-11

## Objective

Fifth and final unit of Phase 3, per `docs/ROADMAP.md`'s single "Leads
and Deals workflows" bullet — implemented as two PRs (Leads first, then
Deals) but closed out together here since the roadmap treats them as
one unit and they share this session's context.

## Files created / changed

Leads (PR #24):
- `apps/crm/forms.py` — `LeadForm` (excludes "Converted" as a
  selectable status choice; disables the field once actually
  converted), `LeadConversionForm`.
- `apps/crm/models.py` — `Lead.get_absolute_url()`.
- `apps/crm/views.py` — `LeadListView`, `LeadDetailView`,
  `LeadCreateView`, `LeadUpdateView`, `LeadConvertView` (a plain `View`,
  not a generic CBV — GET shows a pre-filled conversion form, POST
  creates/links a Company, always creates a Contact, optionally opens a
  Deal, then marks the Lead converted).
- `apps/crm/urls.py` — real routes replacing the `lead_list` placeholder.
- `apps/crm/templates/crm/lead_{list,detail,form,convert}.html`.
- `apps/crm/tests/test_lead_views.py` — 28 tests.

Deals (PR #25):
- `apps/crm/forms.py` — `DealForm` with `clean()` mirroring both of
  Deal's DB `CheckConstraint`s (company-or-contact required,
  probability 0-100) at the form layer.
- `apps/crm/models.py` — `Deal.get_absolute_url()`.
- `apps/crm/views.py` — `DealListView`, `DealDetailView`,
  `DealCreateView`, `DealUpdateView`, plus a `_sync_deal_closed_at()`
  helper implementing the `closed_at` lifecycle behavior documented in
  `docs/DATABASE_DESIGN.md`.
- `apps/crm/urls.py` — real routes replacing the `deal_list` placeholder.
- `apps/crm/templates/crm/deal_{list,detail,form}.html`.
- `apps/crm/templates/crm/{company,contact,lead}_detail.html` — deal
  references now link via `get_absolute_url()` instead of plain text.
- `apps/crm/tests/test_deal_views.py` — 23 tests.

## Commands

$ (manage.py shell, setup_test_environment + Client) full Lead CRUD +
  conversion cycle: create → detail → search → status filter → convert
  GET (prefilled) → convert POST (new company/contact/deal) →
  re-convert blocked → detail shows converted info
Result: PASS, all steps — before any automated Lead test existed.

$ (same approach) conversion edge cases: existing-company path, no-deal
  path, both-company-fields-set validation error, deal-without-title
  validation error, missing-contact-name validation error
Result: PASS, all five — before any automated test existed for them.

$ python manage.py test apps.crm.tests.test_lead_views
Result: FAILED first — one bug in my own test (submitted a POST
without a `status` value, assuming the model's `default=NEW` would
apply; it doesn't for a bound form missing a required field's POST
value — that's not how a real browser submits a `<select>`). Fixed by
including `status` in the test's POST data. PASS after — 135 tests.

$ (manage.py shell, same approach) full Deal CRUD cycle: create
  (company-only, contact-only) → validation rejections (neither
  company/contact; probability > 100) → detail → search/stage/open
  filters → stage transition to closed_won (closed_at set) → reopen
  (closed_at cleared) → open filter excludes closed deals
Result: One step's assertion ("closed deal excluded from open filter")
initially read as FAILED — investigated as a potential real bug before
accepting it. Root cause and resolution: see Errors.

$ python manage.py test
Result: PASS — 158 tests total (28 Lead + 23 Deal, up from 107 after
Contacts CRUD).

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS on the first attempt for both PRs — no fixes needed either
round.

## Tests

`python manage.py test` — 158 passed, 0 failures.

## Decisions

- `LeadConvertView` is a plain `django.views.generic.View`, not a
  `CreateView`/`UpdateView` — the workflow creates up to three separate
  objects (Company, Contact, Deal) and mutates a fourth (the Lead
  itself), which doesn't map cleanly onto any single-model generic CBV.
- Lead's `status` field excludes "Converted" from the editable choices
  entirely (not just disabled) on create, and is `disabled` on update
  once a Lead is actually converted — the only way `status` becomes
  `converted` is through `LeadConvertView`, which is what keeps the
  `converted_at`/`converted_company`/`converted_contact`/
  `converted_deal` fields consistent with the status change.
- `DealForm.clean()` duplicates both of Deal's DB-level
  `CheckConstraint`s in Python. This is deliberate redundancy, not
  copy-paste waste: the DB constraint is the actual guarantee (catches
  anything that bypasses the form — admin, shell, future API), the form
  validation is what turns a violation into a normal user-facing error
  instead of an unhandled 500. Same reasoning already applied to
  `LeadConversionForm` for the "both company fields" and "deal needs a
  title" cases.
- `_sync_deal_closed_at()` runs in both `DealCreateView.form_valid` and
  `DealUpdateView.form_valid`, not in a model `save()` override —
  keeps the invariant at the layer that already owns "how a Deal gets
  changed through the UI," consistent with how `docs/DATABASE_DESIGN.md`
  frames this as an application-layer (not DB-layer) invariant.

## Errors

- My own test bug (Leads): `test_successful_create_sets_created_by_and_defaults`
  posted `{"name": ..., "source": "website"}` with no `status` key,
  expecting the model's `default=NEW` to apply. It doesn't — a
  `ModelForm`'s required field with no submitted value fails validation
  as "This field is required," regardless of the underlying model
  field's default. A real browser always submits *some* value for a
  `<select>`, since one option is always marked `selected`. Fixed by
  including `status: "new"` in the test's POST data, with a comment
  explaining why the omission was wrong rather than just fixing it
  silently.
- A investigation, not a bug (Deals): manually testing the `open=1`
  filter after a `stage` reassigned directly via `deal.stage =
  "closed_lost"; deal.save()` appeared to show the excluded deal's
  title still present in the response body. Investigated properly
  before concluding either way — reproduced the exact same DB state in
  isolation (deal created directly with `stage="closed_lost"`), which
  correctly returned "No deals found," proving the *query* was right.
  Located the actual source of the string match: a queued Django
  **flash message** ("Updated deal “Acme deal”.") left over from an
  earlier `POST` in the same smoke-test script that hadn't been
  displayed (and thus consumed) yet — it rendered on the very next GET
  regardless of which page that GET was for, and my substring check
  matched against it, not the actual deals table. No application
  change needed. Adjusted the automated tests to check
  `response.context["deals"]` structurally instead of raw substring
  matching against `response.content`, to avoid the same false-positive
  risk in the actual test suite.

## Lessons learned

- "The model has a `default=`" is not the same guarantee as "a bound
  form will use it" — a `ModelForm`'s required-field validation runs
  against what was actually submitted, independent of the model's own
  default. Worth remembering when hand-constructing test POST payloads
  rather than assuming a browser-equivalent submission.
- When a manual smoke-test assertion looks like it caught a bug,
  reproducing the *exact* suspicious state in isolation (rather than
  re-running the whole script) is a fast way to tell a real defect from
  a methodology artifact — here it took one extra isolated repro to
  find that Django's flash-message queue, not the filter logic, was
  the actual source of the unexpected match.
- Raw substring matching against `response.content` is fragile once a
  page has *any* other dynamic text on it (flash messages, nav labels,
  filter option lists) — `response.context[...]` gives a structural
  assertion that can't be fooled by unrelated page furniture. Worth
  defaulting to context-based assertions for list-membership checks
  specifically, reserving substring checks for content-presence checks
  where the risk of collision is lower.
- Two units in a row (Leads, Deals) applying a lesson from a prior
  unit's review findings (proactive form validation mirroring DB
  constraints) resulted in zero real findings from either manual smoke
  testing or automated review on either PR — the pattern of "apply the
  last review's lesson before it's found again" appears to actually be
  working, not just aspirational.

## Git

Branch: `feature/leads-crud` (merged, deleted), `feature/deals-crud`
(merged, deleted)
Commits: `f55088e` (Leads CRUD + conversion), `1c408b0` (Deals CRUD)
Merged to `main`: `2acdbcb` (PR #24, squash), `98cd056` (PR #25, squash)

## Next

Phase 3 is now fully complete (all 5 units: authentication/shell,
navigation/error-pages/styling, Companies CRUD, Contacts CRUD, Leads/
Deals workflows). Before Phase 4 (Activities, Tasks, audit history):
resolve `docs/DATABASE_REVIEW.md`'s two HIGH findings (Activity CASCADE
behavior, on_delete enforcement) and the Activity-immutability MEDIUM
finding — deferred by explicit user choice back at the start of Phase
3, not forgotten. This is the natural point to return to them, since
Phase 4's Activity Timeline work is exactly what those findings are
about.
