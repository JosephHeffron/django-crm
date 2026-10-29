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
Phases 15-22 are complete. Phase 18.5, twelve items the
owner reported after testing the running app, is complete, as is
Phase 19.5, three more reported the same way. **Phase 22.5 (VPS
deployment) is next**, then Phase 23 (two-factor authentication) and
Phase 23.5 (public website and booking requests).

**Deployment target changed (2026-10).** The owner has dropped the
Raspberry Pi 5 in favour of a DigitalOcean VPS (2 vCPU, 4 GB, Ubuntu
24.04 LTS, x86-64), with DNS on Cloudflare and notifications from the
business's existing free Gmail account. Phase 25 (Pi hardware
validation) is withdrawn as a result, and Phases 22.5 and 23.5 are
inserted. They are numbered like 17.5 and 18.5 so existing references
to Phases 23 and 24 stay valid. The change of target is recorded here
as intent only. Per `CLAUDE.md`, the ADR that makes it a decision is
the first deliverable of Phase 22.5, and `CLAUDE.md`,
`docs/ARCHITECTURE.md` and `docs/ADMIN_GUIDE.md` still describe the Pi
until that ADR lands.
From Phase 17 the roadmap pivots the CRM to
the owner's exterior home-services business (service catalog, quotes,
crew-scheduled jobs, invoicing, follow-up automation, team messaging,
mobile-first PWA) — see `docs/decisions/0008-roles-and-row-level-scoping.md`
and `docs/decisions/0009-field-service-domain-model.md`. The earlier
Phase 17-22 items are folded into the new sequence (noted inline).
Phase 25 was originally placed last because it was blocked on hardware
the user didn't have (a physical Raspberry Pi 5). It is now withdrawn;
see its entry. Per
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
- [x] **Phase 17.5 — UI restyle (complete).** Match the owner's reference design
      (ADR 0010): new tokens (Inter, rounded cards, pill buttons, accent
      colors, persisted dark mode), shared components, a floating
      sidebar with flyouts (Customers, Crew, Job, Finance), a top bar
      with ⌘K search / Create / notifications / settings gear, and
      restyled or new pages — Dashboard, Scheduling, Estimates,
      Finance (Invoices, Payments, Expenses, Profit), Crew (Time clock,
      Assignments, Payroll, Performance), Map on OpenStreetMap
      (ADR 0011), Reports, and Settings (Business, Account, Company
      Management, Customize, What's New). Features the design needs
      that the CRM lacks are built for real (business settings,
      currency, notifications, goals, time clock, pay rates,
      indicators, map pins, member access, activity log with undo, CSV
      export) or shown as "not available yet"; subscription-only
      screens are skipped. Numbered 17.5 so existing Phase 18+
      references stay valid. Before Phase 18, so its forms are built in
      the new style. Done in eleven steps; full detail in
      `logs/claude/phase-17.5-step*.md`.
- [x] **Phase 18 — Quotes and jobs workflow.** Complete. Quote builder
      (catalog line items, photos), status transitions, accepted quote →
      job, scheduling and crew assignment, calendar drag-to-reschedule
      (with a non-drag alternative), before/after camera photo upload
      with login-gated serving, and removal of the retired Lead/Deal
      models. (Absorbs the earlier "attachments" item.) Five units.
      - [x] Unit 1 — login-gated serving of everything under
            `media/private/`, and the reverse proxy refusing the path
            (PR #130).
      - [x] Unit 2 — before/after photos on a job and reference photos
            on an estimate, through the phone's camera; every upload
            re-encoded so the GPS coordinates a phone writes into a
            photo of a customer's house never reach storage, which
            ADR 0009 promised and nothing had implemented (PR #148).
      - [x] Unit 3 — an accepted estimate opens the job form with the
            customer, address, service, salesperson and every line of
            work already filled in; only the time is asked for, because
            only a person knows it (PR #149).
      - [x] Unit 4 — moving a job to another time: move controls on the
            day schedule that work with no JavaScript as the baseline,
            with dragging a chip on the week and month views built on
            the same endpoint. A move keeps the job's length and never
            touches its completion date (PR #150).
      - [x] Unit 5 — the retired Lead and Deal models removed, with
            their tables deliberately kept: `crm/0011` is state-only
            and runs no SQL (ADR 0012). Fixed a live 500 on every
            logged activity, and a migration-ordering fault that would
            have broken every build of a fresh database (PR #151).
- [x] **Phase 18.5 — Owner-requested fixes.** Complete: all twelve
      items reported
      after testing the running app, cutting across Phases 18, 19 and
      21, so tracked as their own group rather than folded in. Six
      units: the inbox and task form; task context and an address
      filter; quick-add customer/address and job status from the
      schedule; map search and demo addresses that geocode; the master
      change log; a save button at the top of every form.
      - [x] Unit 1 — inbox newest-first with the compose box at the
            top, estimates instead of the retired deal field on the
            task form, customer dropdowns reading "Adams, Daniel", and
            the project's only inline style removed (PR #133).
      - [x] Unit 2 — the Tasks hub narrows to a customer and its Add
            task button carries them, the customer's phone and email
            show on tasks, and Customers and Companies filter by town
            or postcode (PR #135).
      - [x] Unit 3 — jobs can be marked New / In progress / Complete
            from the day schedule and the job page, through one shared
            rule that stamps the completion date; plus the service
            address form the app never had, and quick-add of a customer
            or address from the job form (PR #137).
      - [x] Unit 4 — the Map page gains a search, re-lookup for an
            address already placed, and the pin-drop ADR 0011 promised
            but nothing could reach; the seed uses real roads in real
            towns so a lookup demonstrates working (PR #139).
      - [x] Unit 5 — change-recording extended from four CRM models to
            everything the app writes, with filters by person, record
            type, action and date, its own Owner-only tab, and undo
            held to an explicit allow-list (PR #144).
      - [x] Unit 6 — a Save button in the header of all fourteen record
            forms, reaching its form through the HTML `form` attribute,
            so no JavaScript and no CSP change (PR #146).

- [x] **Phase 19 — Follow-up automation and tasks hub.** Complete.
      Daily follow-up generation via a systemd timer (same pattern as
      the backup timer), per-service intervals, completion logging a
      contact touch, business-plan checklists, notes. (Absorbs the
      earlier "task automation" item.) Three units.

      **Read this before trusting a roadmap entry.** A verification
      pass ran first, and found this entry described intent rather than
      delivery. Of the five items above: generation and
      completion-logging were built and tested in Phase 17; per-service
      intervals were built but **unasserted** — every existing test
      used one service at six months, so hard-coding `6` passed all 14
      of them; and business-plan checklists and notes were **not built
      at all**, only displayed, with the Django admin the only way to
      create either. The phase read as nearly done and was about half
      done. Phase 18's close-out needed the same check, which makes
      this a pattern rather than an incident.
      - [x] Unit 1 — `scripts/followups.sh` and `crm-followups.timer`
            raise the day's follow-ups at 07:00 daily. The command had
            existed since Phase 17 with nothing to run it. Also added
            the six tests that make per-service intervals real
            (PR #154).
      - [x] Unit 2 — plans can be created and edited in the app, and
            their checklists worked through: add a step, tick it,
            untick it, remove it, one POST per step (PR #155).
      - [x] Unit 3 — notes can be written: from the Tasks hub by sales
            and the owner, and from a job's own page by the crew
            working it — the row-scoped path `users/0004` has promised
            since Phase 17 and nothing had built (PR #156).
- [x] **Phase 19.5 — Owner-requested usability fixes.** Complete:
      three items the owner reported after using the running app.
      Numbered like Phase 18.5 and for the same reason — they cut
      across phases (the task form, the customer list, the schedule)
      rather than belonging to one, so they are tracked as their own
      group instead of folded in. Three units, three PRs.
      - [x] Unit 1 — a **New customer** button on the task form, so a
            task for somebody not yet on the books no longer means
            abandoning the form. Create-only: on the edit form the
            round trip would come back showing the old customer, so
            the button would appear to do nothing (PR #164).
      - [x] Unit 2 — **address search** on the customer list (street,
            town or postcode, partially — the box it replaced needed
            the whole postcode exactly), with each customer's address
            shown after their phone. Added as a third filter on the
            same queryset, not a second subquery, so one address has
            to satisfy everything asked (PR #165).
      - [x] Unit 3 — **booking from the schedule**: any day cell on
            the week or month view opens that day, and a day's
            schedule offers half-hour slots from 6am to 8pm that open
            the job form at that time with two hours booked. A slot
            already covered says Busy and still books, because two
            crews can be out at once (PR #166).

      **Sourcery found a real bug in each of the three**, every one
      after CI was green: a customer added with "Active" unchecked was
      shown as chosen and then dropped by the save; the retired
      postcode box kept filtering invisibly and was discarded on the
      next submit; and the indicator dots left a dead patch in the
      middle of a cell built to be clickable. Each unit's log has the
      detail. Two live bugs in existing code were fixed on the way —
      a 500 on the reschedule endpoint and a drag outline whose CSS
      named a class no page has ever rendered.

- [x] **Phase 20 — Money: payment on the job, revenue from finished
      work.** Complete, and **not what this entry originally said.**

      The entry read "Invoices from completed jobs, payments, expenses,
      the Owner-only Financials page (daily/weekly/monthly/YTD, by
      service and by rep, server-rendered SVG charts), profile stats
      hardening". A verification pass found most of that already built
      and genuinely tested — the presets, the custom range, the
      Owner-only gate, the charts, the breakdowns — with four figures
      unasserted, and the profile stats delivered separately as the
      role stats sheet (#158).

      It also found what no mutation could: **every revenue figure came
      from sent invoices, and `Payment.invoice` was required**, so a
      business that takes payment before completion and issues no
      invoices would see zero revenue and have nowhere to record the
      money. "Invoices from completed jobs" was never implemented
      either, and should not be: the owner does not invoice.

      `docs/decisions/0013-payment-on-the-job-revenue-from-completed-work.md`
      records the decision. Four units:
      - [x] Unit 0 — the four unasserted figures guarded, and the ADR
            written (#171).
      - [x] Unit 1 — `Payment.job` required, `Payment.invoice`
            optional, money recorded from the job page (#172).
      - [x] Unit 2 — revenue is the work you finish, dated by
            `completed_at`, everywhere a figure is shown — including
            the monthly goal (#173).
      - [x] Unit 3 — outstanding is finished work nobody has paid for,
            aged by how long ago it was finished (#174).
      - [x] Unit 4 — the demo seed takes payment the way the business
            does, and the documents describe the model that shipped.

      **Invoices are kept and demoted**, not deleted: they drive no
      figure, and remain for the customer who asks for one.
- [x] **Phase 21 — PWA polish. Messaging retired instead.** Complete,
      and most of it was deleted rather than built.

      The entry asked for short polling, unread badges, job/contact
      references in the composer, offline fallback and install
      experience. A verification pass measured each: the **badges**
      were built and well asserted; the reference **display** was
      built and asserted (a customer's timeline, a job link on a
      message) but **nothing in the app could set a reference** — the
      composer was one body field, so the Django admin was the only
      way in; **polling** was never started, which the module
      docstring said; and the **offline fallback and install
      experience** were built, with three behaviours unasserted until
      this pass (the offline page actually reaching the cache, the
      cache name tracking the asset version, and old caches being
      cleaned up — each could be removed with the whole suite green).

      The owner then said the inbox and messaging pages were no longer
      needed, so the first three items are moot and the feature is
      retired **code-only, tables kept**
      (`docs/decisions/0014-retire-team-messaging-code-only.md`), the
      same shape ADR 0012 used for Lead and Deal. Every page gets one
      query cheaper: the unread badge ran on every render for every
      logged-in user.

      Customer texting (Phase 24) still stands and still has the
      models to build on.
- [x] **Phase 22 — Data portability and bulk operations.** CSV import/
      export, bulk actions on list views, saved filters, duplicate
      detection on Contact create. (Formerly Phase 17.) Done, with one
      item declined and one added:
      - CSV **export** already existed (`apps/core/export.py`); the
        verification pass mutation-tested it and found two real gaps,
        fixed in PR #179.
      - CSV **import** of a customer list, Owner-only beside the
        export, reading the same column names it writes (PR #182).
      - **Bulk actions** on the customer and task lists — tag,
        deactivate, reactivate, complete, cancel (PR #181).
      - **Duplicate detection** on Contact create: warns, never blocks
        (PR #179).
      - **Saved filters: declined by the owner on 2026-10-27**, before
        any code existed — "skip save filters, this is not needed". No
        ADR, because nothing was built or removed; this entry is the
        record. The design is in that session's transcript if it is
        ever wanted.
      - **Added, not from this entry:** a search box above the job
        form's customer dropdown (PR #180), asked for by the owner
        after hitting it in use.
      Full detail in `logs/claude/phase-22-data-portability.md`.
- [ ] **Phase 22.5 — VPS deployment.** Move the target from the
      Raspberry Pi to a DigitalOcean VPS and take the CRM live at
      `crm.heffronexteriorservices.com`. Before any code, run an audit:
      read the existing audits (`docs/PRODUCTION_READINESS.md`,
      `docs/SECURITY_REVIEW.md`, `docs/BACKUP_DR_AUDIT.md`,
      `docs/PRODUCTION_CONFIG_REVIEW.md`, `docs/ARM64_REVIEW.md`) and
      re-verify the claims that matter for an x86-64 Ubuntu host,
      rather than redoing them. Expected units, to be confirmed by that
      audit:
      - **ADR first:** the change of target, superseding the Pi
        assumptions in `CLAUDE.md`, `docs/ARCHITECTURE.md` and
        `docs/ADMIN_GUIDE.md`.
      - **A VPS setup guide:**
        - deploy user and SSH keys only
        - firewall allowing 22/80/443 only
        - swap
        - timezone, since the follow-up timer fires at 07:00 server
          time
        - `net.ipv4.ip_unprivileged_port_start=80`, so rootless Caddy
          can bind 80/443; nothing in the repo sets it today
      - **Pi-specific leftovers:** worker-count comments,
        `scripts/test-arm64.sh`.
      - **Staff onboarding without the Django admin:** an in-app "add
        team member" page and email password reset. Today both need
        `/admin/`.
      - **Outbound email from the business's Gmail account.** Choose
        between SMTP with an app password and the Gmail API. Check
        first whether DigitalOcean blocks outbound SMTP ports on new
        Droplets.
      - **Go-live:**
        - HTTPS
        - restic backups to B2
        - **the full `scripts/restore.sh` drill on the VPS before real
          data goes in**, which closes the oldest open known issue
        - uptime monitoring on `/health/`
- [ ] **Phase 23 — Authentication hardening.** Two-factor authentication
      for login (e.g. `django-otp`). (Formerly Phase 21.) More urgent
      once the CRM is on the public internet, so it runs straight after
      Phase 22.5. The ADR must settle how a locked-out owner recovers
      on a single-owner install with no support desk.
- [ ] **Phase 23.5 — Public website and booking requests.** Replace the
      Wix site with a static HTML/CSS/JS site in a top-level `website/`
      folder of this repository, served by the existing Caddy on
      `heffronexteriorservices.com` and `www.`. No framework, no CMS,
      no second backend. Expected units:
      - **ADR first:** the public website in this repo; the Caddyfile
        moving from one `{$DJANGO_ALLOWED_HOSTS}` site address to
        several, keeping the `/media/private/*` 404 and every existing
        header.
      - **The site itself,** rebuilt from the Wix content, mobile-first
        and SEO-friendly.
      - **A booking request form at `/book/` on the public domain:**
        - rendered by Django, so normal CSRF protection applies, with
          no REST API and no CORS
        - no customer account and no photo uploads
        - spam protection, and a rate limit shared across gunicorn
          workers
      - **What a request creates:** a `Contact` with `status = lead`
        and `lead_source = website`, plus a pending appointment request
        with a preferred date and an optional time window.
        - It is never auto-confirmed: staff approve, decline or
          reschedule it in the CRM.
        - Approving opens a pre-filled job, the way an accepted
          estimate does.
        - The customer gets "received" and "confirmed" emails.
      - **DNS:** move to Cloudflare with the Wix site still live, cut
        over the apex and `www`, and keep a rollback path.
      - **Retirement:** archive RevDek's data (for records, not
        import), then cancel RevDek and Wix only after the above is
        verified.

      Not in this phase: the website marking time slots unavailable
      automatically. That needs business hours, service durations and
      a capacity rule, none of which the CRM has yet.
- [ ] **Phase 24 — Customer communication (future).** Revised
      2026-10:
      - appointment reminder emails from the business Gmail account,
        logged as an Activity (confirmation emails arrive in Phase
        23.5)
      - ICS calendar export
      - customer SMS only if the owner decides it is worth a paid
        provider (e.g. Twilio)

      The messaging tables kept by ADR 0014 remain the place SMS would
      build on. (Absorbs the earlier "communication integration" item.)
- [ ] ~~**Phase 25 — Real Raspberry Pi hardware validation.**~~
      **Withdrawn 2026-10:** the deployment target is now an x86-64
      VPS (Phase 22.5), so there is no Pi to validate. The ARM64 work
      (`docs/ARM64_REVIEW.md`/`docs/ARM64_TESTING.md`) stays as a
      record, and stays relevant only if the app ever moves to ARM
      hosting.

**Not yet scheduled, worth their own units:**
- **Booking from a crew-filtered schedule assigns that crew.**
  `JobCreateView` ignores `?crew=` today; see `docs/PROJECT_STATE.md`.
- **Run the suite under a pinned and a shifted clock in CI.** Four
  time-dependent test failures so far; see `docs/PROJECT_STATE.md`.
- **The website showing open slots automatically,** after Phase 23.5.

**Deliberately not planned, and not a default even after the above:** a
REST API (only justified by a concrete integration need — a mobile
client, Zapier-style automation — not built speculatively) and
multi-tenancy (this is a single self-hosted instance for one business/
household; multi-tenancy would invalidate much of the current
architecture's simplicity and isn't a goal of this project).
