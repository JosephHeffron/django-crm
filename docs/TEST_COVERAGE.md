# Test coverage — QA audit, 2026-10-11

What is covered by automated tests, what was covered by hand during the
audit, and — the part that matters most — what is **not** covered.

No line-coverage percentage appears in this document. `coverage.py` is
not installed and was not added: the audit brief asks not to introduce
dependencies without value, and a line-coverage number would be the
least informative thing here. Every defect this audit found sat on a
line that was already executed by a passing test. Coverage below is
stated as *what is asserted*, which is the thing that actually protects
the application.

## Totals

| | Count |
|---|---|
| Test files | 70 |
| Tests | 1,059 |
| Added by this audit | 59, in 5 files |
| Mutation-checked during the audit | 5 guards |

The figures above are the audit's own, kept as a record of what it
measured on 2026-10-11. The suite has grown since; `python manage.py
test` prints the current count (1,196 as of 2026-10-21). What has
**not** changed is the method or anything in "Not covered", below —
read that section before trusting a number.

## Added by this audit

| File | Tests | What it protects |
|---|---|---|
| `apps/core/tests/test_access_sweep.py` | 10 | Every route, against signed-out and role-less visitors, built by walking the URL resolver |
| `apps/core/tests/test_query_counts.py` | 14 | N+1 queries on 14 list and aggregate pages |
| `apps/core/tests/test_backup_integrity.py` | 15 | QA-001: a backup must be readable, and verified before the restore destroys anything. QA-003: the right container image validates it |
| `apps/jobs/tests/test_money_and_hours_invariants.py` | 15 | Money and hours where rounding can make figures disagree; QA-002 characterized |
| `apps/jobs/tests/test_end_to_end_workflow.py` | 5 | The whole business sequence, enquiry to paid, asserted against the database |

The access sweep and the query-count probe are both built from
**introspection rather than from a list** — the resolver in one case,
a seeding function run twice in the other. That is deliberate. The
failure mode they guard against is omission, and a hand-maintained list
of routes or pages is only ever as complete as the person who last
edited it.

## Mutation testing since the audit

The audit mutation-checked 5 guards. That has since become the default
for anything new, because three separate findings this project has made
were **tests that could not fail for the reason they claimed** — an
`assertIn("275", body)` that the average-job-value card also satisfied,
an `assertContains` on a create link that the navigation menu carries
on every page, and a paging test seeded only with matching rows.

The three owner-reported units of 2026-10-17..19 ran 50 mutations
between them, which caught four weaknesses in the tests themselves and
one wrong explanation in a comment. What the exercise is worth
recording for: **a mutation that does not apply reports success.** A
`str.replace` whose anchor had been reflowed by `ruff format` has
reported "OK" here more than once. Every mutation run asserts the edit
landed before trusting the result.

## Python coverage, by area

| Area | Covered | Notes |
|---|---|---|
| Models (30 across 5 apps) | Yes | Field defaults, constraints, `on_delete`, computed properties |
| Forms | Yes | Validation, cross-field rules, formset sizing, querysets scoped through `access.py` |
| Views (94 routes) | Yes | Every route reached by the access sweep; feature behaviour per app |
| Business logic | Yes | Money, hours, status transitions, scheduling, follow-ups, reports |
| Permissions and row scoping | Yes | Per role, plus the sweep; out-of-scope is 404 not 403 |
| Data migrations | Yes | Phase 17 fold and its reverse, against historical migration state |
| Schema migrations | Yes | Forward on an empty database, reverse to zero, ordering pinned |
| Management commands | Partial | `seed_demo` and `generate_followups` covered; see gaps |
| Shell scripts | Partial | Ordering and the validation primitive; see gaps |

## Database coverage

- Every one of the 26 Django-declared constraints confirmed present in
  `pg_constraint`, none `NOT VALID`.
- All 87 foreign keys confirmed `NO ACTION` at the PostgreSQL level —
  i.e. `on_delete` is implemented by the ORM in Python, as
  `CLAUDE.md` states. **Anything bypassing `Model.delete()` /
  `QuerySet.delete()` will not cascade, set-null or protect.**
- 45 migrations apply forward on a genuinely empty database; all five
  apps reverse cleanly to zero.
- Query growth measured on 14 pages at two data volumes.
- CRUD exercised through real HTTP requests, not direct ORM writes, in
  the end-to-end workflow test.

## Security coverage

