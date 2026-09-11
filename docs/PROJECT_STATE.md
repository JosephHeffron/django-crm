# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

> **Last updated 2026-09-11.** Repo is clean (`main` up to date, nothing
> uncommitted). User chose to defer `docs/DATABASE_REVIEW.md`'s HIGH
> findings until before Phase 4 and proceed with Phase 3 now — see
> "Next" below for where Phase 3 currently stands.

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

Phase 2 (CRM database) is complete. Phase 3 (CRM interface) is in
progress — unit 1 (authentication + minimal base template shell) is done
and merged. Next units: full navigation/styling/error pages, then
Companies CRUD, then Contacts CRUD.

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

## Currently working on

Nothing in progress. 6 Dependabot PRs (4 pip minor/patch bumps, 2 GitHub
Actions bumps) are still open, waiting on review/merge — not blocking
anything. (A 7th, the pytest security fix, was merged.)

## Next

1. Phase 3 unit 2 — full navigation (Companies/Contacts/Leads/Deals/
   Activities/Tasks/Search links in the shell), styling refinement,
   custom 404/500 error pages.
2. Phase 3 unit 3 — Companies CRUD (list/detail/create/edit/delete,
   search, filtering, pagination).
3. Phase 3 unit 4 — Contacts CRUD.
4. Before Phase 4: resolve `docs/DATABASE_REVIEW.md`'s two HIGH findings
   (Activity CASCADE, on_delete enforcement) and the Activity-immutability
   MEDIUM finding — deferred by explicit user choice, not forgotten.
5. Review/merge (or leave) the remaining open Dependabot PRs.

## Known issues

Two HIGH-severity schema findings from `docs/DATABASE_REVIEW.md`,
deliberately not yet fixed (review-only, per the explicit instruction —
see "Next" above for the resolution decision):

1. `Activity`'s `CASCADE` on all four relation FKs can destroy history
   still relevant to a surviving object, if an Activity is tagged to
   more than one of Company/Contact/Lead/Deal at once and only one of
   them is deleted.
2. `on_delete` behavior (`PROTECT`/`SET_NULL`/`CASCADE`) is enforced
   entirely by Django's ORM, not by PostgreSQL — any deletion that
   bypasses the ORM (raw SQL, a future data-migration script) won't
   honor it.

Plus one MEDIUM finding worth flagging here specifically: `Activity`
immutability (documented as an invariant) is enforced only by
`ActivityAdmin.has_change_permission`, not at the model layer — any
other write path can still edit or reassign an existing Activity.

Full findings, severities, and recommendations: `docs/DATABASE_REVIEW.md`.

## Production

Not deployed. No Raspberry Pi hardware acquired yet.

## ARM64

Not yet attempted — planned for a later phase, once Podman containers
exist to test.
