# QA report — independent audit

**Date:** 2026-10-11
**Scope:** the whole repository at `663ca85` (Phase 18 complete)
**Verdict:** **PASS WITH WARNINGS**

Companion documents: `docs/BUG_LOG.md` (each issue in full),
`docs/TEST_COVERAGE.md` (what is and is not covered),
`docs/TESTING_INSTRUCTIONS.md` (how to re-run all of it).

---

## Executive summary

The application works. It was tested, not just read: 1,054 automated
tests pass, 342 real browser page loads under the production
Content-Security-Policy produced zero violations and zero console
errors, and the complete business sequence — enquiry through to a paid
invoice — was walked through real HTTP requests with the database
checked after every step.

**One HIGH-severity defect was found and fixed**, and it was not in the
application: a database backup was never checked to be readable, and
`restore.sh` destroyed the live `postgres_data` volume *before*
`pg_restore` ever opened the archive. The only guard was that the file
existed, which — measured — accepts a 0-byte file, a truncated archive,
a 3-byte stub and a plain text file. The fix reads the archive's table
of contents in both scripts, before anything irreversible.

**One LOW-severity defect is documented rather than fixed**: a
timesheet's rows do not add up to its own total, because per-row and
total figures are rounded at different points. Both are individually
correct and pay is exact; every available fix makes something else
worse. It now has a characterization test so changing it is a decision
rather than an accident.

Nothing else of substance was found, and that is a real result rather
than a shrug. The areas where a CRM usually rots — money arithmetic,
permission boundaries, N+1 queries, migration reversibility — were
probed directly and held up. The honest caveat is in the warnings
below, and it is about what could not be tested rather than what was.

### Why "with warnings" and not "pass"

1. **The restore path has never been executed end to end.** QA-001
   narrowed the failure window; it did not close the testing gap. This
   is the one operation that destroys data on purpose, and it needs a
   staging host to exercise. The drill is written out in
   `docs/TESTING_INSTRUCTIONS.md` §7 and should be run before anyone
   relies on the backups.
2. **Deployment is unverified by any test** — `deploy.sh`, the
   Containerfile build, the systemd units, ARM64. Inspected, not run.
3. **Concurrent edits are last-write-wins** with no mechanism and no
   test. Fine for one business; worth knowing before adding staff.

---

## Repository architecture

A Django monolith with server-rendered templates. No build step, no
JavaScript framework, no client-side routing.

| | |
|---|---|
| Stack | Django 6.1.1, Python 3.12, PostgreSQL, psycopg2-binary, Pillow, gunicorn |
| Deployment | Podman + Caddy + systemd, rootless, on a Raspberry Pi 5 (ARM64) |
| Apps | `core`, `crm`, `jobs`, `messaging`, `users` |
| Models | 30 (core 4, crm 10, jobs 12, messaging 3, users 1) |
| Routes | 94 application + 119 Django admin |
| Migrations | 45, across 5 apps |

Access control is role-based through Django Groups — Owner, Sales Rep,
Cleaner — with three mixins (`RoleRequiredMixin`,
`SalesRoleRequiredMixin`, `OwnerRequiredMixin`) and row-level scoping
helpers in `apps/jobs/access.py`. A superuser counts as Owner. Out of
scope is **404, never 403**, so a refusal cannot confirm that a record
exists.

The production CSP is strict: `default-src 'none'`, nonce-based
`script-src` and `style-src`, no `unsafe-inline`. `CSRF_COOKIE_HTTPONLY`
is on, so no script can read the token and every form server-renders a
hidden field.

### Files reviewed

| Type | Count | Notes |
|---|---|---|
| Python | 184 | 27,348 lines. Models, views, forms, access helpers, reporting, migrations, tests |
| HTML templates | 91 | Every one reached by the browser sweep or the template-rendering tests |
| CSS | 5 | `tokens.css`, `base.css` and three others |
| JavaScript | 9 | 8 project files plus vendored Leaflet |
| Shell | 6 | `backup`, `restore`, `restore_offhost`, `deploy`, `entrypoint`, `test-arm64` |
| Infrastructure | 12 | Containerfile, 2 compose files, 2 Caddyfiles, Makefile, 3 systemd units, 2 CI workflows, pyproject |
| **Total tracked** | **442** | |

