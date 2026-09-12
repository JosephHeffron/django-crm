# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

> **Last updated 2026-09-11.** Repo is clean (`main` up to date, nothing
> uncommitted). Phase 4 is in progress — units 1 (Activity timeline)
> and 2 (Tasks) done and merged. Next: lightweight audit history
> (unit 3) — see "Next" below.

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

Phase 2 (CRM database) and Phase 3 (CRM interface) are both complete.
Phase 3 shipped in 5 units: authentication + base shell, full
navigation/error pages/styling, Companies CRUD, Contacts CRUD, and
Leads/Deals workflows (including the lead-to-Contact/Company/Deal
conversion workflow). The two deferred HIGH findings and one MEDIUM
finding from `docs/DATABASE_REVIEW.md` were resolved before starting
Phase 4. Phase 4 (Activities, Tasks, audit history) is now in progress —
units 1 (Activity timeline) and 2 (Tasks) are done and merged.

Phase 2's `docs/DATABASE_REVIEW.md` found 2 HIGH findings (Activity's
`CASCADE` can silently destroy history still relevant to a surviving
object; `on_delete` guarantees only hold through the Django ORM, not raw
SQL) plus a MEDIUM finding that Activity immutability isn't actually
enforced beyond the admin. Per the user's explicit choice, these are
deferred until before Phase 4 (Activities/Tasks UI) rather than blocking
Phase 3 — see Known Issues below.

## Completed

- Phase 0 — Development rules, git baseline, `docs/ARCHITECTURE.md`,
  `docs/ROADMAP.md`.
- Phase 1 — Django project bootstrapped (`config/` + `apps/{core,users,crm}`
  layout), PostgreSQL wired as the only database backend, `manage.py
  check`/`migrate`/`test` all verified passing.
- AI governance layer: `CLAUDE.md` rewritten as the master rules document;
  `docs/AI_RULES.md` (operational procedures); `.claude/settings.json`
  permission allow/ask/deny list; ADRs 0001-0004; `CHANGELOG.md`;
  `Makefile`; `requirements-dev.txt`; `.pre-commit-config.yaml`;
  `pyproject.toml` (ruff config); `.github/workflows/{ci,security}.yml`;
  `.github/dependabot.yml`. All verified locally: `manage.py
  check`/`test`/`makemigrations --check`, `ruff check`/`format --check`,
  `pip-audit`, `bandit` all pass. Full detail in
  `logs/claude/phase-00-ai-rules.md`.
- GitHub remote: `github.com/JosephHeffron/django-crm` (public), `main`
  pushed and verified. Branch protection on `main`: PR required, `test`+
  `dependency-audit` required status checks (the actual CI *job* names,
  not the `ci`/`security` workflow file names — corrected after an
  initial misconfiguration), strict/up-to-date, no force-push, no
  deletion, conversation resolution required, `enforce_admins: true`.
  Secret scanning + push protection enabled by default (public repo);
  Dependabot security updates enabled. PR #4 (`pytest` 8.4.2→9.1.1, fixes
  a real medium-severity advisory) merged; 6 more Dependabot PRs still
  open for review.
