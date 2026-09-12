# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Update this file
for meaningful changes — not for every small fix or documentation tweak.

## [Unreleased]

### Added
- Project bootstrap: Django project structure (`config/` settings split,
  `apps/{core,users,crm}`), PostgreSQL as the only database backend.
- Development contract (`CLAUDE.md`), architecture and roadmap
  documentation (`docs/ARCHITECTURE.md`, `docs/ROADMAP.md`).
- AI development governance layer: operational procedures
  (`docs/AI_RULES.md`), permission allowlist (`.claude/settings.json`),
  architectural decision records (`docs/decisions/`), project state
  tracking (`docs/PROJECT_STATE.md`), CI foundation
  (`.github/workflows/ci.yml`, `security.yml`), Dependabot, pre-commit
  configuration.
- CRM database schema and models: Company, Contact, Lead, Deal, Task,
  Activity, with constraints, indexes, and lifecycle behavior documented
  in `docs/DATABASE_DESIGN.md` and audited in `docs/DATABASE_REVIEW.md`.
- CRM interface: authentication, application shell (navigation, error
  pages, styling), create/edit/deactivate workflows for Companies and
  Contacts, create/edit workflows for Leads and Deals (neither is
  deleted or deactivated from the UI), and the Lead-to-Contact/
  Company/Deal conversion workflow.
- Activity timeline: a reusable component on Company/Contact/Lead/Deal
  detail pages for logging and reviewing calls, meetings, emails, and
  notes.
- Tasks: list/detail/create/edit views with status and priority filters,
  "my tasks" and "overdue" views, and a dedicated one-click completion
  workflow.
- Lightweight audit history: records who changed what and when on
  Company/Contact/Lead/Deal, shown as a "History" section on each
  record's detail page.
- Global search across Companies, Contacts, Leads, Deals, and Tasks.
