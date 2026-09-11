# Development contract — Django CRM

This file is the persistent set of instructions for any AI assistant (or
human) working on this repository. Read it before making changes.
Detailed step-by-step operational procedures (log formats, checklists,
allow/deny examples) live in `docs/AI_RULES.md` — this file holds the
permanent rules; that one holds the mechanics.

## PROJECT

A self-hosted CRM: Django monolith, PostgreSQL, server-rendered templates,
deployed to a Raspberry Pi 5 (ARM64) via Podman + Caddy + systemd. See
`docs/ARCHITECTURE.md` for the system design and `docs/ROADMAP.md` for the
phased build-out plan. Current status: `docs/PROJECT_STATE.md`.

## TECHNOLOGY STACK

Development workstation: Fedora Linux, Git, VS Code, Claude Code, pyenv,
Python 3.12, Podman, qemu-user-static.

Production target: Raspberry Pi 5, ARM64 Linux, Podman, systemd.

Runtime stack:
- Django
- Django templates, HTML, CSS, vanilla JavaScript where necessary
- PostgreSQL
- psycopg2-binary
- Podman + podman-compose
- Caddy (reverse proxy / HTTPS)

## ARCHITECTURE

See `docs/ARCHITECTURE.md`. Past architectural decisions and their
rationale are recorded in `docs/decisions/` — read the relevant ADR before
changing something that looks like it could be simplified; it may be
intentional.

## DEVELOPMENT RULES

1. Keep the architecture simple.
2. Prefer Django's built-in functionality.
3. Prefer server-rendered pages.
4. Use PostgreSQL in development and production — never SQLite as the real
   development database.
5. Keep development and production configurations separate.
6. Never hard-code secrets.
7. Never commit passwords, API keys, certificates, private keys, or `.env`
   files containing secrets.
8. Write automated tests for application behavior.
9. Use migrations for every database schema change.
10. Preserve backward compatibility whenever practical.
11. Do not rewrite existing functionality without first understanding it.
12. Make small, reviewable changes.
13. Update documentation when behavior or architecture changes.
14. Every meaningful feature must have tests.
15. Every production-impacting change must consider security, backups,
    logging, and rollback.

## AI OPERATING RULES

1. Never modify production systems directly.
2. Never access production secrets.
3. Never invent configuration values.
4. Never delete production data.
5. Never run destructive database commands without explicit approval.
6. Never reset, drop, truncate, or recreate a production database.
7. Never force-push Git history.
8. Never modify main/master directly.
9. Never bypass failing tests merely to make a build pass.
10. Never disable security checks to resolve an implementation problem.
11. Never commit secrets.
12. Never commit `.env` files containing real credentials.
13. Never automatically deploy to production.
14. Never change infrastructure unrelated to the current task.
15. Never upgrade a major dependency without reviewing compatibility.
16. Every database change requires a migration.
17. Every feature requires tests.
18. Every bug fix requires a regression test when practical.
19. Before modifying unfamiliar code, inspect it first.
20. Before changing architecture, document why.
21. Keep changes small and logically isolated.
22. Run the relevant tests after every implementation unit.
23. Never claim a test passed unless it was actually executed.
24. Never claim a deployment succeeded unless it was actually verified.
25. Prefer reversible changes.

## ARCHITECTURAL COMPLEXITY RULE — DO NOT OVERENGINEER

This is a small self-hosted CRM.

Prefer: Django, PostgreSQL, server-rendered templates, Podman, Caddy,
systemd.

Do not add: Kubernetes, microservices, Redis, Celery, RabbitMQ,
Elasticsearch, Kafka, React, Next.js, service meshes, complex observability
stacks — unless a concrete requirement demonstrates the simpler
architecture is insufficient.

Every new infrastructure dependency must state: why it is required, what
problem it solves, maintenance cost, security implications, resource
requirements, and the simpler alternative considered.

## BASH POLICY

Routine, safe development commands run without asking for confirmation
(exact allow/deny patterns are enforced technically via
`.claude/settings.json`, not just by convention):

Allowed automatically: `pwd`, `ls`, `find`, `grep`/`rg`, `cat`, `git
status`/`diff`/`log`/`branch` (read-only forms), `python`, `pytest`,
`manage.py check|test|makemigrations --check`, `ruff`, `podman
ps|logs|build`, `podman compose` (non-destructive subcommands),
`systemctl status`, `journalctl`, `curl` against local development
services.

Never automatic — always ask first: `git push --force`, `git reset --hard`,
`rm -rf`, destructive SQL (`DROP`, `TRUNCATE`, unscoped `DELETE`), `dd`,
`mkfs`, `shutdown`, `reboot`, firewall flush/disable, disabling SELinux.

## SUDO POLICY

Sudo may be used for legitimate, routine system administration: `dnf
install/update` packages, `systemctl status/start/stop/restart` on
project-related services, `journalctl` access, directory
ownership/permissions for this project, installing required system
dependencies (Podman, `qemu-user-static`), Podman configuration.

Never use sudo to: delete unrelated system data, recursively change
permissions across the filesystem, disable SELinux, disable the firewall,
modify unrelated services, touch partitions/disks, delete user accounts,
modify SSH configuration, change bootloader configuration, or run a
destructive command merely to make an error go away.

If sudo is required for an unexpected or potentially destructive operation,
stop and explain why before executing it.

## DATABASE SAFETY

**Development:** database resets are permitted only when explicitly
requested.

**Test:** test databases may be freely created and destroyed.

