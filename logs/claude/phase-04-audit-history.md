# PHASE 04: AUDIT HISTORY (UNIT 3)

Started: 2026-09-12
Ended: 2026-09-12

## Objective

Third and final unit of Phase 4, per Prompt 4.3: a lightweight record
of who changed what and when on important CRM records — not a full
event-sourcing/versioning system, not every operation.

## Design step (before implementation)

Per CLAUDE.md's Documentation Rules, wrote the design into
`docs/DATABASE_DESIGN.md` (new "AuditLogEntry" entity + a "Decisions"
note on the signals-vs-explicit-calls mechanism choice) before writing
any code. Confirmed scope with the user first: audited models are
Company/Contact/Lead/Deal only — Task (lower-stakes, has its own
status/`completed_at` trail) and Activity (already immutable history)
are explicitly out.

## Files created / changed

- `apps/crm/models.py` — `AuditLogEntry` (generic FK via `contenttypes`:
  `content_type` + `object_id` + `GenericForeignKey`, `user`
  `on_delete=SET_NULL`, `action` choices `created`/`updated`, `changes`
  `JSONField`).
- `apps/crm/migrations/0004_auditlogentry.py`.
- `apps/crm/admin.py` — `AuditLogEntryAdmin`, read-only (no add, no
  change) — same reasoning as `ActivityAdmin`: a record of what
  happened shouldn't itself be editable after the fact.
- `apps/crm/views.py` — `_record_audit_log()`, `_diff_changed_fields()`,
  `_audit_log_for()` helpers; wired into
  `Company/Contact/Lead/Deal{CreateView,UpdateView}.form_valid()`,
  `Company/ContactDeactivateView.post()`, and `LeadConvertView.post()`
  (its own `created` entries for any newly-created Company/Contact/Deal
  plus an `updated` entry for the Lead's status change — no
  special-cased "conversion" action).
- `apps/crm/templates/crm/_audit_history.html` — reusable partial,
  included on all four detail pages.
- `apps/crm/tests/test_audit_log.py` — 18 tests.

## Commands

$ (manage.py shell, setup_test_environment + Client) full flow: Company
  create → update (diff correctness) → no-op update (no entry) →
  deactivate (`is_active` diff) → detail page renders History → Contact
  create/company-reassignment diff → Lead create → conversion (new
  company/contact/deal all logged `created`, Lead logged `updated` with
  its status diff) → conversion with an *existing* company (no spurious
  `created` entry for it) → Deal create/stage-change diff → confirmed
  distinct `content_type` values scope entries correctly.
Result: PASS, every step — before any automated test existed.

$ python manage.py test apps.crm.tests.test_audit_log
Result: PASS — 18/18 on the first run.

$ python manage.py test (full suite)
Result: PASS — 227 tests (up from 209).

$ manage.py check / makemigrations --check --dry-run
Result: PASS — migration applied cleanly against real PostgreSQL.

$ ruff check . / ruff format --check . / pip-audit / bandit
Result: PASS after two formatting-only fixes (the new test file, and —
new this unit — the generated migration file itself, which isn't
auto-excluded from `ruff format` the way it is from the `E501` lint
rule); no real findings.

**Post-merge, before closing out** — Sourcery was rate-limited on this
PR too (see Git section), so per the lesson from the Tasks unit, did a
second, deliberately adversarial manual pass specifically hunting for
what an automated reviewer would flag: XSS in the History display
(rendered user-submitted field values back out — verified Django's
auto-escaping handles it, confirmed with a literal `<script>` payload
in a field), sequential edits to the same field, a round-trip edit back
to the original value, unsetting a value to blank, and cross-user
visibility (matches the app's existing no-ownership model everywhere
else — not a new gap this unit introduces).
Result: no findings. Dev database confirmed clean of all test/review
leftovers before committing and again before merging.

## Tests

`python manage.py test` — 227 passed, 0 failures.

## Decisions

- Explicit calls from views, not signals — see
  `docs/DATABASE_DESIGN.md`'s new "Decisions that intentionally avoid
  overengineering" note. Signals would also catch admin/shell writes,
  but can't see `request.user` without a thread-local, which this app
  has no other reason to introduce.
- `changes` diffs are built by fetching a fresh pre-edit copy of the
  row at the top of `form_valid()` (before `super().form_valid()`
  saves), then comparing named `form.changed_data` fields against the
  post-save instance — not from `form.initial`, which stores raw FK
  pks rather than the same string representation `cleaned_data` yields
  for a FK field. Using two real model instances for both sides of the
  diff keeps the "old"/"new" formatting consistent (both go through
  `str()`) instead of comparing an int against an object's `__str__`.
- No entry is written for a no-op edit (`form.changed_data` empty) —
  a natural consequence of the diff-based design, not a special case.
- One generic `AuditLogEntry` table (via `django.contrib.contenttypes`,
  already installed) rather than one log table per audited model —
  avoids duplicating an identical shape four times for a "prefer
  Django's built-in functionality" win.

## Errors

None found in the original implementation, either by manual smoke
testing or the post-merge adversarial review pass. Two formatting-only
lint fixes (see Commands above), not application bugs.

## Lessons learned

- The post-merge "review as if I were Sourcery" habit adopted after
  the Tasks unit (which *did* find a real bug that way) is now applied
  a second time — this time coming back clean, which is itself useful
  confirmation that the practice isn't just retroactively rationalizing
  a fluke, and worth keeping as standard practice whenever Sourcery
  isn't available, not just as a one-off reaction to the last miss.
- `ruff format --check .` doesn't skip migration files just because
  `pyproject.toml` gives them an `E501` lint exemption — the two are
  independent; a generated migration can still need a formatting pass.

## Git

Branch: `feature/audit-history` (merged, deleted)
Commit: `42504d3`
Merged to `main`: `479c6a3` (regular merge commit, PR #34 — CI green;
Sourcery rate-limited again, ~5 days 16 hours remaining at merge time;
no findings from either its guide-only comment or the manual
adversarial review pass done in its place)

## Next

Phase 4 is now fully complete (all 3 units: Activity timeline, Tasks,
Audit history). Next is Phase 5 — Search, dashboard, usability.
