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
Phases 15-17 are complete. From Phase 17 the roadmap pivots the CRM to
the owner's exterior home-services business (service catalog, quotes,
crew-scheduled jobs, invoicing, follow-up automation, team messaging,
mobile-first PWA) — see `docs/decisions/0008-roles-and-row-level-scoping.md`
and `docs/decisions/0009-field-service-domain-model.md`. The earlier
Phase 17-22 items are folded into the new sequence (noted inline).
Ordered so that Phase 25 (the one item genuinely blocked on hardware
the user doesn't have yet — a physical Raspberry Pi 5) sits last and
gates nothing before it. Per
`CLAUDE.md`'s architectural complexity rule, none of them justify a new
infrastructure dependency (Celery, Redis, a JS framework, etc.) unless
a phase's own work demonstrates the simpler approach is actually
insufficient.

- [x] **Phase 15 — Backup hardening.** Off-host backup storage (closes
      the open backup-storage HIGH finding in
      `docs/PRODUCTION_READINESS.md` — a separate HIGH finding, a
      possibly-stale production `.env` setting, remains outside this
      phase's scope, since resolving it needs direct access to the
      real `.env` file, which policy never grants) and encrypted backup
      archives. Deliberately scoped to a cloud/software-only
      destination — `restic` (client-side encryption by default) or an
      `rclone crypt` remote, not a plain `rclone` copy, which would
      upload `.env`/database credentials to the destination
      unencrypted — rather than a second local drive, so this doesn't
      wait on hardware the user doesn't have yet. Done — the user
      chose Backblaze B2; full detail in
      `logs/claude/phase-15-backup-hardening.md`.
- [x] **Phase 16 — Browser-verified security review.** Revisit the CSP
      (Content-Security-Policy) header deferred in
      `docs/PRODUCTION_CONFIG_REVIEW.md`, which needs a real-browser
      check against Django admin's inline scripts to do safely. Done —
      a headless-Chromium check found zero violations against admin
      and, after a Sourcery-caught fix, the production 500 page too;
      full detail in `logs/claude/phase-16-csp.md`.
- [x] **Phase 17 — Field-service foundation.** Three units: (1) design
      system, mobile-first app shell, Owner / Sales Rep / Cleaner roles
      enforced server-side, PWA baseline; (2) data model (service
      catalog, properties, quotes, jobs, crews, invoices, messaging),
      Lead → Contact / Deal → Quote data migration, follow-up
      generator, `seed_demo` command; (3) every page — Dashboard,
      Financials, Calendar, Contacts, Tasks hub, Profile, Messages — on
      seeded data. Done across PRs #90–#104 (unit 2 and unit 3 each
      split into smaller PRs to stay reviewable); full detail in
      `logs/claude/phase-17-*.md`.
- [ ] **Phase 18 — Quotes and jobs workflow.** Quote builder (catalog
      line items, photos), status transitions, accepted quote → job,
      scheduling and crew assignment, calendar drag-to-reschedule (with
      a non-drag alternative), before/after camera photo upload with
      login-gated serving, and removal of the retired Lead/Deal models.
      (Absorbs the earlier "attachments" item.)
- [ ] **Phase 19 — Follow-up automation and tasks hub.** Daily
      follow-up generation via a systemd timer (same pattern as the
      backup timer), per-service intervals, completion logging a
      contact touch, business-plan checklists, notes. (Absorbs the
      earlier "task automation" item.)
- [ ] **Phase 20 — Invoicing and financials.** Invoices from completed
      jobs, payments, expenses, the Owner-only Financials page
      (daily/weekly/monthly/YTD, by service and by rep, server-rendered
      SVG charts), profile stats hardening. (Absorbs the earlier
      "reporting" item.)
- [ ] **Phase 21 — Messaging live delivery and PWA polish.** Short
      polling for new messages (no Redis/WebSockets — see the Phase 17
      plan), unread badges, job/contact references in the composer,
      offline fallback and install experience.
- [ ] **Phase 22 — Data portability and bulk operations.** CSV import/
      export, bulk actions on list views, saved filters, duplicate
      detection on Contact create. (Formerly Phase 17.)
- [ ] **Phase 23 — Authentication hardening.** Two-factor authentication
      for login (e.g. `django-otp`). (Formerly Phase 21.)
- [ ] **Phase 24 — Customer communication (future).** Customer SMS via
      Twilio on top of the messaging model (designed for it in Phase
      17), outbound email logged as an Activity, ICS calendar export.
      (Absorbs the earlier "communication integration" item.)
- [ ] **Phase 25 — Real Raspberry Pi hardware validation.** Blocked —
      no physical Raspberry Pi 5 acquired yet. Everything ARM64-related
      so far has only been verified under `qemu-user-static` emulation
      (`docs/ARM64_REVIEW.md`/`docs/ARM64_TESTING.md`), which proves
      ABI compatibility but not real-world performance (SD card I/O,
      thermal throttling, gunicorn worker tuning). Deliberately placed
      last and not a prerequisite for anything above. (Formerly Phase
      22.)

**Deliberately not planned, and not a default even after the above:** a
REST API (only justified by a concrete integration need — a mobile
client, Zapier-style automation — not built speculatively) and
multi-tenancy (this is a single self-hosted instance for one business/
household; multi-tenancy would invalidate much of the current
architecture's simplicity and isn't a goal of this project).
