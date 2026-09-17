# Developer guide

Phase 14 unit 1 — orientation for anyone extending this codebase.
This project already has substantial documentation; this guide's job
is to be the short thing you read first, pointing to the right
longer document for whatever you're about to do, rather than
duplicating any of it.

## Where to start

- **Set up your local environment**: the `README.md`'s "Development
  setup" section — native Python/PostgreSQL, not containers.
  Day-to-day development in this project has always been native
  (`manage.py runserver`), never containerized — the Podman/Caddy
  stack exists for production, and for testing the production stack
  itself, not as a replacement for local dev.
- **Understand the system design**: `docs/ARCHITECTURE.md` — the
  overall shape (Django monolith, PostgreSQL, Caddy, no API layer, no
  background task queue), the project's file layout, and the
  architectural boundaries (security, ARM64, backups) that later
  phases built on top of.
- **Understand the domain model**: `docs/DATABASE_DESIGN.md` — every
  field, relationship, constraint, and lifecycle rule for Company,
  Contact, Lead, Deal, Task, and Activity, with the reasoning behind
  each decision, including several that look simpler than they could
  be on purpose (`docs/decisions/` has the standalone ADRs for the
  biggest ones — monolith vs. microservices, PostgreSQL, server-
  rendered UI, Podman+Caddy, rootless systemd).
- **Understand this project's own working rules**: `CLAUDE.md` — the
  development contract this entire project has been built under
  (small reviewable changes, mandatory tests, migration discipline,
  security defaults, the Git/GitHub workflow). This applies to any
  contributor, not just AI-assisted sessions, even though it was
  originally written with that in mind.

## Project layout

```
config/          # project wiring only — no domain logic
  settings/      # base.py (shared) + development.py / production.py
apps/
  core/          # cross-cutting: health check, dashboard, search,
                 #   base template, error pages
  users/         # authentication (login/logout/password change)
  crm/           # the actual domain: Company, Contact, Lead, Deal,
                 #   Task, Activity — models, views, forms, tests
templates/        # project-level template overrides/base layout
static/           # project-level CSS (no JS framework, no build step)
scripts/          # entrypoint.sh (container), deploy/backup/restore.sh
                  #   (production operations), test-arm64.sh (ARM64
                  #   validation)
systemd/          # production systemd units (see docs/ADMIN_GUIDE.md)
docs/             # architecture, design, and every phase's own
                  #   review/audit document
logs/claude/      # a phase-by-phase build log — what was built, what
                  #   broke, how it was fixed, for every phase of this
                  #   project's development
```

`Containerfile`, `Caddyfile`/`Caddyfile.dev`, and
`compose.prod.yml`/`compose.dev.yml` live at the repository root, not
nested under `containers/`/`compose/` subdirectories — a deliberate
deviation from `docs/ARCHITECTURE.md`'s original sketch, made when
those files were first added, to avoid unnecessary reorganization
churn (see `logs/claude/phase-07-django-container.md`).

## Common tasks

**Add a field to an existing model**: update the model in
`apps/crm/models.py`, run `python manage.py makemigrations`, check the
generated migration is sane, then `python manage.py migrate`. Every
schema change goes through a real migration — never hand-edit the
database. If the field needs a `CheckConstraint` or similar DB-level
rule, add it in the model's own `Meta.constraints`, matching the
existing pattern (`Deal.probability`'s constraints are a good
reference).

**Add a new view**: this project is server-rendered throughout — no
JS framework, no API endpoints beyond `/health/`. Follow the existing
pattern for the model you're working with (e.g. `CompanyListView`/
`CompanyDetailView`/`CompanyCreateView` in `apps/crm/views.py`) rather
than inventing a new one. Every view that changes data needs
`PermissionRequiredMixin` (see `docs/PERMISSIONS.md` for the actual
permission names in use) and a corresponding test.

**Add a test**: this project uses Django's own test runner
(`manage.py test`), not `pytest` directly, even though `pytest-django`
is present in `requirements-dev.txt` — a known, documented,
deliberately-not-yet-cleaned-up inconsistency (see
`docs/DEPENDENCY_AUDIT.md`). Put new tests in the relevant app's
`tests/` directory, following the existing file-per-concern pattern
(e.g. `apps/crm/tests/test_company_views.py`).

**Run the full verification stack** (what CI runs, plus what every
phase of this project has run before every commit):
```
make test       # python manage.py test
make lint       # ruff check + ruff format --check
make security   # pip-audit + bandit
make check      # manage.py check + makemigrations --check
```

## Git / PR workflow

Covered in full in `README.md`'s "Git workflow" section and
`CLAUDE.md`'s GIT POLICY / GITHUB POLICY — branch naming
(`feature/*`/`fix/*`/`chore/*`/`security/*`), `main` protected via
required PR + CI, no force-push, no direct commits to `main`. Every
merge in this project's history has also been followed by a small,
separate docs-only "close out" PR (a phase log plus a
`docs/PROJECT_STATE.md` update) — not mandatory for every future
change, but the established pattern for anything substantial enough to
warrant its own written record; see any file under `logs/claude/` for
what that record looks like.

## Historical context

This project was built phase by phase (`docs/ROADMAP.md`), each with
its own detailed build log under `logs/claude/` — what was
implemented, what broke, how it was found and fixed, and why each
non-obvious decision was made. If something in the codebase looks
surprising, the phase log for whichever phase touched it is usually
the fastest way to find out *why* it's built that way, before assuming
it's a mistake. `docs/decisions/` has the shorter, more permanent
record for the handful of decisions significant enough to warrant a
standalone ADR.

This project was developed with AI assistance (Claude Code) under the
explicit governance of `CLAUDE.md`/`docs/AI_RULES.md` — every commit
required human approval, every merge went through a real PR and CI,
and every non-trivial claim in this project's documentation
(a setting works a certain way, a bug exists, a fix resolves it) was
verified live rather than assumed, with the verification itself
recorded in the relevant phase log. That discipline is worth
continuing for any future work on this codebase, AI-assisted or not.