**Staging:** destructive operations require explicit approval.

**Production:** never `DROP DATABASE`. Never `DROP TABLE`. Never
`TRUNCATE`. Never `DELETE` large record sets without explicit approval.
Never reset migrations. Never modify production data through ad-hoc SQL.
Always back up before a high-risk schema operation.

Prefer Django migrations over manual database modifications. Do not
manually edit migration history unless explicitly directed.

**`on_delete` (`PROTECT`/`SET_NULL`/`CASCADE`) only holds through
Django.** Confirmed via `pg_constraint`
(`docs/DATABASE_REVIEW.md` finding #1): every foreign key in this
schema is `NO ACTION` at the actual PostgreSQL level — Django
implements `on_delete` in Python (the ORM's deletion `Collector`), not
as native `ON DELETE` clauses. Raw SQL, a data-migration script using
`cursor.execute()`, or any other path that bypasses the ORM will not
cascade, set-null, or protect as documented — a raw delete that's
supposed to cascade will instead fail with a foreign-key violation.
Never assume `on_delete` behavior holds outside `Model.delete()`/
`QuerySet.delete()`.

## GIT POLICY

Claude may create commits only when explicitly instructed. Before creating
a commit: show `git status`, inspect the diff, run relevant tests,
summarize the changes, and propose a commit message. Only commit after
explicit approval of that message.

Claude must never, without explicit per-instance authorization:
- push to any remote
- force-push
- delete branches
- rewrite history
- merge pull requests
- modify `main` directly

Branching convention (solo project — no `develop`): `main`,
`feature/<name>`, `fix/<name>`, `chore/<name>`, `security/<name>`. Work
happens on a branch; `main` only receives merges.

## GITHUB POLICY

`main` is protected: pull request required, required status checks
(`ci`, `security`), no force pushes, no branch deletion, conversation
resolution required, secret scanning + push protection enabled.

Dependabot manages dependency PRs (pip, GitHub Actions) — these are
reviewed and merged like any other PR, never auto-merged, never
auto-deployed.

CI (`.github/workflows/ci.yml`, `security.yml`) must pass before merge.
Claude does not modify branch protection or repository security settings
without explicit instruction.

## LOGGING POLICY

Never write the following to any project log, commit message, documentation,
test fixture, or transcript: passwords, database passwords, API keys, OAuth
tokens, private keys, session cookies, authentication headers, production
secrets, customer credentials. Redact as `[REDACTED]` if a value must be
referenced. If a task requires a secret: reference it through environment
variables, never print it, never place it in source, docs, or fixtures.

## SECURITY RULES

Never bypass failing tests or disable security checks to make a build pass.
Never commit secrets or `.env` files with real values — `.env.example`
holds placeholders only. Review Django security settings (`DEBUG`,
`ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, secure cookies) whenever
production configuration changes.

## TESTING RULES

Every meaningful feature and every bug fix (regression test, when
practical) requires automated tests. Run relevant tests after every
implementation unit — never claim a test passed without having executed
it. Do not claim a deployment succeeded without verifying it.

## PERFORMANCE RULES

1. Use `select_related`/`prefetch_related` where appropriate.
2. Do not load unbounded record sets into memory.
3. Paginate user-facing lists.
4. Add indexes based on actual query patterns.
5. Use database aggregation for aggregate operations.
6. Do not optimize speculative problems without measurements.

## DOCUMENTATION RULES

Update documentation when behavior or architecture changes. Record
significant architectural decisions in `docs/decisions/` (Decision /
Context / Alternatives considered / Decision made / Reason / Consequences /
Date) before implementing them, not after. Update `CHANGELOG.md` for
meaningful releases — not for every small fix.

## SESSION START PROCEDURE

Before making any changes:
1. Read `CLAUDE.md`.
2. Read `docs/PROJECT_STATE.md`.
3. Read `docs/ROADMAP.md`.
4. Read the latest entry under `logs/claude/` and `docs/sessions/`.
5. Inspect `git status`, current branch, and recent commits.
6. Identify the current phase and summarize what is already completed.
7. Identify the exact next task.

Do not modify anything until this review is complete. Do not repeat
completed work unless verification shows it's actually necessary.

## SESSION CLOSE PROCEDURE

Before ending a session:
1. Run relevant tests and required validation.
2. Inspect `git diff` and `git status`.
3. Update `docs/PROJECT_STATE.md` to reflect actual state.
4. Write/update the current phase log under `logs/claude/`.
5. Update `CHANGELOG.md` if the change is meaningful.
6. Record commands executed, results, errors, and resolutions.
7. Record architectural decisions made (as ADRs if significant).
8. Record remaining/unresolved work and the next recommended step.
9. Record the commit hash if a commit was created.
10. Do not push unless explicitly authorized. Do not claim anything is
    complete unless it was actually verified.

Full templates for phase logs, failure logs, and session transcripts are in
`docs/AI_RULES.md`.

## PRODUCTION RESTRICTIONS

Claude Code is a development tool. Claude Code must never: SSH into
production automatically, execute arbitrary production commands, modify
production databases, restart production services, delete production
files, or deploy production releases. Production deployment happens only
through the documented deployment process and explicit human
authorization.

## DEPLOYMENT RULES

No automatic deployment to production, ever. Deployments are scripted,
non-destructive, and reviewable (`scripts/deploy.sh`, once it exists), with
a documented rollback path. GitHub Actions builds and tests; a human
approves production deployment.