### Incomplete or suspicious code

**None found**, which is worth stating plainly because it is unusual.
No `TODO`, `FIXME`, `XXX` or `HACK` anywhere in the repository. The two
`NotImplementedError`s (`apps/jobs/media.py`, `apps/jobs/views.py:868`)
are intentional abstract methods on base classes.

---

## Features tested

Established from the route table and the model registry, not assumed.

| Feature | Implemented | Tested here |
|---|---|---|
| Customers (contacts, lead/customer stages, tags, notes) | Yes | Yes |
| Companies | Yes | Yes |
| Service addresses (properties, geocoding, map) | Yes | Yes |
| Estimates (quotes, line items, status transitions, photos) | Yes | Yes |
| Jobs (scheduling, crew assignment, status, reschedule, photos) | Yes | Yes |
| Invoices, payments, expenses | Yes | Yes |
| Financials and reports (+ CSV) | Yes | Yes |
| Time clock, payroll, performance | Yes | Yes |
| Tasks, follow-ups, business plans | Yes | Yes |
| Activities / timeline | Yes | Yes |
| Change log with undo (Owner-only) | Yes | Yes |
| Team messaging (channels, direct messages) | Yes | Partial |
| Users, roles, profiles, team view | Yes | Yes |
| Dashboard, search, notifications, settings, PWA | Yes | Yes |
| **Leads, Deals, sales pipeline** | **No — retired in Phase 18** | Redirects asserted |
| Data import | No | n/a |
| Email / SMS sending | No | n/a |

Leads and Deals were folded into Customers and Estimates in Phase 17
and the code removed in Phase 18 (ADR 0012). `/leads/` and `/deals/`
redirect permanently; their detail pages 404. Confirmed in the browser.

---

## Testing methodology

Tools chosen for value, not completeness, per the brief.

| Tool | Version | Used |
|---|---|---|
| Django test runner | 6.1.1 | Yes — the project's framework; pytest deliberately not adopted |
| ruff | 0.16.10 | Yes |
| bandit | 1.9.4 | Yes |
| pip-audit | 2.10.1 | Yes |
| Playwright + Chromium | current | Yes, in a separate virtualenv |
| `pg_restore` / Podman | PostgreSQL 18.6 | Yes — real containers, real archives |
| coverage.py | — | **Not installed, not added.** See below |
| mypy, shellcheck, hadolint | — | Not available; `sh -n` used for shell syntax |

**No line-coverage figure appears in this report.** Every defect found
here sat on a line already executed by a passing test, so the number
would have been actively misleading. Coverage is stated in
`docs/TEST_COVERAGE.md` as *what is asserted*.

Four principles drove the work:

1. **Build sweeps from introspection, never from a list.** The access
   sweep walks the URL resolver; the N+1 probe runs a seeding function
   at two volumes. The failure mode being guarded against is omission,
   and a hand-kept list is only as complete as its last edit.
2. **Mutation-check every guard.** A test that cannot fail proves
   nothing. Four were checked by breaking the thing they protect.
3. **Positive-control the browser harness.** Zero violations is
   meaningless until the harness has been seen reporting one.
4. **Assert on database state, not on page content.** A page can say
   "saved" while nothing was written.

---

## Test results

| | Count |
|---|---|
| Automated tests executed | **1,054** |
| Passed | **1,054** |
| Failed | 0 |
| Skipped | 0 in this environment (1 would skip without `pg_restore`) |
| Blocked | 0 |
| Added by this audit | 54, in 5 files |

```
Ran 1054 tests in 658.602s
OK
```

Beyond the suite:

