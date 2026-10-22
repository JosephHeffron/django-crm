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
- Three things asked for after using the app: a **New customer**
  button on the task form, so a task for somebody not yet on the
  books no longer means abandoning the form; **address search** on
  the customer list (street, town or postcode, partially) with each
  customer's address shown after their phone; and **booking from the
  schedule** — any day cell on Week or Month opens that day, and a
  day's schedule offers half-hour slots from 6am to 8pm that open the
  job form at that time with two hours booked. A slot that already
  has a job says Busy and still works.

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
  came out of the menu here and stayed reachable by URL until Phase 18
  removed them — see "Leads and Deals are gone", below.
- #sales is readable by the Owner and sales reps only.
- The audit history no longer records fields whose value didn't
  actually change, and records tag changes by name.

### Security
- Pillow upgraded to 13.0.0, which fixes 24 CVEs reported against
  12.3.0. It is what re-encodes every uploaded job photo, and that
  re-encode is what strips the picture's GPS location, so it parses
  attacker-supplied images by design.
- Django upgraded to 6.1.2, a security release (five CVEs, of which
  forging actions in model formsets, `parse_header_parameters` and
  memory exhaustion in `get_supported_language_variant` are reachable
  from this app).
- Job photos and profile pictures are no longer served from disk.
  Everything under `media/private/` now goes through a login-gated
  view that also checks whether the person may see the job or estimate
  the file belongs to — a cleaner sees photos of the jobs they're on
  and no one else's. Before this, anyone with the URL could read them
  without signing in. The reverse proxy refuses the path outright, and
  that refusal is asserted against the configuration Caddy actually
  runs rather than the text of the config file.
- A storage failure no longer looks like a missing photo. A
  permissions problem or a read error raises rather than telling every
  user the photos were never uploaded, and so does a media volume that
  is unmounted or mounted empty: if the directory the photos live in
  isn't there at all, every private file in the system would otherwise
  return "not found" with nothing explaining why. One genuinely missing
  file still returns "not found", and is now logged.

### Changed
- Demo data seeds finished work on the last few weekdays, so Payroll
  and the time clock show a real week instead of being empty until the
  first job of the day ends.
- Demo data now uses real roads in real towns around Rochester with
  made-up house numbers, so the Map page's lookup demonstrates working.
  The previous invented streets could never be found, which read as the
  map being broken. Seeding still never contacts OpenStreetMap.

### Fixed
- Messages read newest-first in every channel, with the box to write in
  above them instead of below.
- The task form asked for a deal. Deals were folded into estimates in
  Phase 17, so that dropdown had been empty ever since; it asks for the
  estimate now. (Tasks still naming an old deal kept it and showed it
  until Phase 18 retired the model; no task in the database named
  one.)
- Customer dropdowns read in the order they are sorted. They were
  already sorted by surname but displayed given names first, so the
  list looked random.
- A task can no longer be saved against an estimate belonging to a
  different customer.
- Moving a job no longer fails on an impossible or offset-carrying
  time. The reschedule endpoint crashed on a value like
  `2026-02-30T09:00` instead of refusing it.
- A customer added from the task form with "Active" unchecked is now
  kept on the task. The page showed them as chosen while the save
  dropped them.
- The drag-and-drop outline on the week and month schedule now shows.
  Its style named a class no page has ever rendered.

### Added
- The Tasks page narrows to one customer, and adding a task from there
  opens the form with that customer already chosen.
- A task shows its customer's phone number and email address, as links
  you can call or write to.
- Customers and Companies can be filtered by town or postal code. A
  company matches when any of its customers has an address there.
- A job can be marked New, In progress or Complete from the day
  schedule and from the job page, without opening the edit form. Crews
  can do this for the jobs they are on.
- Service addresses can be added and corrected in the app. Until now
  they could only be created through the Django admin.
- Booking a job offers a new customer or a new address without losing
  your place: both open their own page and return with the new one
  already chosen.
- The Map page can be searched by customer, street, town or postal
  code, and an address already on the map can be looked up again after
  its street is corrected.
- An address OpenStreetMap cannot find can be pinned by hand, either by
  typing the point or by clicking the map. This was promised by the map
  page but had no way to be done.
- A change log the owner can open, covering every change made in the
  app — jobs, estimates, invoices, payments, expenses, services, tasks,
  customers, companies and addresses — with filters by who made it,
  what kind of record, whether it was created or changed, and when.
  Changes made in the Django admin or by a direct database edit still
  do not appear, which the page says.
- Every form has a Save button at the top as well as the bottom, so a
  long one no longer needs scrolling to save.

### Added
- Before/after photos on a job and reference photos on an estimate,
  taken with the phone's camera. Every photo is re-encoded before it is
  stored, so the location a phone records inside a photo of a
  customer's house never reaches the server. Large photos are scaled
  down, and the right way up is preserved. HEIC photos are refused with
  a note saying which iPhone setting to change.
- An accepted estimate can be scheduled as a job without retyping the
  work: the job form opens with the customer, address, service,
  salesperson and every line of the estimate already filled in. Only
  the time is asked for. The job and the estimate link to each other.
- A job can be moved to another time from the day schedule — a date and
  time box, or back a day, on a day, on a week — and by dragging it on
  the week and month views. A move keeps the job's length and never
  changes whether it is finished.

### Changed
- Leads and Deals are gone from the app. They were folded into
  Customers and Estimates in Phase 17, and their pages, forms and admin
  entries are now removed. `/leads/` and `/deals/` redirect to
  Customers and Estimates; the individual lead and deal pages no longer
  exist. **No data was deleted**: both tables are still in the
  database, untouched, and the change can be undone with a single
  migration command.

### Fixed
- Logging an activity no longer fails after saving it. The page it sent
  you to was built from fields that had been removed, so every logged
  call, email, meeting or note ended in an error even though it had
  been saved.
- Submitting the move form without changing the time, or dragging a job
  back where it started, no longer records a change that did not
  happen.

### Added
- Follow-ups now appear on their own. A daily timer raises them at
  07:00, so a customer who is due for a repeat service turns up on the
  follow-ups list without anyone remembering to look. The generator
  itself has been there since Phase 17; nothing ran it.
- Business plans can be written and edited in the app, and their
  checklists worked through — add a step, tick it off, untick it,
  remove it. Until now a plan could only be created through the Django
  admin.
- Notes can be written in the app, which also was admin-only. From the
  Tasks page for a general note or one about a customer or a job, and
  from a job's own page for the crew working it — so "gate code 4821,
  side entrance" can be left at the kerb, on a phone.
- A job's page now shows notes about the customer as well as notes
  about the job, marked so it is clear which is which. Crews can read
  them, and the note form says so: a note about a customer is readable
  by any crew member assigned to any of that customer's jobs, at any of
  their addresses.
