# Project state

Update this file at the end of every session (see `CLAUDE.md`'s Session
Close Procedure). Do not describe anything as complete unless it was
actually verified.

> **Last updated 2026-09-17.** Repo is clean (`main` up to date, nothing
> uncommitted). **Phase 14 (Documentation and handoff) is fully
> complete, and with it, the entire 14-phase roadmap.** See
> "Project complete" below.
> Note: the GitHub repo, switched from public to private earlier in the
> project, is now **public again** — Phase 13 unit 1's audit found
> branch protection and secret scanning had been silently disabled
> while private (both are gated behind GitHub Pro on the free plan);
> the user chose to go public again rather than pay for Pro, and both
> protections are restored. Sourcery's automated review is available
> again as a result (though it's hit its own free-tier review-budget
> limit on the last couple of PRs — a summary/reviewer's guide only, no
> line-level findings).

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

**Not yet done, deliberately outside this roadmap's scope:**
- Actual deployment to a physical Raspberry Pi 5 — no hardware acquired
  yet; everything ARM64-related has been verified only under
  `qemu-user-static` emulation (see `docs/ARM64_REVIEW.md`/
  `docs/ARM64_TESTING.md`).
- The two HIGH findings tracked in `docs/PRODUCTION_READINESS.md` that
  remain genuinely open: off-host backup storage (needs a concrete
  destination the user hasn't chosen yet) and a residual manual check
  of the real `.env` for a stale `DJANGO_SETTINGS_MODULE` line (needs
  direct access to that file, which policy never grants an AI
  assistant).
- Email integration, calendar integration, reporting, file attachments,
  APIs, and mobile-specific functionality — explicitly deferred past
  initial release per `docs/ROADMAP.md`'s "Initial release scope".

## Currently working on

Nothing — the roadmap is complete. Future work would be a new,
explicitly-scoped initiative (e.g. actual Pi deployment, or a
post-release feature), not a continuation of this roadmap.

## Next

None currently queued. See "Project complete" above for what's
deliberately out of scope and would need its own decision to start.

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
