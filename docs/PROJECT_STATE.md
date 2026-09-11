# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

Phase 2 (CRM database design) — design complete
(`docs/DATABASE_DESIGN.md`), reviewed and merged. Model implementation
(`apps/crm/models.py`, migrations, admin, tests) is the next step, not yet
started.

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

## Currently working on

Nothing in progress. 6 Dependabot PRs (4 pip minor/patch bumps, 2 GitHub
Actions bumps) are still open, waiting on review/merge — not blocking
anything. (A 7th, the pytest security fix, was merged.)

## Next

1. Implement `apps/crm` models from `docs/DATABASE_DESIGN.md`: Company,
   Contact, Lead, Deal, Task, Activity — migrations, admin registration,
   model tests (creation, relationships, constraints, validation, edge
   cases).
2. `docs/DATABASE_REVIEW.md` — a senior-reviewer pass on the implemented
   schema against the design doc, per the roadmap, before moving on to
   the CRM interface (Phase 3).
3. Review/merge (or leave) the remaining open Dependabot PRs.

## Known issues

None.

## Production

Not deployed. No Raspberry Pi hardware acquired yet.

## ARM64

Not yet attempted — planned for a later phase, once Podman containers
exist to test.
