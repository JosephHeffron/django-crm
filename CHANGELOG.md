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
