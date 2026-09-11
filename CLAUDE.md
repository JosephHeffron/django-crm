# Development contract — Django CRM

This file is the persistent set of instructions for any AI assistant (or human)
working on this repository. Read it before making changes.

## Stack

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

Do **not** introduce React, Vue, Node.js, Redis, Celery, Kubernetes, or other
infrastructure unless a clearly demonstrated requirement appears — and explain
why it is necessary before adding it.

## Project principles

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

## Required workflow

**Before implementing anything, explain:**
- what you found (current state of the relevant code)
- what you intend to change
- what files will likely be affected
- what tests you will run

**After implementation:**
- run relevant tests
- check migrations
- check formatting/linting where configured
- summarize changes
- identify anything that still needs manual testing

**Always:**
- Inspect the existing implementation before changing code. Do not assume
  previous architecture decisions are correct — but do not discard them
  without understanding why they exist.
- Do not modify unrelated files.
- Do not attempt an entire roadmap phase in one change. Break work into small
  logical units; after each unit, implement, test, inspect, and report before
  moving to the next.
- Show exactly what changed and what tests were run.

## Roadmap

See `docs/ROADMAP.md` for the phased development plan and
`docs/ARCHITECTURE.md` for the system architecture.
