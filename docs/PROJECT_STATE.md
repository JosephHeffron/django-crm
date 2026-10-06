# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

> **Last updated 2026-10-06.** Repo is clean (`main` up to date, nothing
> uncommitted). The original 14-phase roadmap is fully complete (see
> "Project complete" below). The post-release roadmap
> (`docs/ROADMAP.md`'s "Phase 15+") is now underway: **Phase 15
> (Backup hardening)'s off-host, encrypted backup mechanism** — `restic`,
> the user's chosen destination being Backblaze B2 — **is implemented
> and live-verified** (real B2 account/bucket/key creation remains the
> deploying operator's own step, not further code). **Phase 16
> (browser-verified CSP review) is also complete** — a headless-Chromium
> check found zero violations, including after a real Sourcery-caught
> bug (an un-nonced inline style on the production 500 page) was fixed.
> Phase 17 (field-service foundation) is complete. Phase 17.5 (UI restyle) is complete — all 11 steps done.
> **Phase 18 (quotes and jobs workflow) is underway: unit 1 (private
> media) is merged** (PR #130, 815 tests). It closed a live exposure —
> job photos and profile pictures under `media/private/` were served
> straight from disk by Caddy and readable by anyone with the URL.
> Worth reading the phase log before trusting a config test: the first
> fix did not work and the test guarding it passed anyway, twice, for
> the same reason (it searched the Caddyfile's text instead of the
> configuration Caddy actually runs).
> Note: the GitHub repo, switched from public to private earlier in the
> project, is now **public again** — Phase 13 unit 1's audit found
> branch protection and secret scanning had been silently disabled
> while private (both are gated behind GitHub Pro on the free plan);
> the user chose to go public again rather than pay for Pro, and both
> protections are restored. Sourcery's automated review is available
> again as a result — after hitting its free-tier review-budget limit
> on a couple of PRs around Phase 14, it delivered real, substantive
> findings on every PR through Phase 16, several of them genuine bugs
> this project's own testing hadn't caught. It skipped PR #90 (Phase 17
> unit 1) entirely — the diff exceeded its 150,000-character limit — so
> that PR was self-reviewed instead; large units should be split to
> stay under that limit.

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

The original 14-phase roadmap (Phases 0-14) is fully complete — see
"Project complete," below, for the summary, and "Completed" for full
phase-by-phase detail. The post-release roadmap is now underway:
Phases 15-17.5 are complete and Phase 18 is underway — see
"Post-release roadmap progress,"
below, for current status. This section deliberately stays short and points at
those two rather than duplicating them, so it can't drift out of sync
with them the way an earlier version of this section once did (it
stopped being updated after Phase 7, while the rest of this file kept
moving — corrected during Phase 15's close-out, PR #87).

## Completed

- Phase 0 — Development rules, git baseline, `docs/ARCHITECTURE.md`,
  `docs/ROADMAP.md`.
- Phase 1 — Django project bootstrapped (`config/` + `apps/{core,users,crm}`
  layout), PostgreSQL wired as the only database backend, `manage.py
  check`/`migrate`/`test` all verified passing.
- AI governance layer: `CLAUDE.md` rewritten as the master rules document;
  `docs/AI_RULES.md` (operational procedures); `.claude/settings.json`
  permission allow/ask/deny list; ADRs 0001-0004; `CHANGELOG.md`;
  `Makefile`; `requirements-dev.txt`; `.pre-commit-config.yaml`;
  `pyproject.toml` (ruff config); `.github/workflows/{ci,security}.yml`;
  `.github/dependabot.yml`. All verified locally: `manage.py
  check`/`test`/`makemigrations --check`, `ruff check`/`format --check`,
  `pip-audit`, `bandit` all pass. Full detail in
  `logs/claude/phase-00-ai-rules.md`.
- GitHub remote: `github.com/JosephHeffron/django-crm` (public), `main`
  pushed and verified. Branch protection on `main`: PR required, `test`+
  `dependency-audit` required status checks (the actual CI *job* names,
  not the `ci`/`security` workflow file names — corrected after an
  initial misconfiguration), strict/up-to-date, no force-push, no
  deletion, conversation resolution required, `enforce_admins: true`.
  Secret scanning + push protection enabled by default (public repo);
  Dependabot security updates enabled. PR #4 (`pytest` 8.4.2→9.1.1, fixes
  a real medium-severity advisory) merged; 6 more Dependabot PRs still
  open for review.
- Phase 2 database design (`docs/DATABASE_DESIGN.md`, PR #9): Company,
  Contact, Lead, Deal, Task, Activity — fields, relationships,
  constraints, indexing, lifecycle. An automated review caught two real
  defects (a `SET_NULL`/`CheckConstraint` conflict on Deal, and a
  self-contradictory `CASCADE` rationale) — both fixed before merge. Full
  detail in `logs/claude/phase-02-database-design.md`.
- Phase 2 model implementation (`apps/crm/models.py`, PR #11): all six
  models implemented from the design doc, migrated against real
  PostgreSQL (both CheckConstraints confirmed live via `\d+`), 38 model
  tests. An automated review caught two more real gaps — `Deal.probability`
  had no upper-bound enforcement (added a CheckConstraint) and
  `Activity` (documented as immutable) was still editable via the admin,
  the only mutation path that currently exists (disabled admin change
  permission for it). Full detail in `logs/claude/phase-02-crm-models.md`.
- Phase 2 schema review (`docs/DATABASE_REVIEW.md`, PR #14): senior-
  reviewer pass on the implemented schema. Two HIGH findings, both
  verified empirically (not inferred): `on_delete` behavior is enforced
  entirely by Django's ORM, not by PostgreSQL (every FK is `NO ACTION`
  at the DB level — confirmed via `pg_constraint` and a raw SQL delete
  that should have cascaded but instead failed); Activity's `CASCADE` on
  all four relation FKs can destroy history still relevant to a
  surviving object (confirmed by deleting a Deal and watching an
  Activity also tagged to a still-existing Company vanish with it). Plus
  5 MEDIUM findings (including that Activity immutability still isn't
  enforced beyond the admin — confirmed a plain `.save()` bypasses it)
  and several LOW findings. Automated review caught two issues in the
  review itself (an unsound `SET_NULL` recommendation, an overly
  reassuring "nothing contradicts the design" claim) — both fixed. Full
  detail in `logs/claude/phase-02-database-review.md`.
- Phase 3 unit 1 — authentication + minimal base template shell
  (PR #16): Django's built-in login/logout/password-change views under
  `apps/users`, `templates/base.html` shell, `apps.core`'s dashboard
  placeholder now behind `login_required`. Verified end-to-end against a
  running server before writing 9 tests. Automated review caught a real
  `NoReverseMatch` bug on successful password change (the view's default
  `success_url` didn't account for app namespacing) — reproduced,
  fixed, and covered with a regression test (48 tests total). Full
  detail in `logs/claude/phase-03-authentication.md`.
- Phase 3 unit 2 — full navigation, error pages, styling (PR #18):
  full shell nav (Dashboard + all 6 CRM sections + Search), a shared
  `ComingSoonView` giving every not-yet-built section a real working
  login-required URL, custom `404.html`/`500.html` (500 deliberately
  standalone per Django's own guidance), expanded `base.css`. All 8 nav
  URLs, the 404 page, and the 500 template verified directly before
  writing 4 new tests (52 total). First unit in this project with no
  automated-review findings. Full detail in
  `logs/claude/phase-03-navigation-shell.md`. This completes the
  "application shell" scope (Prompt 3.1).
- Phase 3 unit 3 — Companies CRUD (PR #20): list (search + active/
  inactive filter + pagination), detail (shows related Contacts/Deals),
  create, edit, and deactivate (not delete — see below) views,
  replacing the `crm:company_list` placeholder. Manual smoke testing
  caught a real 500 on deleting a company with deal history
  (`Deal.company` is `on_delete=PROTECT`); automated review then caught
  a deeper issue — hard-deleting a company at all contradicts
  `docs/DATABASE_DESIGN.md`'s documented "never hard-deleted from the
  UI" invariant. Reworked to `CompanyDeactivateView`
  (`is_active=False`, never calls `.delete()`), which made the earlier
  fix moot. 78 tests total. Full detail in
  `logs/claude/phase-03-companies-crud.md`.
- Phase 3 unit 4 — Contacts CRUD (PR #22): list (search across name/
  email + active/inactive + company filters + pagination), detail
  (shows linked Company, related Deals/Tasks), create, edit, deactivate
  views, replacing the `crm:contact_list` placeholder. Checked
  `docs/DATABASE_DESIGN.md` before building (unit 3's lesson) and used
  deactivation from the start this time. Automated review still caught
  three real gaps in the company filter: no UI control to actually set
  it, pagination silently dropping it, and a non-numeric value crashing
  with a 500 — all reproduced and re-verified fixed. 107 tests total.
  Full detail in `logs/claude/phase-03-contacts-crud.md`.
- Phase 3 unit 5 — Leads and Deals workflows (PRs #24, #25), the final
  Phase 3 unit: Lead CRUD with a status field that excludes "Converted"
  as directly selectable (only the dedicated conversion workflow can
  set it), and `LeadConvertView` — link/create a Company, always create
  a Contact, optionally open a Deal, then mark the Lead converted, per
  `docs/DATABASE_DESIGN.md`'s Lifecycle section. Deal CRUD with form
  validation mirroring both of Deal's DB `CheckConstraint`s (applied
  proactively this time, not found by review) and a `closed_at`
  set/clear lifecycle tied to stage. Deal references from Company/
  Contact/Lead detail pages now link properly. 158 tests total, zero
  real findings from review on either PR — full detail in
  `logs/claude/phase-03-leads-deals.md`.

**Phase 3 (CRM interface) is now fully complete.**

- Pre-Phase-4 — resolved `docs/DATABASE_REVIEW.md`'s two HIGH findings
  and MEDIUM finding #7 (PR #27): `Activity`'s four relation FKs changed
  `CASCADE` → `SET_NULL` (chose to preserve multi-tagging rather than
  restrict Activity to exactly one relation), the now-incompatible
  `activity_has_related_object` `CheckConstraint` removed,
  `Activity.save()` now rejects updates to existing rows, and
  `CLAUDE.md` documents that `on_delete` only holds through Django, not
  raw SQL. Each finding's original failing reproduction was re-run and
  confirmed fixed, not just re-read. 161 tests total. Full detail in
  `logs/claude/phase-04-prep-resolve-review-findings.md`.
- Phase 4 unit 1 — Activity timeline (PR #29): real
  `ActivityListView`/`ActivityCreateView` (type filter, pagination,
  query-param prefill, priority-ordered redirect after save), a
  reusable timeline partial included on all four detail pages
  (Company/Contact/Lead/Deal), `ActivityForm` enforcing "at least one
  relation" at the form layer. No update/detail view for Activity —
  it's immutable and its "detail page" is the timeline on whichever
  record it's attached to. 181 tests total, zero findings from review.
  Full detail in `logs/claude/phase-04-activity-timeline.md`.
- Phase 4 unit 2 — Tasks (PR #31): list (status/priority filters,
  `?mine=1`, `?overdue=1`, pagination), detail, create, edit views, and
  a dedicated `TaskCompleteView` (POST-only one-click completion,
  separate from the edit form, open-redirect-safe `next` handling),
  replacing the `crm:task_list` placeholder. `completed_at` kept in
  sync with `status` via `_sync_task_completed_at`, mirroring the
  existing `Deal.closed_at` pattern. Contact/Deal detail pages' task
  listings now link to task detail. Sourcery's automated review was
  rate-limited on this PR (no findings either way), so it merged on
  CI + full local verification alone (207 tests total at merge time).
  A subsequent, deliberately more thorough manual review (to
  compensate for the missing Sourcery pass) found a real bug:
  `TaskCompleteView` had no guard against completing an already-
  cancelled task via a direct POST — fixed with the same kind of
  status guard `LeadConvertView` already uses, plus 2 regression
  tests (209 tests total). Full detail in
  `logs/claude/phase-04-tasks.md`.
- Phase 4 unit 3 — Audit history (PR #34), the final Phase 4 unit: a
  new `AuditLogEntry` model (generic FK via `contenttypes`) records who
  changed what and when on Company/Contact/Lead/Deal — scope confirmed
  with the user up front; Task and Activity are deliberately excluded.
  Design written into `docs/DATABASE_DESIGN.md` before implementation.
  Written explicitly from each model's Create/Update/Deactivate views
  and Lead conversion (not signal-based — signals can't see
  `request.user` without a thread-local). Displayed as a "History"
  section on all four detail pages. 227 tests total. Sourcery was
  rate-limited on this PR too; per the lesson from unit 2, did a
  second deliberately adversarial manual review pass afterward
  (checking specifically for XSS in the history display, multi-edit
  and round-trip sequences, cross-user visibility) — came back clean.
  Full detail in `logs/claude/phase-04-audit-history.md`.

**Phase 4 (Activities, Tasks, audit history) is now fully complete.**

- Phase 5 unit 1 — Global search (PR #36): `SearchView` searches
  Company/Contact/Lead/Deal/Task by name-like fields, capped at 20
  results per model, each ordered by its own natural key plus `pk` as
  a tiebreaker so results are stable across requests even when rows
  tie on that key. Activity excluded — no detail page of its own,
  same reasoning as `AuditLogEntry`'s scope. Replaces the
  `core:search` `ComingSoonView` placeholder; `ComingSoonView` itself
  and its template removed as fully dead code. Adds a search box to
  the site nav. 239 tests total. The user pasted an external review
  with two findings: one ("missing template") was verified false
  against the actual commit; the other (no ordering tiebreaker) was
  real once checked against the actual generated SQL, and was fixed
  with a regression test that asserts the fix's effect directly
  (`sorted(pk)`), not just that two requests match. Full detail in
  `logs/claude/phase-05-global-search.md`.
- Phase 5 unit 2 — Operational dashboard (PR #39): `DashboardView`
  replaces the placeholder "Signed in as {{ user.username }}" page
  with quick counts (active companies/contacts, open leads, open deals
  + total value, pending tasks), an open-deal pipeline breakdown by
  stage in natural pipeline order (not alphabetical — `.values()`/
  `.annotate()` doesn't respect `Meta.ordering`, so this is built by
  iterating `Deal.Stage.choices` directly), the signed-in user's own
  pending tasks, and a recent-activity feed. No charting library or JS
  dashboard framework — plain server-side ORM aggregates throughout.
  254 tests total. Sourcery was rate-limited on this PR too; rather
  than a fresh adversarial script, reasoned through the same edge
  cases (null-value `Sum()` handling, zero-default stage lookups,
  per-user task scoping) directly against what the existing tests
  already assert — no new issues found. Full detail in
  `logs/claude/phase-05-operational-dashboard.md`.
- Phase 5 unit 3 — Usability review (PR #41), the final Phase 5 unit:
  no visual browser tool was available (this project's `WebFetch` tool
  refuses `localhost`), so the review ran a real authenticated
  walkthrough against the dev server via `curl` (real CSRF tokens,
  real cookies) rather than relying only on the Django test client.
  **Found and fixed a real bug**: Django's `{# #}` comment tag doesn't
  support multi-line content, so the multi-line comments atop
  `_activity_timeline.html`/`_audit_history.html` had been rendering as
  literal raw text on every Company/Contact/Lead/Deal detail page since
  Phase 4 — undetected by ~250 existing tests because none asserted on
  the *absence* of that text. Also fixed: missing accessible labels on
  every list page's filter inputs, no Cancel link on any create/edit
  form, no current-page nav indicator, missing `role="status"` on
  flash messages, no horizontal-scroll handling for data tables on
  narrow viewports. Findings and fixes documented in
  `docs/USABILITY_REVIEW.md`. 268 tests total. Full detail in
  `logs/claude/phase-05-usability-review.md`.

**Phase 5 (Search, dashboard, usability) is now fully complete.**

- Phase 6 unit 1 — Security audit (PR #43): `manage.py check --deploy`
  against production settings is clean; a repo-wide grep for raw SQL,
  `mark_safe`/`|safe`, `@csrf_exempt`, and `eval`/`exec` found none.
  Two safe fixes applied — `CSRF_COOKIE_HTTPONLY` (no JS in this app
  ever reads that cookie; verified live via a real login + form-submit
  round trip against a running dev server, since Django's test client
  disables real CSRF checks by default) and a stronger password
  minimum (8 → 12). Everything else found (no role separation, no
  login rate-limiting, the default `/admin/` path, no CSP, no custom
  `AUTH_USER_MODEL`) documented as a deliberate deferral with reasoning
  in `docs/SECURITY_REVIEW.md`, not a silent gap. 271 tests total. Full
  detail in `logs/claude/phase-06-security-audit.md`.
- Phase 6 unit 2 — Role/permission model (PR #45): a "Staff" Group
  (seeded by a data migration, verified against a genuinely fresh
  PostgreSQL database — model permissions are created by a
  `post_migrate` signal that fires *after* this migration would
  otherwise run, a real gotcha this migration handles explicitly)
  holds add/change permissions on the six CRM models; every
  create/edit/deactivate/complete/convert view (15 total) now uses
  `PermissionRequiredMixin`; superusers bypass via Django's own
  built-in behavior. Visibility stays unrestricted — only writes are
  gated. Added a custom `403.html` matching the existing 404/500
  pages. Sourcery was rate-limited on this PR; a post-merge
  self-review pass found and fixed two real gaps before merging: the
  "Staff" Group name could be confused with Django's unrelated
  `is_staff` field (documented explicitly, verified empirically that
  each is independent of the other), and the Deactivate confirmation
  page's GET wasn't explicitly tested for the 403 boundary (added).
  296 tests total. Full detail in `logs/claude/phase-06-permissions.md`.
- Phase 6 unit 3 — Dependency security audit (PR #47), the final
  Phase 6 unit: `pip-audit` clean, no open Dependabot security alerts,
  production dependencies (Django, psycopg2-binary, python-dotenv)
  already at latest. **Cleared the long-open backlog of 6 Dependabot
  PRs** — each pip-tooling bump (`ruff`, `bandit`, `pytest-django`,
  `pre-commit`) re-verified locally against the *current* codebase
  (not the much-staler codebase each PR's own CI last ran against)
  before merging; one genuine merge conflict on `requirements-dev.txt`
  resolved by hand. Found and fixed a real gap during the audit:
  `.github/dependabot.yml` didn't track the `pre-commit` ecosystem at
  all, and `.pre-commit-config.yaml`'s own `ruff` pin had already
  silently drifted from `requirements-dev.txt`'s — added the ecosystem
  and synced the pins. 296 tests total (unchanged — a dependency audit
  doesn't add test cases of its own). Full detail in
  `logs/claude/phase-06-dependency-audit.md`.

**Phase 6 (Security hardening) is now fully complete.**

- Phase 7 unit 1 — Django production container (PR #50): single-stage
  `Containerfile` (`python:3.12-slim`) — no multi-stage build, since
  `psycopg2-binary` ships a self-contained wheel and needs no compiler
  step to isolate. Runs as a non-root user (uid 1000), all config from
  environment variables, `gunicorn` (3 workers, fixed — not computed
  from CPU count, since the deployment target is a known, singular
  Raspberry Pi 5). `scripts/entrypoint.sh` runs `migrate`/
  `collectstatic` at container startup (not build time — no real
  secrets then) before handing off to gunicorn. **Verified with a real
  live container run**, not just a successful build: a throwaway
  `postgres:18-alpine` container proved all 22 migrations apply, 131
  static files collect, gunicorn serves real pages with correct
  production security headers, the container truly runs as non-root
  (checked via `podman exec ... whoami`), and a restart is
  idempotent. 184 MB final image, 296 tests total (unchanged — infra
  work adds no Django test cases; the live container run is this
  unit's real test). Full detail in
  `logs/claude/phase-07-django-container.md`.
- Phase 7 unit 2 — PostgreSQL container + podman-compose (PR #52), the
  final Phase 7 unit: `compose.prod.yml` wires `postgres:18-alpine`
  (named persistent volume, healthcheck, restart policy) to the Django
  image from Unit 1 (`depends_on: service_healthy`); `web` publishes
  no host port, the correct final shape once Caddy (Phase 8) exists to
  proxy to it. `compose.dev.yml` is the same stack with both services'
  ports published, for local/staging inspection — day-to-day dev
  stays native, unchanged since Phase 0. **Found and fixed two real
  bugs during live verification**: `containerfile:` isn't a valid
  Compose Spec key (`dockerfile:` is — caught by `podman-compose
  config` before any container ran), and `postgres:18`'s official
  image expects its volume mounted at `/var/lib/postgresql`, not the
  pre-18 `.../data` path (caught from the container's own exit-1 logs
  on the first real `up`). **Proved the actual persistence guarantee**
  by inserting a marker row, tearing the containers down, recreating
  them from scratch, and confirming the row survived — not just
  trusting a `volumes:` section that looked correct. 296 tests total
  (unchanged). Full detail in `logs/claude/phase-07-podman-compose.md`.

**Phase 7 (Containerization with Podman) is now fully complete.**

- Phase 8 unit 1 — Caddy container (PR #54): `Caddyfile`/`Caddyfile.dev`
  (root level, matching Phase 7's file placement) added — reverse
  proxy to `web:8000`, HTTPS termination (real automatic HTTPS in
  production, `tls internal` for local testing), `/static/*`/`/media/*`
  served directly by Caddy, security headers. `caddy` service wired
  into both compose files, with new `caddy_data`/`caddy_config`
  volumes. **Verified live** against a real 3-container stack (not
  just a config review): HTTP→HTTPS redirect, reverse proxy, and —
  the one thing this unit most needed to prove — that Caddy's
  `X-Forwarded-Proto` is actually recognized by Django's
  `SECURE_PROXY_SSL_HEADER` (confirmed via `Strict-Transport-Security`
  present on the proxied response, not assumed from documentation).
  That same live run found and fixed three real bugs: a host-port
  5432 collision with this project's own native dev PostgreSQL, a
  Fedora-SELinux bind-mount denial on the Caddyfile mount (needed
  `:Z`), and duplicate security headers on the proxied path (Caddy's
  header block was site-wide, duplicating what Django's
  `SecurityMiddleware` already sets — rescoped to just the static/
  media blocks). 296 tests total (unchanged — infra work adds no
  Django test cases). Full detail in
  `logs/claude/phase-08-caddy-https.md`.
- Phase 8 unit 2 — Production configuration review (PR #56), the final
  Phase 8 unit: `docs/PRODUCTION_CONFIG_REVIEW.md` audits the complete
  assembled stack (Django settings, `Containerfile`,
  `compose.prod.yml`, `Caddyfile`). **Found and fixed a real HIGH
  finding**: `.env.example`'s `DJANGO_SETTINGS_MODULE=config.settings.
  development` line would silently override the production
  container's baked-in settings via `env_file:` — confirmed live by
  running the actual built production image against an env file
  copied verbatim from `.env.example`, which booted with `DEBUG=True`,
  `SECURE_SSL_REDIRECT=False`. Fixed by removing the line (the
  existing `setdefault`/`Containerfile` `ENV` defaults were already
  correct on their own); re-verified live against the fixed file. Two
  MEDIUM findings deferred with reasoning (no CSP — needs a
  real-browser check this environment can't perform against Django
  admin's inline scripts; Caddy runs as root, the official image's
  default, substantially mitigated by rootless Podman). 296 tests
  total (unchanged). Full detail in
  `logs/claude/phase-08-production-config-review.md`.

**Phase 8 (Caddy and HTTPS) is now fully complete.**

- Phase 9 unit 1 — ARM64 compatibility review (PR #58):
  `docs/ARM64_REVIEW.md` audits ARM64 support across the stack, per
  `docs/ARCHITECTURE.md`'s "ARM64 deployment strategy." Confirmed all
  three base images (`python:3.12-slim`, `postgres:18-alpine`,
  `caddy:2.11.4-alpine`) publish `linux/arm64/v8` manifests, and every
  pinned Python dependency is either pure-Python or, for
  `psycopg2-binary` (the one with compiled code), ships a matching
  `manylinux_aarch64` wheel. **Went beyond manifest-checking** —
  actually built the production `Containerfile` for `linux/arm64`
  under this workstation's existing `qemu-user-static` emulation
  (set up in Phase 0) and ran it live: `uname -m` reports `aarch64`,
  the non-root `django` user still applies, and `psycopg2` actually
  imports and initializes under emulation — proof the wheel is
  genuinely ABI-compatible, not just correctly named. No compatibility
  blockers found; limitations (emulation ≠ performance, no physical Pi
  yet) stated explicitly. 296 tests total (unchanged — a review doc,
  no application code). Full detail in
  `logs/claude/phase-09-arm64-review.md`.
- Phase 9 unit 2 — ARM64 image build + cross-architecture validation
  (PR #60), the final Phase 9 unit: `scripts/test-arm64.sh` builds the
  production image for `linux/arm64` and runs the full
  `db`+`web`+`caddy` stack under emulation, asserting (not just
  observing containers stay up) that migrations ran, static files
  collected, and a real page renders both directly through gunicorn
  and through the full Caddy proxy chain — `docs/ARM64_TESTING.md`
  documents the procedure. **Found and fixed a real environment bug**:
  `podman pull --platform linux/arm64` silently overwrites a shared
  local image tag — confirmed live that this demoted the native
  `amd64` `postgres`/`caddy` images this project's actual dev/prod
  compose stacks depend on to dangling, which would have silently
  forced real local development into unnecessary emulation. Fixed by
  restoring the `amd64` tags and building that restoration into the
  script's cleanup `trap` unconditionally — verified it fires on both
  a clean run and a deliberately failed one. 296 tests total
  (unchanged). Full detail in
  `logs/claude/phase-09-arm64-testing.md`.

**Phase 9 (ARM64 deployment) is now fully complete.**

- Phase 10 unit 1 — Production systemd unit (PR #62): `systemd/
  crm.service` supervises the production Podman Compose stack via
  `Type=oneshot`/`RemainAfterExit=yes`. **A real architectural
  decision, not just a file**: it's a systemd *user* unit, not a
  system unit — documented in a new ADR
  (`docs/decisions/0005-rootless-systemd-deployment.md`) — so
  production keeps running rootless Podman under a dedicated non-root
  account (`loginctl enable-linger`), matching every environment this
  project has actually run Podman in so far, and keeping
  `docs/PRODUCTION_CONFIG_REVIEW.md`'s existing Caddy-as-root
  deferral (which assumes rootless user-namespace isolation) actually
  true in production. Verified live under `systemctl --user` against
  a throwaway stack: start/stop correctly bring the full 3-container
  stack up and down, `RemainAfterExit` behaves correctly,
  `journalctl --user` transparently captures container logs, and
  `enable`/`disable` correctly manage the `[Install]` symlink. 296
  tests total (unchanged). Full detail in
  `logs/claude/phase-10-systemd-unit.md`.
- Phase 10 unit 2 — Deployment script with rollback (PR #64), the
  final Phase 10 unit: `scripts/deploy.sh` — pull an intended git
  revision, build/pull images, restart, verify health, auto-rollback
  on failure, plus standalone `rollback`/`status` commands. **Live
  testing against a real throwaway git clone with a deliberately
  broken commit found and fixed four real bugs**, all sharing one root
  cause — a `Type=oneshot`/`RemainAfterExit=yes` systemd unit's
  "active" state only ever reflects whether `ExecStart` last exited 0,
  never whether the containers it started are still alive:
  `systemctl restart` silently reused a stale container instead of
  the freshly-built image; `systemctl stop` on an already-`failed`
  unit was a no-op (never ran `ExecStop`) — precisely the state a
  rollback runs in; `systemctl start` on a unit systemd believed was
  already `active` was *also* a no-op, even with the real containers
  gone. Fixed by having `deploy.sh` drive `podman-compose` directly
  instead of routing through `systemctl` — `systemd/crm.service`
  (unit 1) is untouched, still doing its real job of starting the
  stack on boot. Also found `podman-compose up -d` can hang
  indefinitely on a `depends_on: condition: service_healthy` chain
  that never resolves — fixed with an explicit `timeout`. Re-verified
  the full scenario suite (good deploy, broken deploy with real
  auto-rollback, explicit rollback, status, dirty-tree guard) end to
  end after the fixes. 296 tests total (unchanged). Full detail in
  `logs/claude/phase-10-deploy-script.md`.

**Phase 10 (systemd on the Raspberry Pi) is now fully complete.**

- Phase 11 unit 1 — Scheduled PostgreSQL backups (PR #66):
  `scripts/backup.sh` — `pg_dump` (custom format) of the database
  plus `podman volume export` of `media_files`/`caddy_data`/
  `caddy_config` (named volumes, not host directories) plus a copy of
  `.env`, per `docs/ARCHITECTURE.md`'s "Backup strategy". Configurable
  retention policy; a failure-cleanup trap removes a partial backup
  directory rather than leaving a misleading one behind.
  `systemd/crm-backup.{service,timer}` schedules it daily (same
  rootless user-unit model as `crm.service`, `Persistent=true` for a
  missed window). **Verified live in an isolated clone**: inserted a
  real marker row and file, ran the backup, then actually restored the
  dump into a fresh database and confirmed the marker row survived —
  not just checked the dump's structure. Also verified the retention
  policy, the systemd timer's schedule/journald integration, and the
  failure-cleanup path (db stopped mid-backup). **Caught and fixed a
  real process mistake**: the first test run executed against the
  actual project directory, copying the real `.env` into a backup
  directory — confirmed with the user before deleting it, then moved
  all further testing to an isolated clone (matching `deploy.sh`'s
  established pattern). 296 tests total (unchanged). Full detail in
  `logs/claude/phase-11-backup-script.md`.
- Phase 11 unit 2 — Tested restore procedure + backup/DR audit (PR
  #68), the final Phase 11 unit: `scripts/restore.sh` models a real
  disaster — rebuilds `postgres_data`/`media_files`/`caddy_data`/
  `caddy_config` entirely from a backup rather than restoring "over"
  current state. Requires `--yes`, takes a best-effort pre-restore
  safety backup, never auto-applies a backup's `.env`. **Ran two full
  live disaster-recovery drills** in an isolated clone: destroyed
  every container and volume, restored, confirmed a marker row, a
  media marker file, and a real served page all survived — and
  separately, deliberately reproduced a retention-boundary edge case
  (the safety backup's own pruning deleting the exact backup being
  restored from, mid-restore) before fixing and re-confirming it.
  **Found and fixed three real bugs**: the safety backup being
  unconditionally required (defeating recovery from a total loss,
  the primary case), the retention-pruning race above, and a shell
  redirection ordering bug (`2>/dev/null >&2` discards both streams,
  not just stderr) that silently hid the usage message's backup
  listing. `docs/DISASTER_RECOVERY.md` documents the tested procedure;
  `docs/BACKUP_DR_AUDIT.md` audits the complete system — one HIGH
  finding (backups live only on the same host/SD-card as the data
  they protect, a real risk for Raspberry Pi hardware specifically),
  two MEDIUM (unencrypted `.env` backups, no automated ongoing
  restore verification), both deferred with reasoning rather than
  invented solutions. 296 tests total (unchanged). Full detail in
  `logs/claude/phase-11-restore-dr.md`.

**Phase 11 (Backups and disaster recovery) is now fully complete.**

- Phase 12 unit 1 — Health-check endpoint (PR #70): `HealthCheckView`
  at `/health/` (`apps/core/views.py`) runs a real `SELECT 1` against
  the database, replacing Phase 7's plain-TCP-connect `web`
  healthcheck in both compose files — the thing that check's own
  comment explicitly deferred to this phase. Unauthenticated, GET-only,
  returns 503 on DB failure. **Found and fixed a real bug via live
  testing**: production's `SECURE_SSL_REDIRECT=True` redirected the
  same-container healthcheck request to HTTPS, which `web` can't
  serve (only Caddy terminates TLS) — the request timed out mid TLS
  handshake. Fixed with Django's `SECURE_REDIRECT_EXEMPT`. Verified
  live: `web` reports healthy when `db` is up (both same-container and
  through the full Caddy proxy chain) and unhealthy (real 503) when
  `db` is stopped. 299 tests total (296 + 3 new). Full detail in
  `logs/claude/phase-12-health-endpoint.md`.
- Phase 12 unit 2 — Application logging review (PR #72), the final
  Phase 12 unit: `docs/LOGGING_REVIEW.md`. **Found and fixed a real
  HIGH finding**: Django's default logging config gates its only
  console handler behind `DEBUG=True`, and its one production-active
  handler (`mail_admins`) is a silent no-op without `ADMINS`
  configured (never set here) — confirmed live that an unhandled
  production view exception logged nowhere at all, by simulating
  Django's own exception-logging call
  (`django.utils.log.request_logger.error(..., exc_info=True)`,
  verified against Django's source) under real production settings.
  Fixed with an explicit `LOGGING` setting in `config/settings/
  base.py`: the `django` logger gets its own unconditional handler,
  everything else reaches a root-level handler via propagation —
  same journald delivery path as gunicorn/Caddy/PostgreSQL's logs, no
  new infrastructure. **Caught and fixed a duplicate-logging bug in
  the fix's own design** before ever committing it, by testing the
  design live first. Confirmed no sensitive data anywhere in what
  gets logged. 303 tests total (299 + 4 new). Full detail in
  `logs/claude/phase-12-logging-review.md`.

**Phase 12 (Logging and monitoring) is now fully complete.**

- Phase 13 unit 1 — Production readiness audit (PR #74):
  `docs/PRODUCTION_READINESS.md` synthesizes every prior review
  (Phases 2, 5, 6, 8, 9, 11, 12) into one consolidated picture, with
  fresh live re-verification of a sample of the most safety-critical
  claims (deploy checks, ruff/bandit/pip-audit, a live `psql \d+
  crm_deal` confirming `Deal`'s `CheckConstraint`s are still present,
  zero open Dependabot alerts) — **no drift found anywhere checked**.
  **Found one new, real HIGH finding no prior phase covered**: branch
  protection and secret scanning had been silently disabled on GitHub
  ever since the repo switched to private (both gated behind GitHub
  Pro for private repos on the free plan) — confirmed directly via the
  API. Presented to the user as a real trade-off (stay private and
  accept the gap, upgrade to GitHub Pro, or go public again); the user
  chose to make the repository **public again**. Executed and
  verified: branch protection restored to its exact original
  documented settings, secret scanning/push protection re-enabled
  automatically. Two HIGH items remain genuinely open (off-host
  backup storage; a residual manual check of the real `.env`), both
  correctly identified as blocked on something outside this audit's
  reach. 303 tests total (unchanged). Full detail in
  `logs/claude/phase-13-production-readiness.md`.
- Phase 13 unit 2 — Clean-environment end-to-end test (PR #76), the
  final Phase 13 unit: a real `git clone` from the public GitHub
  remote, `systemd/crm.service` installed exactly as documented, real
  login and a real Company record created through the actual web form
  (not just HTTP status codes), a real backup, a simulated total
  disaster, and a real restore — all working end to end for a
  genuinely fresh deployment. **Found and fixed a real bug**:
  `scripts/backup.sh`/`scripts/restore.sh` silently produced wrong,
  empty backups when pointed at `compose.dev.yml` (whose volumes
  carry a `_dev` suffix `compose.prod.yml`'s don't) — exactly the
  documented `COMPOSE_FILE` override example in `backup.sh`'s own
  header comment, never actually tested until this unit. Also found
  that `podman volume export` doesn't reliably fail on a nonexistent
  volume name on this Podman version. Fixed with a `VOLUME_SUFFIX` env
  var (default empty — real production via `compose.prod.yml`
  completely unaffected) plus an explicit `podman volume exists`
  check; re-verified via a full second disaster/restore cycle. Native
  dev setup (the README's path) wasn't re-verified — blocked on an
  interactive sudo password this session couldn't supply; the user
  chose to skip it. 303 tests total (unchanged). Full detail in
  `logs/claude/phase-13-clean-environment-test.md`.

**Phase 13 (Final production audit) is now fully complete.**

- Phase 14 unit 1 — Admin and developer guides (PR #78):
  `docs/ADMIN_GUIDE.md` (first-time deployment, day-to-day operations,
  deploying updates, backups, disaster recovery, known limitations)
  and `docs/DEVELOPER_GUIDE.md` (orientation, project layout, common
  tasks, git workflow, how to use `logs/claude/`'s build history) —
  both consolidate knowledge previously scattered across a dozen
  phase-specific docs, each claim linking back to its verified source
  rather than restating it. Spot-checked factual claims (the `/health/`
  endpoint really is the only JSON endpoint; `crm-backup.service`'s
  quoted install commands match its own header exactly) against the
  actual codebase before writing. 303 tests total (unchanged). Full
  detail in `logs/claude/phase-14-admin-developer-guides.md`.
- Phase 14 unit 2 — Final repository cleanup (PR #80), the final unit
  of the final phase: fixed `docs/ARCHITECTURE.md`'s stale nested
  `containers/`/`compose/` file-layout sketch to match the real
  root-level layout; brought `CHANGELOG.md` up to date from roughly
  Phase 5 through Phase 14; wired the long-stubbed `Makefile`
  `build`/`arm64`/`backup` targets to their real scripts; removed the
  confirmed-unused `pytest`/`pytest-django` dev dependency, resolving a
  standing LOW finding from `docs/DEPENDENCY_AUDIT.md`/
  `docs/PRODUCTION_READINESS.md`; removed a leftover `.gitignore` rule
  from the original (never-built) nested container layout. **Found**
  that `logs/git/commits.md`/`logs/git/branches.md` — a
  `docs/AI_RULES.md`-mandated practice — silently stopped being
  maintained after Phase 4 unit 1, superseded in practice by the
  richer `logs/claude/phase-*.md` per-unit log; rather than a
  low-value retroactive backfill, added closing notes to both files
  and updated `docs/AI_RULES.md`'s "Git operation logs" section to
  reflect current, actual practice. 303 tests total (unchanged). Full
  detail in `logs/claude/phase-14-final-cleanup.md`.

**Phase 14 (Documentation and handoff) is now fully complete — this
also completes the entire 14-phase roadmap.**

## Project complete

All 14 roadmap phases (`docs/ROADMAP.md`) are done. The application
covers its full initial release scope (Companies, Contacts, Leads,
Deals, Activities, Tasks, Search, Dashboard, Users/Permissions — Notes
was folded into Activities' "note" type rather than built as a
separate model) and the full production path (containerization, Caddy/
HTTPS, ARM64 compatibility, systemd deployment, backups/DR, logging,
health checks, a final production audit, and admin/developer
documentation).

**Not yet done, deliberately outside this original roadmap's scope —
see "Post-release roadmap" below for what picks these up:**
- Actual deployment to a physical Raspberry Pi 5 — no hardware acquired
  yet; everything ARM64-related has been verified only under
  `qemu-user-static` emulation (see `docs/ARM64_REVIEW.md`/
  `docs/ARM64_TESTING.md`). Now `docs/ROADMAP.md`'s Phase 22.
- Of the two HIGH findings tracked in `docs/PRODUCTION_READINESS.md`:
  off-host backup storage is now **fixed** (Phase 15, below); a
  residual manual check of the real `.env` for a stale
  `DJANGO_SETTINGS_MODULE` line remains genuinely open (needs direct
  access to that file, which policy never grants an AI assistant).
- Email integration, calendar integration, reporting, file attachments,
  APIs, and mobile-specific functionality — explicitly deferred past
  initial release per `docs/ROADMAP.md`'s "Initial release scope", now
  picked up piecemeal by Phases 17-20 of the post-release roadmap.

## Post-release roadmap progress

`docs/ROADMAP.md`'s "Phase 15+" section, added after the original
roadmap completed:

- **Phase 15 — Backup hardening: mechanism implemented and
  live-verified; real off-host storage pending operator setup.**
  `scripts/backup.sh` pushes
  each backup to a `restic` repository (client-side encrypted) when
  `RESTIC_REPOSITORY` is configured — opt-in, existing deployments
  unaffected until they set it. `scripts/restore_offhost.sh` recovers
  `backups/` itself from that repository when the local directory is
  gone, not just the running containers/volumes. Live-verified in an
  isolated clone: a marker record survived containers, volumes, AND
  the local `backups/` directory all being destroyed, recovered purely
  from a local repository standing in for the real destination
  (Backblaze B2, the user's choice — creating the actual account/
  bucket/key is the user's own remaining step, documented in
  `docs/ADMIN_GUIDE.md`). Closes `docs/BACKUP_DR_AUDIT.md`'s HIGH
  finding #1 and MEDIUM finding #2. 303 tests total (unchanged — no
  Django application code touched). Full detail in
  `logs/claude/phase-15-backup-hardening.md`.
- **Phase 16 — Browser-verified security review: DONE.** Django's own
  built-in CSP middleware (`django.middleware.csp`, present since
  Django 6.1 — this project's actual installed version, discovered
  while starting this phase, not assumed from either prior finding
  that deferred it) plus a strict production-only `SECURE_CSP` policy
  (`default-src 'none'`, no `'unsafe-inline'` anywhere). Verified with
  a headless Chromium instance (Playwright, installed into an isolated
  throwaway venv for this session only) driven against a real
  `manage.py runserver` under production settings: admin login,
  changelist, an add form's date/related-object widgets, and a
  related-object popup all loaded with **zero CSP violations**.
  Sourcery's review then caught a real bug this project's own template
  audit had missed — `templates/500.html`'s inline `<style>` block, for
  which a nonce-based fix wasn't even viable (Django's `handler500`
  renders that template with no request context at all) — fixed by
  moving the CSS to an external stylesheet, re-verified by deliberately
  triggering a real 500 under full CSP enforcement and confirming via
  the browser's own computed style that it still rendered correctly.
  Closes `docs/SECURITY_REVIEW.md` #6 / `docs/PRODUCTION_CONFIG_REVIEW.md`
  #2. 304 tests total (+1 regression test). Full detail in
  `logs/claude/phase-16-csp.md`.
- **Phase 17 — Field-service foundation (complete).** The roadmap pivoted here to the owner's exterior
  home-services business (ADRs 0008/0009; plan approved 2026-09-28).
  **Unit 1 (PR #90) — done:** Owner / Sales Rep / Cleaner roles
  enforced server-side (replacing the Phase 6 "Staff" group; no-role
  users fail closed), nav and views declared against the same role
  sets with a per-role consistency test, a mobile-first shell (sidebar
  / drawer / phone bottom bar) on a tokenized light/dark design system
  meeting WCAG AA, and an installable PWA baseline whose service worker
  never caches authenticated pages. Verified in a real browser across
  4 roles × 3 viewports, and under production settings (zero CSP
  violations, worker active, offline fallback). Sourcery skipped the PR
  (diff over its size limit); a self-review found stale "Staff"
  references in the user/admin docs, fixed before merge. 333 tests.
  Full detail in `logs/claude/phase-17-unit1-shell-roles.md`.
  **Unit 2a (PR #92) — done:** contact lifecycle status, lead source,
  tags, properties, notes, business plans; follow-up tasks with DB
  constraints; `apps.jobs` (service catalog seeded with the ten default
  services, quotes, crew-assigned jobs, photos, invoices, payments,
  expenses) with Subquery-based totals and per-role row scoping; Leads
  folded into lead contacts and Deals into quotes; Pillow. Reversing the
  migrations on a throwaway database found a Django backwards-migration
  collector failure (fixed); Sourcery then found five reversibility
  gaps in the fold (fixed, each regression-tested). 378 tests. Full
  detail in `logs/claude/phase-17-unit2a-data-model.md`.
  **Unit 2b (PR #94) — done:** `apps.messaging` (channels, direct
  messages, per-user read markers, job/contact/quote references; shaped
  for customer SMS later without a schema change) with the #general /
  #crew / #sales channels, and per-role model permissions for all the
  field-service models (money and the service catalog Owner-only).
  Sourcery's weekly review budget ran out, so it was self-reviewed —
  found and fixed an SMS-channel contact FK that should be PROTECT, and
  permission docs that overstated what views enforce yet. 388 tests.
  Full detail in `logs/claude/phase-17-unit2b-messaging-permissions.md`.
  **Unit 2c (PR #96) — done:** the repeat-service follow-up engine
  (`generate_followups`: due when neither a job for a service nor any
  contact touch happened within its interval; idempotent, dismissals
  respected, completion logs the touch that resets the clock) and
  `seed_demo` (a realistic year of demo data owned by `demo_` users;
  `--reset` removes exactly that). Fixed a 500 when a follow-up's
  customer was cleared in the task form. Sourcery's budget was still
  exhausted; the self-review found and fixed seeded messages not
  linking to the customers they name, and over-broad follow-up
  lookups. 408 tests. Full detail in
  `logs/claude/phase-17-unit2c-followups-seed.md`.
  **Unit 3a (PR #98) — done:** the role-aware dashboard (Owner:
  revenue and balances; Sales Rep: own quotes, follow-ups, site
  visits; Cleaner: own jobs and hours), a day/week/month calendar
  (cleaners see only their assignments), job and quote pages (prices
  hidden from cleaners, invoices Owner-only), and the Owner's service
  catalog editor; Leads/Deals left the menu. Verified in a browser per
  role at phone and desktop widths, and with zero CSP violations under
  production settings. Self-reviewed (Sourcery budget exhausted): no
  defects. 435 tests. Full detail in
  `logs/claude/phase-17-unit3a-dashboard-calendar.md`.
  **Unit 3b (PR #100) — done:** contacts with lead/customer tabs, tag
  and phone filters, last job / last contact and a "longest since
  contact" sort, and a contact page with properties, upcoming jobs,
  and one timeline of jobs, quotes, notes, activity, and messages
  (direct messages only for their members); the contact form sets
  stage, source, contact method, and tags; the Tasks hub (tasks,
  follow-ups with mark done, quotes, plans, notes); search by phone
  and job/quote number. Browser-verified per role at phone and
  desktop widths, zero CSP violations. Self-reviewed (Sourcery budget
  exhausted): two defects fixed before merge — open tasks sorted last
  on a contact page, and a same-named-company move missing from the
  audit log. 459 tests. Full detail in
  `logs/claude/phase-17-unit3b-contacts-tasks.md`.
  **Unit 3c (PR #102) — done:** the Owner's Financials page —
  revenue, collected, expenses, and net for preset or custom periods;
  a revenue-vs-expenses chart; revenue by service and by sales rep;
  expenses by category; outstanding balances aged by lateness. All
  database aggregates, with the definitions in one place
  (`apps/jobs/reports.py`). Browser-verified, zero CSP violations;
  self-reviewed (Sourcery budget exhausted), no defects. 468 tests.
  Full detail in `logs/claude/phase-17-unit3c-financials.md`.
  **Unit 3d (PR #104) — done:** team messaging (#general, #crew, a
  sales-only #sales via a new channel audience field, private direct
  messages, posting by form, an unread badge — one visibility rule
  for every list, count, and page) and profiles (per-role stats over
  30/90/365 days, self-editing, the Owner's team view); per-role phone
  bottom bar. Browser-verified, zero CSP violations. Self-reviewed
  (Sourcery budget exhausted): one defect fixed before merge — a
  superuser owner couldn't be sent a direct message. 494 tests. Full
  detail in `logs/claude/phase-17-unit3d-profile-messages.md`.
- **Phase 17.5 — UI restyle (complete — all 11 steps).**
  Matching the owner's reference design (ADR 0010); map on
  OpenStreetMap (ADR 0011). Reference screenshots hold real people's
  data and are kept outside the repo. **Step 1 (PR #106) — done:** new
  design tokens (AA-checked palette, light/dark with a saved-choice
  override, large radii, soft shadows), self-hosted Inter, and the
  shared components on an Owner-only `/styleguide/`; every existing
  page picked up the new look. Self-reviewed (Sourcery budget still
  counting last week): one visual defect fixed before merge. 500
  tests. Full detail in `logs/claude/phase-17.5-step1-foundation.md`.
  **Step 2 (PR #108) — done:** the app shell — floating sidebar with
  flyouts (Customers, Crew, Job, Finance; Inbox → team messages), top
  bar with a ⌘K command palette, Create menu, dark-mode toggle saved
  per user, settings gear, help button, role-aware keyboard shortcuts,
  footer email links (`CRM_SUPPORT_EMAIL`); works without JavaScript.
  Self-reviewed: two defects fixed before merge (the palette reopened
  on Escape; an unchecked shortcut key). 507 tests. Full detail in
  `logs/claude/phase-17.5-step2-shell.md`.
  **Step 3 (PR #112) — done:** Business Settings for the Owner at
  `/settings/business/` — business name, logo (cropped in the browser,
  then validated and re-encoded server-side as a ≤512px PNG with no
  metadata; the uploaded bytes are never stored), customer-facing
  contact email and phone, website and social links (one per main
  platform plus labeled Other links), and the currency (USD/CAD) that
  the `money` filter follows everywhere. The name and logo replace the
  install brand across the shell, the sign-in page, and the PWA
  manifest. Export Data streams any dataset as CSV or JSON with
  spreadsheet-formula cells neutralized. Settings load once per
  request; reading never writes the row. Self-reviewed: three defects
  fixed before merge (an added link sorted second; an unreadable hidden
  crop value silently discarded the save; a negative amount exported as
  text). 530 tests. Full detail in
  `logs/claude/phase-17.5-step3-business-settings.md`.
  **Step 4 (PR #114) — done:** the dashboard to the reference layout —
  a greeting, four overview cards per role (the Owner's revenue card
  carries a month-to-date mini chart and a comparison with the same
  stretch of last month), today's jobs, quick action tiles, and the
  task and activity lists. Two models the design needs are built for
  real: `Notification` (a top-bar bell and its own page, written only
  through `notify()`, raised by a task assigned to someone else and by a
  due follow-up, de-duplicated so a daily run can't announce the same
  task twice) and `Goal` (one monthly target per metric, measured
  against aggregates that reuse the Financials definitions). The Owner
  also gets a setup checklist answered entirely from the database, so a
  step un-ticks itself when its data goes away. Progress bars are SVG,
  since the CSP forbids an inline width. Self-reviewed: two defects
  fixed before merge (a stored notification link was followed verbatim;
  a hand-rolled "next" check replaced with Django's). 586 tests. Full
  detail in `logs/claude/phase-17.5-step4-dashboard.md`.
  **Step 5 (PR #116) — done:** Scheduling and Estimates. The calendar
  becomes **Scheduling** in the new style (segmented view switcher, date
  chip, crew filter) and gains per-day indicators — one dot per booking,
  colored by service, capped at six — because a month cell only fits two
  events. **Booking a job** is new: customer, address, time, service,
  crew and the lines of work, saved in one transaction, with the price
  filled in from the chosen service; editing is how a job moves day or
  changes hands, and hours already logged survive it. **Estimates** is
  its own page rather than wearing the Tasks heading, sharing the same
  line-item editor, with sent and accepted dates stamped from the
  status. The dashboard's "New job" button now works. Self-reviewed: a
  job marked Completed recorded no date, so every count of finished work
  ignored it — fixed before merge. 633 tests. Full detail in
  `logs/claude/phase-17.5-step5-scheduling-estimates.md`.
  **Step 6 (PR #118) — done:** the Finance menu — **Invoices**,
  **Payments**, **Expenses** and **Profit** (Financials restyled and
  retitled; it keeps the route name). Until now the money could only be
  read; the Owner can now raise an invoice, take a payment and record a
  cost. Invoice states aren't stored: unpaid, overdue and paid are
  queryset filters over the payments and the due date, so a badge can't
  drift from the money. Billing a job starts from that job's own lines
  and takes the customer from the job. A payment defaults to the whole
  balance (quantized to cents); overpayment is allowed and says so.
  Self-reviewed: billing a multi-line job dropped all but the first
  line, which would have under-billed the customer — fixed before
  merge. 666 tests. Full detail in
  `logs/claude/phase-17.5-step6-finance.md`.
  **Step 7 (PR #120) — done:** the Crew menu — **Time clock**,
  **Assignments**, **Payroll** and **Performance** — plus the two things
  the design needed and the CRM had no record of: an hourly rate and the
  days someone normally works, both Owner-only. `TimeEntry` is the clock
  (one running per person, enforced by a partial unique constraint);
  clocking out of a job tops up that person's hours on it, so the job's
  record and the clock agree by construction. Payroll pays for clocked
  time and names anyone whose rate is missing rather than quietly paying
  nothing. Self-reviewed: listing people created profile rows for them
  (a rule the app shell already stated, and broken in `profile_context`
  since long before this step), and a double tap on Clock in would have
  been a 500 — both fixed before merge. 696 tests. Full detail in
  `logs/claude/phase-17.5-step7-crew.md`.
  **Step 8 (PR #122) — done:** the **Map** on OpenStreetMap (ADR 0011).
  Customer addresses become pins colored by whether a job is booked
  there this week, with the same addresses listed below so nothing
  needs the map to be reachable. Leaflet is vendored with its licence
  and SHA-256 of every file (Dependabot can't see vendored files, so
  updates are deliberate); the production CSP gains exactly one entry,
  `img-src https://tile.openstreetmap.org`. Addresses become
  coordinates through Nominatim — server-side, one request a second,
  the address only and never a name or a job — and **never while a page
  renders**: the page lists what needs placing and
  `manage.py locate_properties` works through them. Anything Nominatim
  can't find, or shouldn't be sent, can be pinned by hand. Self-reviewed:
  the page loaded every property to filter in Python, against the
  project's own performance rules, and two of the tests written for it
  proved nothing — both fixed before merge. 724 tests. Full detail in
  `logs/claude/phase-17.5-step8-map.md`.
  **Step 9 (PR #124) — done:** **Reports** — eleven questions (revenue
  by service and by rep, profit over time, expenses, crew hours and pay,
  jobs by status and service, new customers, where they come from,
  estimate outcomes, follow-ups), each over a period you pick, with
  totals and a CSV. A report declares its columns and what each holds,
  so the page and the file render from one description. Money reuses the
  Profit definitions. A money report asked for by a rep is a 404, not a
  403. Sourcery reviewed this one properly: nine findings, eight real,
  all fixed before merge (a custom range never reached the download;
  leads counted as customers; a past period dropped people who had left;
  an empty period downloaded as zero bytes; shares could disagree with
  totals; two columns shared a label; and two of the tests were wrong).
  751 tests. Full detail in `logs/claude/phase-17.5-step9-reports.md`.
  **Step 10 (PR #126) — done:** **Settings** — a hub behind the gear
  showing only what a role can open, **Company management** that sets
  someone's role and whether they can sign in (admin-only until now;
  turning off sign-in keeps every record they made), an **activity log
  with undo**, a **Customize** hub of services and tags, and **What's
  new** read from `CHANGELOG.md` so a release note is written once. Undo is deliberately narrow and says so: the log
  stores changes as text, so it restores a name or a phone number
  exactly, refuses a date or a linked record rather than guessing,
  refuses a field that decides what else exists, and refuses when
  somebody has changed it since. Full detail in
  `logs/claude/phase-17.5-step10-settings.md`.
  **Step 11 (PR #127) — done:** the pages the earlier steps hadn't
  touched, and a sweep of **480 page loads** (40 routes × 3 roles × 2
  themes × 2 widths) failing on overflow, a missing heading, a bad
  status, a console error or a CSP violation. It found one real defect
  — Activities overflowing a phone by 119px — and the sweep is clean
  after the fixes. Sourcery reviewed steps 10 and 11 together and found
  nine issues, all real, all fixed before merge; two of them lost work
  or locked a person out (undo could overwrite a newer edit; turning off
  someone's sign-in removed them from the only page that could turn it
  back on). 783 tests. Full detail in
  `logs/claude/phase-17.5-step11-remaining.md`.
- Phase 18 unit 1 — **private media**. `media/private/` (job photos,
  profile pictures) is no longer served from disk. Both now need a
  signed-in account with a role, but they are scoped differently, and
  the difference matters: a **job or estimate photo**
  (`apps/jobs/media.py`) is shown only to someone who may see the job
  or estimate it belongs to, so a cleaner sees the jobs they're on and
  no others, with out of scope being 404 and never 403. A **profile
  picture** (`AvatarView` in `apps/users/views.py`) is shown to anyone
  with any role, deliberately — colleagues work together — and is not
  scoped per person. Verified in Chromium under production
  settings: the assigned crew member gets the image, a crew member on
  another job gets 404, signed out goes to sign-in, and the raw
  `/media/private/` path is refused — with photos rendering in an
  `<img>` on an ordinary page at zero CSP violations.

  Review found four real defects, and two of them were in the guard
  rather than the feature: the proxy fix did not work (Caddy sorts
  directives into its own order, so a `respond` matcher above the
  general block never ran), and the test passed anyway because it
  grepped for strings — then its replacement would still have passed
  with the block commented out. The guards now run `caddy adapt` and
  assert the effective configuration, mutation-checked four ways, and
  CI installs a pinned Caddy so they cannot silently skip. Also: a
  storage permission error was being disguised as "photo not found",
  and the content type came from the host's MIME database, which
  differs between this workstation, CI and the Pi. 815 tests. Full
  detail, including what it means for unit 2, in
  `logs/claude/phase-18-unit1-private-media.md`.
- Phase 18 units 2-5 and Phases 19-25: not yet started (re-sequenced in
  `docs/ROADMAP.md`).

## Currently working on

Nothing in flight — Phase 18 unit 1 is merged (PR #130).

## Next

1. **Phase 18 unit 2 — uploading and showing photos.** Unit 1 built
   only the serving side; nothing displays or uploads a photo yet.
   Scope is both parents the `Photo` model and the serving view already
   support: before and after photos on a job, taken on a phone, **and
   reference photos on an estimate**, which `docs/ROADMAP.md` lists
   under the quote builder.

   Two constraints found while verifying unit 1, both recorded in
   `logs/claude/phase-18-unit1-private-media.md`: Pillow has no HEIF
   support in this environment, so an `ImageField` upload of a HEIC
   file is rejected at validation — and iPhones shoot HEIC by default.
   Most desktop browsers also cannot render HEIC even when labelled
   correctly. So unit 2 has to choose between relying on iOS converting
   to JPEG on upload and adding `pillow-heif`. CLAUDE.md's
   justification checklist is written for new *infrastructure*
   dependencies rather than a Python library, but the same questions
   are worth answering here, since this one would ship to the Pi.
2. Phase 18 unit 3 — turning an accepted estimate into a job in one
   click.
3. Phase 18 unit 4 — drag-to-reschedule on the calendar, with a
   keyboard alternative.
4. Phase 18 unit 5 — removing the retired Lead and Deal models, whose
   pages the restyle left alone for that reason.

Before calling Phase 18 done, check the remaining items in its
`docs/ROADMAP.md` entry against what Phase 17.5 actually delivered —
quote status transitions, and scheduling with crew assignment — rather
than assuming the restyle covered them.

## Known issues

None currently known. (The three findings previously tracked here —
Activity's `CASCADE` behavior, `on_delete` ORM-only enforcement, and
Activity immutability — are resolved; see "Completed" above and
`docs/DATABASE_REVIEW.md` for the full resolution detail.)

Remaining MEDIUM/LOW findings from `docs/DATABASE_REVIEW.md` (#3-#6 and
the LOW items) are still open but were assessed as non-blocking —
see that document for details.

## Production

Not deployed. No Raspberry Pi hardware acquired yet.

## ARM64

Not yet attempted — planned for a later phase, once Podman containers
exist to test.