- Phase 2 database design (`docs/DATABASE_DESIGN.md`, PR #9): Company,
  Contact, Lead, Deal, Task, Activity — fields, relationships,
  constraints, indexing, lifecycle. An automated review caught two real
  defects (a `SET_NULL`/`CheckConstraint` conflict on Deal, and a
  self-contradictory `CASCADE` rationale) — both fixed before merge. Full
  detail in `logs/claude/phase-02-database-design.md`.
- Phase 2 model implementation (`apps/crm/models.py`, PR #11): all six
  models implemented from the design doc, migrated against real
  PostgreSQL (both CheckConstraints confirmed live via `\d+`), 38 model
  tests. An automated review caught two more real gaps — `Deal.probability`
  had no upper-bound enforcement (added a CheckConstraint) and
  `Activity` (documented as immutable) was still editable via the admin,
  the only mutation path that currently exists (disabled admin change
  permission for it). Full detail in `logs/claude/phase-02-crm-models.md`.
- Phase 2 schema review (`docs/DATABASE_REVIEW.md`, PR #14): senior-
  reviewer pass on the implemented schema. Two HIGH findings, both
  verified empirically (not inferred): `on_delete` behavior is enforced
  entirely by Django's ORM, not by PostgreSQL (every FK is `NO ACTION`
  at the DB level — confirmed via `pg_constraint` and a raw SQL delete
  that should have cascaded but instead failed); Activity's `CASCADE` on
  all four relation FKs can destroy history still relevant to a
  surviving object (confirmed by deleting a Deal and watching an
  Activity also tagged to a still-existing Company vanish with it). Plus
  5 MEDIUM findings (including that Activity immutability still isn't
  enforced beyond the admin — confirmed a plain `.save()` bypasses it)
  and several LOW findings. Automated review caught two issues in the
  review itself (an unsound `SET_NULL` recommendation, an overly
  reassuring "nothing contradicts the design" claim) — both fixed. Full
  detail in `logs/claude/phase-02-database-review.md`.
- Phase 3 unit 1 — authentication + minimal base template shell
  (PR #16): Django's built-in login/logout/password-change views under
  `apps/users`, `templates/base.html` shell, `apps.core`'s dashboard
  placeholder now behind `login_required`. Verified end-to-end against a
  running server before writing 9 tests. Automated review caught a real
  `NoReverseMatch` bug on successful password change (the view's default
  `success_url` didn't account for app namespacing) — reproduced,
  fixed, and covered with a regression test (48 tests total). Full
  detail in `logs/claude/phase-03-authentication.md`.
- Phase 3 unit 2 — full navigation, error pages, styling (PR #18):
  full shell nav (Dashboard + all 6 CRM sections + Search), a shared
  `ComingSoonView` giving every not-yet-built section a real working
  login-required URL, custom `404.html`/`500.html` (500 deliberately
  standalone per Django's own guidance), expanded `base.css`. All 8 nav
  URLs, the 404 page, and the 500 template verified directly before
  writing 4 new tests (52 total). First unit in this project with no
  automated-review findings. Full detail in
  `logs/claude/phase-03-navigation-shell.md`. This completes the
  "application shell" scope (Prompt 3.1).
- Phase 3 unit 3 — Companies CRUD (PR #20): list (search + active/
  inactive filter + pagination), detail (shows related Contacts/Deals),
  create, edit, and deactivate (not delete — see below) views,
  replacing the `crm:company_list` placeholder. Manual smoke testing
  caught a real 500 on deleting a company with deal history
  (`Deal.company` is `on_delete=PROTECT`); automated review then caught
  a deeper issue — hard-deleting a company at all contradicts
  `docs/DATABASE_DESIGN.md`'s documented "never hard-deleted from the
  UI" invariant. Reworked to `CompanyDeactivateView`
  (`is_active=False`, never calls `.delete()`), which made the earlier
  fix moot. 78 tests total. Full detail in
  `logs/claude/phase-03-companies-crud.md`.
- Phase 3 unit 4 — Contacts CRUD (PR #22): list (search across name/
  email + active/inactive + company filters + pagination), detail
  (shows linked Company, related Deals/Tasks), create, edit, deactivate
  views, replacing the `crm:contact_list` placeholder. Checked
  `docs/DATABASE_DESIGN.md` before building (unit 3's lesson) and used
  deactivation from the start this time. Automated review still caught
  three real gaps in the company filter: no UI control to actually set
  it, pagination silently dropping it, and a non-numeric value crashing
  with a 500 — all reproduced and re-verified fixed. 107 tests total.
  Full detail in `logs/claude/phase-03-contacts-crud.md`.
- Phase 3 unit 5 — Leads and Deals workflows (PRs #24, #25), the final
  Phase 3 unit: Lead CRUD with a status field that excludes "Converted"
  as directly selectable (only the dedicated conversion workflow can
  set it), and `LeadConvertView` — link/create a Company, always create
  a Contact, optionally open a Deal, then mark the Lead converted, per
  `docs/DATABASE_DESIGN.md`'s Lifecycle section. Deal CRUD with form
  validation mirroring both of Deal's DB `CheckConstraint`s (applied
  proactively this time, not found by review) and a `closed_at`
  set/clear lifecycle tied to stage. Deal references from Company/
  Contact/Lead detail pages now link properly. 158 tests total, zero
  real findings from review on either PR — full detail in
  `logs/claude/phase-03-leads-deals.md`.

**Phase 3 (CRM interface) is now fully complete.**

- Pre-Phase-4 — resolved `docs/DATABASE_REVIEW.md`'s two HIGH findings
  and MEDIUM finding #7 (PR #27): `Activity`'s four relation FKs changed
  `CASCADE` → `SET_NULL` (chose to preserve multi-tagging rather than
  restrict Activity to exactly one relation), the now-incompatible
  `activity_has_related_object` `CheckConstraint` removed,
  `Activity.save()` now rejects updates to existing rows, and
  `CLAUDE.md` documents that `on_delete` only holds through Django, not
  raw SQL. Each finding's original failing reproduction was re-run and
  confirmed fixed, not just re-read. 161 tests total. Full detail in
  `logs/claude/phase-04-prep-resolve-review-findings.md`.
- Phase 4 unit 1 — Activity timeline (PR #29): real
  `ActivityListView`/`ActivityCreateView` (type filter, pagination,
  query-param prefill, priority-ordered redirect after save), a
  reusable timeline partial included on all four detail pages
  (Company/Contact/Lead/Deal), `ActivityForm` enforcing "at least one
  relation" at the form layer. No update/detail view for Activity —
  it's immutable and its "detail page" is the timeline on whichever
  record it's attached to. 181 tests total, zero findings from review.
  Full detail in `logs/claude/phase-04-activity-timeline.md`.
- Phase 4 unit 2 — Tasks (PR #31): list (status/priority filters,
  `?mine=1`, `?overdue=1`, pagination), detail, create, edit views, and
  a dedicated `TaskCompleteView` (POST-only one-click completion,
  separate from the edit form, open-redirect-safe `next` handling),
  replacing the `crm:task_list` placeholder. `completed_at` kept in
  sync with `status` via `_sync_task_completed_at`, mirroring the
  existing `Deal.closed_at` pattern. Contact/Deal detail pages' task
  listings now link to task detail. Sourcery's automated review was
  rate-limited on this PR (no findings either way), so it merged on
  CI + full local verification alone (207 tests total at merge time).
  A subsequent, deliberately more thorough manual review (to
  compensate for the missing Sourcery pass) found a real bug:
  `TaskCompleteView` had no guard against completing an already-
  cancelled task via a direct POST — fixed with the same kind of
  status guard `LeadConvertView` already uses, plus 2 regression
  tests (209 tests total). Full detail in
  `logs/claude/phase-04-tasks.md`.

## Currently working on

Nothing in progress. 6 Dependabot PRs (4 pip minor/patch bumps, 2 GitHub
Actions bumps) are still open, waiting on review/merge — not blocking
anything. (A 7th, the pytest security fix, was merged.)

## Next

1. Phase 4 unit 3 — lightweight audit history for important CRM record
   changes, per Prompt 4.3.
2. Review/merge (or leave) the remaining open Dependabot PRs.

## Known issues

None currently known. (The three findings previously tracked here —
Activity's `CASCADE` behavior, `on_delete` ORM-only enforcement, and
Activity immutability — are resolved; see "Completed" above and
`docs/DATABASE_REVIEW.md` for the full resolution detail.)

Remaining MEDIUM/LOW findings from `docs/DATABASE_REVIEW.md` (#3-#6 and
the LOW items) are still open but were assessed as non-blocking —
see that document for details.

## Production

Not deployed. No Raspberry Pi hardware acquired yet.

## ARM64

Not yet attempted — planned for a later phase, once Podman containers
exist to test.