| Check | Result |
|---|---|
| `ruff check .` | clean |
| `ruff format --check .` | clean, 296 files |
| `makemigrations --check --dry-run` | no changes detected |
| `check --deploy` (production settings) | no issues |
| `bandit -r apps config` (excl. tests/migrations) | 3 medium, all triaged false positives |
| `pip-audit -r requirements.txt` | no known vulnerabilities |
| Browser sweep | 342 loads, 0 problems |
| Browser acceptance run | 12 steps, 0 failed |
| Clean-database migrate | 45 forward, all 5 apps reverse to zero |
| Constraint audit | 26/26 present, 0 `NOT VALID` |

### Mutation checks performed

| Guard | Mutation | Result |
|---|---|---|
| Access sweep | Removed `SalesRoleRequiredMixin` from `CompanyDetailView` | Failed, both signed-out and role-less |
| N+1 probe | Dropped `select_related` from the Tasks hub | Failed: "grew by 15" for 15 extra rows |
| Backup integrity | Made the dump verification advisory instead of fatal | Failed |
| Browser CSP detection | Injected `style="color:red"` into a template | Reported the violation |

---

## Issues

| Severity | Found | Fixed | Remaining |
|---|---|---|---|
| CRITICAL | 0 | — | 0 |
| HIGH | 1 | 1 | 0 |
| MEDIUM | 0 | — | 0 |
| LOW | 1 | 0 | 1 (documented by decision) |

- **QA-001 (HIGH, fixed)** — a backup was never checked to be readable,
  and the restore destroyed the live database before looking at it.
- **QA-002 (LOW, documented)** — a timesheet's rows do not add up to
  its own total.

Full detail, reproduction steps, root causes and verification in
`docs/BUG_LOG.md`.

---

## Security findings

**No vulnerabilities found.** What was actually checked:

| Check | Finding |
|---|---|
| Anonymous access, all 94 routes | Nothing outside a 9-entry public allowlist answers 200. Mutation-checked |
| Signed in with **no role** | Reaches only their own account, the PWA shell, and a dashboard that computes nothing — asserted, not assumed |
| IDOR / row scoping | Another crew's job → 404; their photo → 404. Never 403 |
| XSS | **Zero** uses of `mark_safe`, `\|safe`, `format_html`, `eval`, `exec`, `subprocess`, `os.system`, `pickle` in application code |
| SQL injection | One raw cursor in the whole application: `SELECT 1` in the health check. Three bandit hits are all in migrations, with identifiers from `quote_name(Model._meta.db_table)` and parameterised values |
| CSRF | Enabled, `CSRF_COOKIE_HTTPONLY` on, every token server-rendered |
| Password handling | Django's hashers and validators, unmodified |
| Secrets | None in the repository. `.env.example` holds placeholders only. `DJANGO_SECRET_KEY` and the database password come from the environment |
| `DEBUG` | `False` in production settings; `check --deploy` clean |
| Error exposure | The health check returns `ok`/`error` per component and nothing more |
| Private media | Login-gated and scope-checked (Phase 18 unit 1, 18 tests) |
| Dependencies | Production set clean. Two dev-only transitive packages have advisories and do not ship |
| CSP | Verified in a real browser across 342 loads, positive-controlled |

The one bandit finding outside migrations is a test file's constant
named `PASSWORD`. Not a secret.

**Not attempted:** no live penetration testing, no fuzzing, no
timing-attack analysis, and nothing against production infrastructure
(forbidden by `CLAUDE.md` and by the brief).

---

## Performance findings

**No N+1 queries** on any of the 14 list and aggregate pages measured.
Each was loaded with 3 records and with 18; none grew by more than 3
queries, against a budget that 15 extra rows cannot hide in. The probe
is mutation-checked and now permanent.

Pages measured: Customers, Companies, Tasks, Activities, Calendar
(month), Estimates, Invoices, Payments, Expenses, Financials,
Dashboard, Search, Change log, Map.

The codebase earns this deliberately. `_sum_subquery` in
`apps/jobs/models.py` annotates sums as subqueries rather than joins,
with a comment explaining that joining would multiply rows into each
other's totals — and the audit confirmed it by annotating two sums on
one invoice and checking both. The `pk__in` subquery pattern is used
consistently for filters so `paginator.count` stays correct.

