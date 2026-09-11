# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

> **Session paused here on 2026-09-11.** Repo is clean (`main` up to
> date, nothing uncommitted, no PRs open from this session). To resume,
> see "Next" below — a decision is needed on how to handle the two HIGH
> findings from `docs/DATABASE_REVIEW.md` before continuing.

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

Phase 2 (CRM database) — design, model implementation, and schema review
all complete and merged. `docs/DATABASE_REVIEW.md` found 2 HIGH findings
(Activity's CASCADE can silently destroy history still relevant to a
surviving object; `on_delete` guarantees only hold through the Django
ORM, not raw SQL) plus a MEDIUM finding that Activity immutability isn't
actually enforced beyond the admin. The review's own recommendation:
these don't need to block Phase 3 (CRM interface), but should be
resolved before Phase 4 (Activities/Tasks UI) builds on top of them.

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
  4 MEDIUM findings (including that Activity immutability still isn't
  enforced beyond the admin — confirmed a plain `.save()` bypasses it)
  and several LOW findings. Automated review caught two issues in the
  review itself (an unsound `SET_NULL` recommendation, an overly
  reassuring "nothing contradicts the design" claim) — both fixed. Full
  detail in `logs/claude/phase-02-database-review.md`.

## Currently working on

Nothing in progress. 6 Dependabot PRs (4 pip minor/patch bumps, 2 GitHub
Actions bumps) are still open, waiting on review/merge — not blocking
anything. (A 7th, the pytest security fix, was merged.)

## Next

**Decision needed**: whether to resolve `docs/DATABASE_REVIEW.md`'s two
HIGH findings (+ the MEDIUM Activity-immutability one) now, or proceed
straight to Phase 3 and resolve them before Phase 4 specifically (the
review's own recommendation — Phase 3 doesn't touch Activity's CASCADE
behavior or mutation surface, so nothing blocks it).

1. Either: resolve the Activity findings (schema change — needs its own
   design decision per `docs/DATABASE_REVIEW.md` finding #2's two
   options, migration, and re-verification), or: start Phase 3 — CRM
   interface: application shell (nav, layout, base templates), then
   Companies/Contacts CRUD.
2. Review/merge (or leave) the remaining open Dependabot PRs.

## Known issues

None.

## Production

Not deployed. No Raspberry Pi hardware acquired yet.

## ARM64

Not yet attempted — planned for a later phase, once Podman containers
exist to test.
