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
- Operational dashboard: quick counts, an open-deal pipeline breakdown
  by stage, the signed-in user's own pending tasks, and a recent-
  activity feed — plain server-side ORM aggregates, no charting
  library.
- Usability review and fixes (`docs/USABILITY_REVIEW.md`): accessible
  form labels, a Cancel link on every create/edit form, a current-page
  navigation indicator, and a real bug fix (multi-line template
  comments rendering as literal text on every detail page).
- Security audit and hardening (`docs/SECURITY_REVIEW.md`):
  `manage.py check --deploy` clean, `CSRF_COOKIE_HTTPONLY`, a stronger
  password minimum.
- Role/permission model (`docs/PERMISSIONS.md`): a "Staff" group
  gating create/edit/deactivate/complete/convert actions across all
  six CRM models; superusers bypass automatically; visibility remains
  unrestricted.
- Dependency security audit (`docs/DEPENDENCY_AUDIT.md`) and a cleared
  backlog of Dependabot PRs.
- Production containerization: a non-root Django/Gunicorn image
  (`Containerfile`), a PostgreSQL container with persistent storage,
  and `podman-compose` configurations for local/staging
  (`compose.dev.yml`) and production (`compose.prod.yml`).
- Caddy reverse proxy and HTTPS termination (`Caddyfile`/
  `Caddyfile.dev`): automatic HTTPS in production, static/media file
  serving, security headers.
- Production configuration review (`docs/PRODUCTION_CONFIG_REVIEW.md`)
  — found and fixed a real bug where a stale `.env.example` line could
  have silently put a real deployment into `DEBUG=True`.
- ARM64 (Raspberry Pi 5) compatibility, verified via `qemu-user-static`
  emulation (`docs/ARM64_REVIEW.md`, `docs/ARM64_TESTING.md`,
  `scripts/test-arm64.sh`, a repeatable, self-verifying build-and-run
  check).
- Production systemd unit (`systemd/crm.service`) running rootless
  Podman under a dedicated user's systemd session
  (`docs/decisions/0005-rootless-systemd-deployment.md`), and a
  deployment script with automatic health-check-triggered rollback
  (`scripts/deploy.sh`).
- Scheduled PostgreSQL backups (`scripts/backup.sh`,
  `systemd/crm-backup.{service,timer}`) and a tested disaster recovery
  restore procedure (`scripts/restore.sh`,
  `docs/DISASTER_RECOVERY.md`), audited in
  `docs/BACKUP_DR_AUDIT.md`.
- A `/health/` endpoint checking real database connectivity, and a
  fix for a real gap where production silently logged unhandled
  exceptions nowhere at all (`docs/LOGGING_REVIEW.md`).
- Final production readiness audit (`docs/PRODUCTION_READINESS.md`) —
  found and fixed a real gap where GitHub branch protection and secret
  scanning had been silently disabled since the repository switched to
  private.
- A clean-environment end-to-end test (`docs/CLEAN_ENVIRONMENT_TEST.md`)
  against a genuine fresh clone — found and fixed a real bug in the
  backup/restore scripts' handling of the local/staging compose file.
- Administrator and developer guides (`docs/ADMIN_GUIDE.md`,
  `docs/DEVELOPER_GUIDE.md`).
- Mobile-first app shell (sidebar / drawer / phone bottom bar) on a
  tokenized design system with light and dark themes, and an
  installable PWA baseline (manifest, service worker, offline page) —
  Phase 17 unit 1.
- Field-service domain (Phase 17 unit 2): a service catalog with
  per-service prices, follow-up intervals, and calendar colors;
  properties (service addresses), tags, notes, and business plans;
  quotes, crew-assigned jobs, invoices, payments, and expenses with
  computed totals; team messaging built so customer texting can be
  added later; per-role permissions and row-level scoping.
- Repeat-service follow-ups: a `generate_followups` command creates a
  follow-up task when a customer hasn't had a service, or been in
  touch, within that service's interval; completing one logs the
  check-in. `seed_demo` fills a development database with a realistic
  year of demo data.
- Field-service pages (Phase 17 unit 3): a role-aware dashboard; a
  day / week / month calendar; job and quote pages; the Owner's
  service catalog and Financials (revenue, collected, expenses, net,
  breakdowns by service and rep, outstanding balances aged by
  lateness, a trend chart); contacts with lead/customer stages,
  last-job and last-contact dates, and one timeline per customer; a
  Tasks hub (tasks, follow-ups, quotes, plans, notes); team channels
  and private direct messages with unread counts; profiles with
  per-role stats and an Owner team view. Search also finds contacts
  by phone and jobs/quotes by number.

### Changed
- Access control is now role-based: Owner, Sales Rep, and Cleaner
  groups, enforced server-side, replace the Phase 6 "Staff" group and
  its implicit read-only tier. Existing Staff members become Sales
  Reps; users with no role are denied customer pages
  (`docs/decisions/0008-roles-and-row-level-scoping.md`).
- Default timezone is now the business's local time
  (`America/New_York`, configurable via `CRM_TIME_ZONE`).
- Leads are now Contacts with the "Lead" stage and Deals are now
  Quotes (a reversible data migration). The old Lead and Deal pages
  are out of the menu but still open by URL until Phase 18 removes
  them.
- #sales is readable by the Owner and sales reps only.
- The audit history no longer records fields whose value didn't
  actually change, and records tag changes by name.

### Security
- Job photos and profile pictures are no longer served from disk.
  Everything under `media/private/` now goes through a login-gated
  view that also checks whether the person may see the job or estimate
  the file belongs to — a cleaner sees photos of the jobs they're on
  and no one else's. Before this, anyone with the URL could read them
  without signing in. The reverse proxy refuses the path outright, and
  that refusal is asserted against the configuration Caddy actually
  runs rather than the text of the config file.
- A storage failure no longer looks like a missing photo. Only a file
  that is genuinely gone returns "not found"; a permissions problem or
  an unmounted media volume raises instead of telling every user the
  photos were never uploaded.
