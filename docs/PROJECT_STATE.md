# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

AI development governance layer — complete. GitHub remote is live with CI,
branch protection, Dependabot, and secret scanning all active and
verified.

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
  pushed and verified (`ci`/`security` both passed on the push). Branch
  protection on `main`: PR required, `ci`+`security` required status
  checks (strict/up-to-date), no force-push, no deletion, conversation
  resolution required, `enforce_admins: true`. Secret scanning + push
  protection enabled by default (public repo); Dependabot security
  updates enabled. Dependabot already opened 7 PRs (5 pip, 2 GitHub
  Actions), all passing CI — none merged yet, awaiting review (one,
  `pytest` 8.4.2→9.1.1, is a major bump that needs a closer look per the
  "review before major upgrades" rule).

## Currently working on

Nothing in progress. Open Dependabot PRs are waiting on your review/merge
decision — not blocking anything.

## Next

1. Review/merge (or leave) the open Dependabot PRs.
2. Phase 2 — Database design (`docs/DATABASE_DESIGN.md`) for Companies,
   Contacts, Leads, Deals, Activities, Tasks, Notes, before any models are
   implemented.

## Known issues

None.

## Production

Not deployed. No Raspberry Pi hardware acquired yet.

## ARM64

Not yet attempted — planned for a later phase, once Podman containers
exist to test.
