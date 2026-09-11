# PHASE 00: AI DEVELOPMENT GOVERNANCE LAYER

Started: 2026-09-10 (continuing same day as Phase 0/1)
Ended: 2026-09-11 (files complete, awaiting explicit commit approval)

## Objective

Harden the process around AI-assisted development before CRM domain work
begins: master rules (`CLAUDE.md`), detailed operational procedures
(`docs/AI_RULES.md`), a technical permission allowlist
(`.claude/settings.json`), a stricter Git/GitHub workflow with branch
protection and CI, and a durable audit trail (ADRs, project state, phase
logs) independent of chat history.

## Files created / changed

- `CLAUDE.md` — rewritten as the master governance document (PROJECT,
  TECHNOLOGY STACK, ARCHITECTURE, DEVELOPMENT RULES, AI OPERATING RULES,
  BASH/SUDO/DATABASE/GIT/GITHUB/LOGGING policies, SECURITY/TESTING/
  PERFORMANCE/DOCUMENTATION rules, SESSION START/CLOSE procedures,
  PRODUCTION RESTRICTIONS, DEPLOYMENT RULES, DO NOT OVERENGINEER).
- `docs/AI_RULES.md` — new; phase-log/failure-log/session-transcript
  templates, session checklists, bash/sudo allow-deny examples.
- `.claude/settings.json` — new; permission allow/ask/deny lists.
- `.claude/settings.local.json` — new; empty machine-local placeholder,
  gitignored.
- `.gitignore` — added `.claude/settings.local.json`; clarified that the
  `*.log` rule doesn't apply to the tracked `logs/` markdown tree.
- `docs/decisions/0001-0004` — ADRs for decisions already made in Phase
  0/1 (Django monolith, PostgreSQL, server-rendered UI, Podman+Caddy).
- `docs/PROJECT_STATE.md`, `CHANGELOG.md` — new.
- `docs/sessions/2026-09-10-phase-00-01-bootstrap.md` — retroactive log
  for the Phase 0/1 work already done.
- `logs/claude/phase-00-ai-rules.md` (this file), `logs/git/{commits,
  branches,releases}.md`, `logs/failures/.gitkeep`,
  `logs/system/2026-09-10-pg-hba-scram-auth.md` — retroactive entry for
  the pg_hba.conf change made during Phase 1.

Also added this phase: `requirements-dev.txt` (ruff, pytest, pytest-django,
bandit, pip-audit, pre-commit), `Makefile` (setup/dev/test/lint/security/
migrate/shell/check, plus honestly-failing stubs for build/arm64/backup),
`.pre-commit-config.yaml`, `.github/workflows/ci.yml`,
`.github/workflows/security.yml`, `.github/dependabot.yml`,
`pyproject.toml` (ruff config), README updates (dev tooling, common
commands, git workflow section).

## Commands

$ pip install -r requirements-dev.txt
Result: PASS — ruff 0.14.4, pytest 8.4.2, pytest-django 4.11.1, bandit
1.8.6, pip-audit 2.9.0, pre-commit 4.3.0 all resolved cleanly.

$ pre-commit run --all-files
Result: ruff auto-fixed 13 lint issues and reformatted 19 files across the
existing Phase 0/1 code (quote style, blank lines) — cosmetic only,
verified with a re-run of `manage.py check`/`test` afterward.

$ ruff check . && ruff format --check .
Result: initially FAILED — `config/settings/development.py` and
`production.py` use Django's standard `from .base import *` settings-split
pattern, which ruff's F403 rule flags by default. This is intentional, not
a bug. Added `pyproject.toml` with a per-file-ignore scoped to those two
files (F403, and F405 for production.py which also references names from
the wildcard import) rather than disabling the rule project-wide. Also
bumped line-length to 100 and re-ran `ruff format .`, which reformatted
`base.py`/`production.py` (cosmetic). Re-verified `manage.py check`/`test`
pass afterward. PASS on re-run.

$ pip-audit -r requirements.txt
Result: PASS — no known vulnerabilities.

$ bandit -r apps config -q
Result: PASS — no issues identified (160 lines scanned).

$ python manage.py check / makemigrations --check --dry-run / test
Result: PASS (0 tests exist yet; none expected until Phase 2).

## Tests

`python manage.py test` — 0 tests, 0 failures (no application code exists
yet to test; this phase is process/tooling only).

## Decisions

- Git/GitHub workflow adopted: `main` + `feature/*`/`fix/*`/`chore/*`/
  `security/*` branches (no `develop`, solo project); Claude never pushes,
  force-pushes, deletes branches, rewrites history, or merges without
  explicit per-instance authorization; commits only on explicit
  instruction after review.
- `container.yml`/`release.yml` workflows deliberately not created yet —
  nothing to build until the Podman phase; a workflow with nothing to
  exercise would just be dead CI.
- `docs/decisions/0005-arm64-production.md` deferred until the ARM64 phase
  actually makes that decision concrete.
- Ruff wildcard-import warnings on the settings split were suppressed
  narrowly (two files, two specific rule codes) rather than broadly, to
  keep the exception auditable.

## Errors

- Initial `.pre-commit-config.yaml` pinned `ruff-pre-commit` to `v0.14.4`,
  which doesn't exist as a tag (ruff-pre-commit's tags don't map 1:1 to
  ruff's own version numbers). Checked actual tags via the GitHub API and
  corrected to `v0.16.7`, the current latest. Resolution verified by
  actually running `pre-commit run --all-files` successfully afterward —
  this is exactly the kind of claim that must be checked, not assumed.
- `ruff check .` failed on F403 in the settings package before the
  `pyproject.toml` per-file-ignore was added — see Commands above.

## Lessons learned

- Pinning a pre-commit hook `rev` needs verifying against the actual
  upstream tags, not guessing a version string that "looks right."
- Django's settings-split pattern (`from .base import *`) is idiomatic but
  trips default linter rules — worth handling with a scoped ignore up
  front rather than leaving lint red.
- Running the full local verification stack (`check`, `test`,
  `makemigrations --check`, `ruff`, `pip-audit`, `bandit`) before proposing
  a commit caught two real issues (the pre-commit tag, the F403 rule) that
  would otherwise have landed as a broken first CI run.

## Git

Branch: `main`
Commit: not yet created — awaiting explicit approval per the Git Policy
this same phase introduced into `CLAUDE.md`.

## Next

Commit this phase's changes in logical groups (see chat for the proposed
commit messages), then set up the GitHub remote
(`JosephHeffron/django-crm`, public): install `gh`, user runs `gh auth
login` themselves, then Claude creates the repo, pushes `main`, and
configures branch protection + secret scanning — all pending the user's
go-ahead.
