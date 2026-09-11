# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

AI development governance layer — files complete, awaiting explicit commit
approval (see `CLAUDE.md`'s Git Policy) and then GitHub remote setup.

## Completed

- Phase 0 — Development rules, git baseline, `docs/ARCHITECTURE.md`,
  `docs/ROADMAP.md`.
- Phase 1 — Django project bootstrapped (`config/` + `apps/{core,users,crm}`
  layout), PostgreSQL wired as the only database backend, `manage.py
  check`/`migrate`/`test` all verified passing.
- AI governance layer: `CLAUDE.md` rewritten as the master rules document;
  `docs/AI_RULES.md` (operational procedures); `.claude/settings.json`
  permission allow/ask/deny list; ADRs 0001-0004; `docs/PROJECT_STATE.md`
  (this file); `CHANGELOG.md`; `Makefile`; `requirements-dev.txt`;
  `.pre-commit-config.yaml`; `pyproject.toml` (ruff config);
  `.github/workflows/{ci,security}.yml`; `.github/dependabot.yml`. All
  verified locally: `manage.py check`/`test`/`makemigrations --check`,
  `ruff check`/`format --check`, `pip-audit`, `bandit` all pass. Full
  detail in `logs/claude/phase-00-ai-rules.md`.

## Currently working on

Nothing in progress — governance layer files are complete and verified.
Blocked on: your approval of the proposed commit messages (not yet
committed, per the Git Policy this phase introduced), then the GitHub
remote setup (you run `gh auth login` yourself; Claude does the rest).

## Next

1. Commit the governance layer (pending your approval).
2. Set up `github.com/JosephHeffron/django-crm` (public repo), branch
   protection, Dependabot, secret scanning.
3. Phase 2 — Database design (`docs/DATABASE_DESIGN.md`) for Companies,
   Contacts, Leads, Deals, Activities, Tasks, Notes, before any models are
   implemented.

## Known issues

None.

## Production

Not deployed. No Raspberry Pi hardware acquired yet.

## ARM64

Not yet attempted — planned for a later phase, once Podman containers
exist to test.
