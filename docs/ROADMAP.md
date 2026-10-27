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
Phase 19.5, three more reported the same way. **Phase 22.5 — going
live on a VPS, with a public website — is next**, and it changes the
deployment target: the business is moving off RevDek and Wix onto one
x86-64 VPS, so Phase 25's Raspberry Pi validation is superseded
rather than merely deferred.
From Phase 17 the roadmap pivots the CRM to
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
- [ ] **Phase 22.5 — Production on a VPS, and a public website.**
      Not a feature phase: this is the business actually using the
      thing. Heffron Exterior Services is cancelling RevDek ($85/month)
      and replacing the Wix site, with both the CRM and a static
      website on one x86-64 Ubuntu VPS —
      `crm.heffronexteriorservices.com` for the CRM, the apex and
      `www` for the website. Numbered 22.5 for the same reason as 18.5
      and 19.5: it cuts across the phases rather than belonging to one.

      Audited before planning, and the audit found the codebase
      architecturally ready but the surroundings not
      (`docs/VPS_AUDIT.md`): rootless Caddy cannot bind 80/443 without
      a sysctl nothing in the repo sets, there is no in-app way to
      create a user, no password reset, no outbound email of any kind,
      and `scripts/restore.sh` has still never run end to end. The
      plan is `docs/VPS_DEPLOYMENT_PLAN.md`, with
      `docs/VPS_PLAN_SUMMARY.md` as the owner's one-pager.

      Seven units, in this order — the first three cannot affect the
      website or the domain, which is the point of the sequence:
      1. **P0 repo fixes** — outbound email, in-app team member
         creation (Owner-only), password reset, an Ubuntu x86-64
         deployment guide, and alerting for a backup that stops
         running.
      2. **VPS provisioning** — the owner's own work, following that
         guide.
      3. **CRM live on `crm.`** — HTTPS, backups to B2, uptime
         monitoring, staff accounts, and **the restore drill before
         any real data exists**.
      4. **Website build** — static HTML/CSS/JS in a top-level
         `website/` folder in this repository, mounted read-only into
         Caddy and served by a second site block. The booking page
         shares the site's stylesheet and header/footer partials
         rather than duplicating them, CI keeps the required checks
         reporting on website-only PRs, and a guard keeps private data
         out of a folder that is published the moment it is committed.
      5. **Website → CRM** — one public booking page, `/book/`, served
         by Django on the website's own origin, creating a `Contact`
         with `status=lead` and `lead_source=website`. No API, no DRF,
         no CORS.
      6. **DNS cutover** of the apex and `www`.
      7. **Retirement** — export RevDek for records, cancel it, then
         cancel Wix. In that order, and Wix last: it is both the
         registrar and the DNS host, so cancelling it early takes the
         domain down.

      Six ADRs will be written as their units start: 0015 (x86-64 VPS
      replaces the Pi), 0016 (two sites behind one Caddy), 0017 (the
      website lives in this repository, with the mounts, deploy, CI
      filter and private-data guard that implies), 0018 (same-origin
      lead intake at `/book/`), 0019 (email via the existing Gmail
      account), 0020 (database-backed cache for rate limiting instead
      of Redis). ADRs 0004, 0005, 0006, 0007 and 0011 all stand
      unchanged, and ADR 0014's retirement of team messaging is not
      reopened by any of this.
- [ ] **Phase 23 — Authentication hardening.** Two-factor authentication
      for login (e.g. `django-otp`). (Formerly Phase 21.)
- [ ] **Phase 24 — Customer communication (future).** Customer SMS via
      Twilio on top of the messaging model (designed for it in Phase
      17), outbound email logged as an Activity, ICS calendar export.
      (Absorbs the earlier "communication integration" item.)
- [ ] **Phase 25 — Real Raspberry Pi hardware validation.**
      **Superseded by Phase 22.5**, which moves the deployment target
      to an x86-64 VPS; ADR 0015 will record that. Kept rather than
      deleted because nothing about the Pi work was wrong, and because
      the ARM64 compatibility it proved still holds — the plan's audit
      confirmed nothing in the build is ARM-specific. Reopen only if a
      Pi is ever actually deployed. Originally: blocked —
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
