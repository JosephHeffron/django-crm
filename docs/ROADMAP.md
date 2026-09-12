# Roadmap

Development proceeds in small, reviewable phases. Each phase ends with
passing tests, updated documentation, and a commit before the next phase
begins. See `CLAUDE.md` for the workflow this repository follows.

- [x] **Phase 0 — Development rules.** `CLAUDE.md`, git baseline, `.gitignore`,
      this roadmap, `docs/ARCHITECTURE.md`.
- [x] **Phase 1 — Bootstrap Django.** `config/`/`apps/` project structure,
      environment-based settings split, PostgreSQL wired up, dependency
      management, project boots and passes `manage.py check`.
- [x] **Phase 2 — Database design.** Design Companies/Contacts/Leads/Deals/
      Activities/Tasks/Notes relationships in `docs/DATABASE_DESIGN.md` before
      writing models (done); implement models + migrations + admin
      registration (done); schema review in `docs/DATABASE_REVIEW.md`
      (done — found 2 HIGH + 5 MEDIUM findings on Activity's CASCADE
      behavior and on_delete enforcement; tracked in
      `docs/PROJECT_STATE.md`'s Known Issues, to be resolved before
      Phase 4, not blocking this phase or Phase 3).
- [x] **Phase 3 — CRM interface.** Application shell (nav, layout, base
      templates, messages, error pages), then Companies and Contacts CRUD,
      then Leads and Deals workflows. Done in 5 units — full detail in
      `logs/claude/phase-03-*.md`.
- [x] **Phase 4 — Activities, notes, tasks, history.** Activity timeline
      component, Tasks (my tasks / overdue / completion workflow), lightweight
      audit history for important record changes. Done in 3 units — full
      detail in `logs/claude/phase-04-*.md`.
- [ ] **Phase 5 — Search, dashboard, usability.** Global search across CRM
      objects, operational dashboard, a dedicated usability review pass.
- [ ] **Phase 6 — Security hardening.** Full Django security audit
      (`docs/SECURITY_REVIEW.md`), practical role/permission model
      (`docs/PERMISSIONS.md`), dependency security audit.
- [ ] **Phase 7 — Containerization with Podman.** Django production container
      (Gunicorn, non-root), PostgreSQL container with persistent volume,
      complete `podman-compose` configuration.
- [ ] **Phase 8 — Caddy and HTTPS.** Reverse proxy, HTTPS termination, static
      / media file serving, security headers, production configuration review.
- [ ] **Phase 9 — ARM64 deployment.** ARM64 compatibility audit
      (`docs/ARM64_REVIEW.md`), ARM64 image builds via `qemu-user-static`,
      repeatable cross-architecture validation (`docs/ARM64_TESTING.md`).
- [ ] **Phase 10 — systemd on the Raspberry Pi.** Production systemd unit,
      safe non-destructive deployment script with rollback.
- [ ] **Phase 11 — Backups and disaster recovery.** Scheduled PostgreSQL
      backups, a tested restore procedure (`docs/DISASTER_RECOVERY.md`), a
      backup/DR audit.
- [ ] **Phase 12 — Logging and monitoring.** Health-check endpoint,
      application logging review (what's logged, what never is).
- [ ] **Phase 13 — Final production audit.** Full architecture/security/ARM64
      audit (`docs/PRODUCTION_READINESS.md`), remediation of critical/high
      findings, a clean-environment end-to-end test.
- [ ] **Phase 14 — Documentation and handoff.** `docs/ADMIN_GUIDE.md`,
      `docs/DEVELOPER_GUIDE.md`, final repository cleanup.

## Initial release scope

Companies, Contacts, Leads, Deals, Activities, Tasks, Search, Dashboard,
Users/Permissions, Notes. Email integration, calendar integration,
reporting, file attachments, APIs, and mobile-specific functionality are
explicitly deferred until this scope is working reliably on the Raspberry Pi.
