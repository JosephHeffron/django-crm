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
- [x] **Phase 5 — Search, dashboard, usability.** Global search across CRM
      objects, operational dashboard, a dedicated usability review pass.
      Done in 3 units — full detail in `logs/claude/phase-05-*.md`.
- [x] **Phase 6 — Security hardening.** Full Django security audit
      (`docs/SECURITY_REVIEW.md`), practical role/permission model
      (`docs/PERMISSIONS.md`), dependency security audit
      (`docs/DEPENDENCY_AUDIT.md`). Done in 3 units — full detail in
      `logs/claude/phase-06-*.md`.
- [x] **Phase 7 — Containerization with Podman.** Django production container
      (Gunicorn, non-root), PostgreSQL container with persistent volume,
      complete `podman-compose` configuration. Done in 2 units — full
      detail in `logs/claude/phase-07-*.md`.
- [x] **Phase 8 — Caddy and HTTPS.** Reverse proxy, HTTPS termination, static
      / media file serving, security headers, production configuration review.
- [x] **Phase 9 — ARM64 deployment.** ARM64 compatibility audit
      (`docs/ARM64_REVIEW.md`), ARM64 image builds via `qemu-user-static`,
      repeatable cross-architecture validation (`docs/ARM64_TESTING.md`).
- [x] **Phase 10 — systemd on the Raspberry Pi.** Production systemd unit,
      safe non-destructive deployment script with rollback.
- [x] **Phase 11 — Backups and disaster recovery.** Scheduled PostgreSQL
      backups, a tested restore procedure (`docs/DISASTER_RECOVERY.md`), a
      backup/DR audit.
- [x] **Phase 12 — Logging and monitoring.** Health-check endpoint,
      application logging review (what's logged, what never is).
- [x] **Phase 13 — Final production audit.** Full architecture/security/ARM64
      audit (`docs/PRODUCTION_READINESS.md`), remediation of critical/high
      findings, a clean-environment end-to-end test.
- [x] **Phase 14 — Documentation and handoff.** `docs/ADMIN_GUIDE.md`,
      `docs/DEVELOPER_GUIDE.md`, final repository cleanup. Done in 2
      units — full detail in `logs/claude/phase-14-*.md`.

**This completes the 14-phase roadmap and the project's initial release
scope (see below).**

## Initial release scope

Companies, Contacts, Leads, Deals, Activities, Tasks, Search, Dashboard,
Users/Permissions, Notes. Email integration, calendar integration,
reporting, file attachments, APIs, and mobile-specific functionality are
explicitly deferred until this scope is working reliably on the Raspberry Pi.

## Post-release roadmap (Phase 15+)

The initial release scope above is done. The phases below pick up the
functionality it deliberately deferred, plus hardening work identified
along the way (`docs/PRODUCTION_READINESS.md`'s still-open findings).
Not yet started, not yet ordered by priority beyond the sequence below,
and — per `CLAUDE.md`'s architectural complexity rule — none of them
justify a new infrastructure dependency (Celery, Redis, a JS framework,
etc.) unless a phase's own work demonstrates the simpler approach is
actually insufficient.

- [ ] **Phase 15 — Backup hardening and real hardware validation.**
      Off-host backup storage (closes `docs/PRODUCTION_READINESS.md`'s
      one open HIGH finding), encrypted backup archives, and an actual
      deployment test on physical Raspberry Pi 5 hardware (everything
      ARM64 so far has only been verified under `qemu-user-static`
      emulation).
- [ ] **Phase 16 — Browser-verified security review.** Revisit the CSP
      (Content-Security-Policy) header deferred in
      `docs/PRODUCTION_CONFIG_REVIEW.md`, which needs a real-browser
      check against Django admin's inline scripts to do safely.
- [ ] **Phase 17 — Data portability and bulk operations.** CSV import/
      export for Companies/Contacts/Deals, bulk actions on list views,
      saved/custom list filters, tags/labels, duplicate detection on
      Company/Contact create.
- [ ] **Phase 18 — Attachments and reporting.** File attachments on
      Company/Contact/Lead/Deal records (stored on the existing `media/`
      volume — already backed up, no object storage needed at this
      scale), and a deal forecasting/reporting view (win/loss rate,
      average deal size, sales-cycle length by stage) using plain ORM
      aggregation, matching the existing dashboard's approach.
- [ ] **Phase 19 — Task automation and notifications.** Recurring/
      templated tasks (e.g. one-click "follow up in 7 days"), and a
      daily overdue-task email digest via a systemd timer, matching the
      existing backup timer's pattern.
- [ ] **Phase 20 — Communication integration.** Outbound-only email
      (log as an Activity, send via Django's built-in `django.core.mail`
      — no inbox sync), and an ICS calendar export of Tasks/Deal close
      dates, both intentionally scoped below full two-way sync.
- [ ] **Phase 21 — Authentication hardening.** Two-factor authentication
      for login (e.g. `django-otp`) — a reasonable, well-scoped
      dependency addition given this is a public-facing admin-style
      tool.

**Deliberately not planned, and not a default even after the above:** a
REST API (only justified by a concrete integration need — a mobile
client, Zapier-style automation — not built speculatively) and
multi-tenancy (this is a single self-hosted instance for one business/
household; multi-tenancy would invalidate much of the current
architecture's simplicity and isn't a goal of this project).
