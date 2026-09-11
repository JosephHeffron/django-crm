# Session: Phase 0 + Phase 1 bootstrap

Date: 2026-09-10

## Objective

Establish the development contract and git baseline (Phase 0), then
bootstrap a real Django project with PostgreSQL (Phase 1), replacing a
stray untracked `django-admin startproject` scaffold that had been left
directly in the home directory.

## Actions taken

- Removed the stray scaffold (`~/manage.py`, `~/crm/`, `~/db.sqlite3`) —
  confirmed disposable, untracked, default-generated.
- Created `~/projects/django-crm`, `git init`, `pyenv local 3.12.6`, a
  project-local virtualenv.
- Wrote `CLAUDE.md` (development contract) and `.gitignore`; committed as
  the git baseline.
- Wrote `docs/ARCHITECTURE.md` and `docs/ROADMAP.md`; committed separately.
- Bootstrapped Django: `config/` split into `settings/{base,development,
  production}.py`, three apps under `apps/{core,users,crm}`, PostgreSQL
  configured via environment variables (`.env`/`.env.example`), a minimal
  root route (`apps.core`) so the project actually boots.
- Created the local PostgreSQL role/database (`django_crm`/`django_crm`),
  which required a scoped `scram-sha-256` `pg_hba.conf` rule since the
  system default (`ident`) rejects password auth over localhost — see
  `logs/system/2026-09-10-pg-hba-scram-auth.md`. This required `sudo`; the
  user supplied the password directly to run it.
- Verified: `manage.py check` clean, `manage.py migrate` applied against
  real PostgreSQL, `manage.py test` runs (0 tests, none exist yet).

## Files changed

`CLAUDE.md`, `.gitignore`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`,
`manage.py`, `config/**`, `apps/**`, `requirements.txt`, `README.md`,
`.env.example`, `static/.gitkeep`, `templates/.gitkeep`.

## Commands / tests

```
$ python manage.py check          → System check identified no issues
$ python manage.py migrate        → all built-in migrations applied
$ python manage.py test           → 0 tests, no failures
```

## Decisions

Recorded retroactively as ADRs: `docs/decisions/0001-django-monolith.md`,
`0002-postgresql.md`, `0003-server-rendered-ui.md`,
`0004-podman-caddy-deployment.md`.

## Errors encountered

- `startapp` failed with `ModuleNotFoundError` because the three app
  labels were already listed in `INSTALLED_APPS` before their directories
  existed. Resolved by temporarily removing them from `INSTALLED_APPS`,
  running `startapp` three times, then restoring the list and fixing each
  app's `apps.py` `name` attribute to the `apps.<name>` dotted path.
- Local PostgreSQL connection failed with `Ident authentication failed`
  until the `pg_hba.conf` rule above was added.
- `sudo` required a password with no TTY available to the agent; the user
  provided the password directly in chat for this one-off system change.

## Git

Branch: `main`
Commits: `7fd6941` (contract + baseline), `9226fd4` (architecture +
roadmap), `33a3b2f` (Django bootstrap).

## Unresolved issues

None outstanding for Phase 0/1.

## Next recommended step

Formalize AI development governance (this session's follow-on task) before
starting Phase 2 (CRM database design).