| Checked | How |
|---|---|
| Anonymous access, all routes | Automated sweep, mutation-checked |
| Role enforcement, including "signed in with no role" | Automated sweep |
| IDOR / row scoping | Another crew's job and photo → 404 |
| Session handling, sign-out | Browser acceptance run and workflow test |
| CSRF | Every form server-renders its token; `CSRF_COOKIE_HTTPONLY` is on, so no script can read the cookie |
| XSS | Zero escape-hatch calls in application code; Django autoescaping relied on |
| SQL injection | One raw cursor in the app (`SELECT 1`); three bandit hits in migrations triaged |
| Production settings | `check --deploy` clean; strict CSP verified in a real browser |
| Dependency advisories | `pip-audit` against production requirements: none |
| Static analysis | `bandit` across `apps/` and `config/` |
| Private media | Covered by Phase 18 unit 1's own 18 tests |

## Frontend coverage

Real Chromium under production settings (`DEBUG=False`, the strict CSP),
not a mock.

- 57 pages × 3 roles (Owner, Sales Rep, Cleaner) × 3 widths (1280,
  834, 390) = **342 page loads**, asserting on CSP violations, console
  errors, failed requests, 5xx responses and horizontal overflow.
- A 12-step acceptance run driving the real sign-in form, creating a
  record, checking validation refuses an empty form, searching for the
  record, and signing out.
- **Positive-controlled.** An inline style was injected into a template
  and the harness reported the violation; without that control the
  zero-violation result would have been unfalsifiable. Note the control
  initially reported nothing because `DEBUG=False` makes Django cache
  templates in memory — a template change needs a server restart. That
  is recorded in `docs/TESTING_INSTRUCTIONS.md`.

## Not covered — be aware of these

### Infrastructure that needs real hardware or a running stack

- **A full restore against a live stack.** QA-001's fix is verified for
  its validation primitive (in a real `postgres:18-alpine` container,
  against four corrupt archives) and for its ordering, but the complete
  `restore.sh` path — teardown, volume import, `pg_restore`, health
  check — was not executed. It needs the production compose stack.
  **This is the most important untested path in the project**, and
  `docs/TESTING_INSTRUCTIONS.md` has the manual procedure.
- **`backup.sh` and `restore_offhost.sh` end to end**, including
  `restic` and the off-host push.
- **ARM64.** `scripts/test-arm64.sh` exists and was not run; it needs
  `qemu-user-static` and builds the whole image.
- **The Containerfile build** and the deployed stack under Podman.
- **`deploy.sh`.** Never run by this audit, by policy.
- **systemd units.** Inspected, not started.
- **Caddy.** The config is asserted via `caddy adapt` by existing
  tests; no live proxy was run here.

### Application paths not exercised

- **Geocoding against the real Nominatim service.** Stubbed, on
  purpose — the project has made the mistake of calling it for real
  once already.
- **Concurrent modification.** Two people editing one record at the
  same time is not tested. There is no optimistic-locking mechanism, so
  last-write-wins is the behaviour; no test pins it.
- **Real file uploads at scale.** Photo processing is covered by Phase
  18 unit 2's tests with real images; sustained upload volume is not.
- **Email.** Nothing in the app sends any, so there is nothing to test.
- **Load and realistic data volume.** The N+1 probe uses 18 rows, which
  is enough to expose per-row queries but is not a load test. The demo
  seed's ~750 jobs and ~1,000 contacts render acceptably by hand; no
  timing threshold is asserted anywhere.
- **Browsers other than Chromium.** No Firefox or WebKit run.
- **Accessibility.** No automated audit (axe or similar). Keyboard
  operability of specific features is asserted where it was a design
  requirement — the reschedule controls, for instance — but there is no
  project-wide check.

### Known limitations of the method

- **The access sweep sends GETs.** A POST-only endpoint that wrongly
  accepted an anonymous POST would not be caught by it. Per-feature
  tests cover the POST endpoints individually.
- **`test_backup_integrity.py`'s ordering tests read script text.**
  That is weak by nature. It is the only way to assert "the check runs
  before the destructive step", and it would catch the check being
  deleted or moved, which is the realistic regression.
- **One test in that file skips** where no `pg_restore` is installed.
  It says so when it skips rather than passing quietly. Checked after
  the audit: GitHub's runner ships `pg_restore`, and the CI run on
  PR #153 reported 1,054 tests with **no skips**, so the assertion does
  execute there. A runner image without postgresql-client would lose
  it.
- **QA-002 is characterized, not fixed.** The test asserts today's
  behaviour, so it will fail if someone improves it. That is intended:
  it makes the change deliberate.

## Where the real risk sits

Ranked by what would hurt most and is least protected:

1. **Restore.** Untested end to end, and the one operation that
   destroys data on purpose. QA-001 narrowed the window; it did not
   close the testing gap.
2. **Deployment.** No automated verification of `deploy.sh`, the image
   build, or the systemd units in place.
3. **Concurrency.** Last-write-wins with no test and no mechanism.
   Fine for one business; worth knowing before adding staff.
