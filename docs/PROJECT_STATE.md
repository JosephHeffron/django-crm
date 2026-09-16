# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

> **Last updated 2026-09-16.** Repo is clean (`main` up to date, nothing
> uncommitted). **Phase 9 (ARM64 deployment) is fully complete.** Phase
> 10 (systemd on the Raspberry Pi) is in progress — unit 1 (production
> systemd unit) is merged; unit 2 (deployment script with rollback) is
> next — see "Next" below. Note: the GitHub repo was switched from
> public to private by the user (Sourcery's free tier no longer reviews
> it as a result — not a rate-limit, a plan/access change).

## Project version

0.1.0 (unreleased — no tags yet)

## Current phase

Phase 2 (CRM database), Phase 3 (CRM interface), and Phase 4
(Activities, Tasks, audit history) are all complete. Phase 3 shipped in
5 units: authentication + base shell, full navigation/error
pages/styling, Companies CRUD, Contacts CRUD, and Leads/Deals workflows
(including the lead-to-Contact/Company/Deal conversion workflow). The
two deferred HIGH findings and one MEDIUM finding from
`docs/DATABASE_REVIEW.md` were resolved before starting Phase 4. Phase
4 shipped in 3 units: Activity timeline, Tasks (plus a post-merge fix
for a real `TaskCompleteView` bug), and lightweight audit history for
Company/Contact/Lead/Deal. Phase 5 (Search, dashboard, usability) is
complete — Global search, Operational dashboard, and a usability
review pass that found and fixed a real bug. Phase 6 (Security
hardening) is now complete — Security audit, Role/permission model,
and a dependency security audit that also cleared a long-open backlog
of 6 Dependabot PRs. Phase 7 (Containerization with Podman) is now
complete — Django production container, and a PostgreSQL container +
podman-compose configuration that proved its persistence guarantee by
actually destroying and recreating containers, not just by having a
`volumes:` section that looked right.

Phase 2's `docs/DATABASE_REVIEW.md` found 2 HIGH findings (Activity's
`CASCADE` can silently destroy history still relevant to a surviving
object; `on_delete` guarantees only hold through the Django ORM, not raw
SQL) plus a MEDIUM finding that Activity immutability isn't actually
enforced beyond the admin. Per the user's explicit choice, these are
deferred until before Phase 4 (Activities/Tasks UI) rather than blocking
Phase 3 — see Known Issues below.

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

## Currently working on

Phase 10 unit 2 — a safe, non-destructive deployment script with
rollback (`scripts/deploy.sh`) (not yet started).

## Next

1. Phase 10 unit 2 — `scripts/deploy.sh`: pull the intended git
   revision, build/pull ARM64 images, run migrations, restart via
   `systemctl --user`, verify health, support rollback — per
   `docs/ARCHITECTURE.md`'s "Production deployment architecture" and
   `CLAUDE.md`'s "DEPLOYMENT RULES". Phase 10 will be complete once
   this merges.

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