Not measured: load testing, sustained concurrency, or any timing
threshold. The demo seed's ~750 jobs render acceptably by hand but
nothing asserts a response time. 18 rows is enough to expose per-row
queries; it is not a load test.

---

## Regression results

The complete suite was executed after all modifications: **1,054 tests,
all passing, exit code 0**, captured to a file rather than piped
through `tail` (a pipeline reports the *last* command's status, which
masked a result earlier in this project's history).

- All 1,000 pre-existing tests still pass. None was weakened, skipped
  or deleted to accommodate a change.
- The two scripts modified are `backup.sh` and `restore.sh`. Both still
  pass `sh -n`, and the older existence check was kept alongside the
  new one rather than replaced — a missing file should be reported as
  missing, not as unreadable.
- `git diff` reviewed: changes are confined to the two scripts, five
  new test files and four new documents. **No application code was
  modified by this audit.**
- Migrations untouched; `makemigrations --check` reports no changes.

---

## Final application status

**PASS WITH WARNINGS.**

| Verification | Result |
|---|---|
| Application starts | Yes — development and production settings |
| Database operational | Yes — PostgreSQL, 45 migrations applied |
| Migrations verified | Yes — forward from empty, reverse to zero, ordering pinned |
| Backend operational | Yes — 1,054 tests |
| Frontend operational | Yes — 342 loads, 3 roles, 3 widths, 0 problems |
| Authentication operational | Yes — real sign-in and sign-out through the form |
| Permissions enforced | Yes — swept across every route, mutation-checked |
| Security checks completed | Yes — bandit, pip-audit, `check --deploy`, manual review |
| End-to-end tests completed | Yes — enquiry to paid invoice, verified in the database |

---

## Remaining work

### Before relying on the backups

1. **Run the restore drill** in `docs/TESTING_INSTRUCTIONS.md` §7 on a
   staging host. It includes a step that deliberately feeds a truncated
   dump to `restore.sh` and confirms it refuses *before* tearing the
   stack down. If the stack comes down, QA-001 has regressed. This is
   the single most valuable thing left to do.

### Before production deployment

2. **Exercise the deployment path** — the Containerfile build on ARM64
   (`scripts/test-arm64.sh`), `deploy.sh` on staging, the systemd units
   starting and restarting, and the documented rollback.
3. **Confirm the off-host backup** with a real `restic` repository, and
   restore from it once.

### Worth knowing, not blocking

4. **QA-002** needs a product decision, not a fix. Showing durations as
   hours and minutes (`0:10`) and keeping the decimal total for pay is
   the likely answer.
5. **Concurrent edits are last-write-wins.** No mechanism, no test.
   Acceptable for a single-operator business; revisit before several
   people edit the same records.
6. **Dev-tooling advisories** clear with
   `pip install -U -r requirements-dev.txt`.
7. **Sourcery's review budget** was exhausted during Phase 18 and
   resets around 2026-10-13. PR #151, the largest diff of that phase,
   went in self-reviewed.
8. **No accessibility audit** has been run. Keyboard operability is
   asserted where it was an explicit design requirement; there is no
   project-wide check.

### Known limitations of this audit

- The access sweep sends GET requests only.
- The backup-script ordering tests read script text, which is weak by
  nature but is the only way to assert that a check precedes a
  destructive step.
- One test skips where `pg_restore` is absent, which may include CI. It
  announces the skip rather than passing quietly.
- Only Chromium was driven. No Firefox or WebKit.
- QA-002 is characterized, not fixed; its test will fail if someone
  improves the behaviour, which is intended.

### A note on side effects

Two things were changed outside the repository during this audit, both
in the **development** database only:

- `demo_owner`'s password was set to a temporary value so the browser
  acceptance run could use the real sign-in form. **Re-run
  `python manage.py seed_demo`, or set a new password, to restore it.**
- A test customer created through the browser was deleted afterwards,
  and a scratch database (`qa_audit_migrate_test`) was created for the
  clean-migration test and dropped.

No production system was touched, and no production secret was read.
