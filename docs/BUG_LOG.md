# Bug log — QA audit, 2026-10-11

Every issue the audit found, with what was done about it. See
`docs/QA_REPORT.md` for method and scope, and `docs/TEST_COVERAGE.md`
for what was and was not covered.

Severity, as the audit brief defines it:

| Level | Meaning |
|---|---|
| CRITICAL | Data loss, unauthorized access, application-wide failure, severe security vulnerability |
| HIGH | Major functionality broken, incorrect business data, serious security weakness |
| MEDIUM | Significant feature defect with a workaround |
| LOW | Minor functional or presentation defect |

Summary: **1 HIGH, 1 LOW, 0 CRITICAL, 0 MEDIUM.** One fixed, one
documented with a characterization test rather than fixed, for the
reason given below. Three bandit findings triaged as false positives.

---

## QA-001 — A backup was never checked to be readable, and the restore destroyed the live database before looking at it

**Severity:** HIGH
**Status:** FIXED, regression-tested, mutation-checked
**Files:** `scripts/backup.sh`, `scripts/restore.sh`

### Description

`backup.sh` wrote `db.dump` and verified nothing about it.
`restore.sh` required only that the file *exist* — `[ -f "$SRC/$f" ]` —
and then removed the live `postgres_data` volume **before** `pg_restore`
ever opened the archive. A dump that was present but unusable therefore
cost the current database and gave nothing back.

The same script already guards the *volume* exports against exactly this
failure, with a comment recording that it was hit for real:

> `podman volume exists` is checked explicitly first … confirmed live
> that on this project's podman version, exporting a name that doesn't
> appear in `podman volume ls` can still exit 0 and silently produce a
> small, empty-looking tar … the backup "succeeded" with no error while
> quietly backing up nothing.

The database dump — the single most important artifact in the backup —
was the one thing with no equivalent check.

### Reproduction

1. Arrange for `db.dump` in a backup directory to be empty, truncated
   or otherwise unreadable. A failed `pg_dump` leaves a 0-byte file;
   measured during the audit.
2. `scripts/restore.sh <that timestamp> --yes`
3. The existence check passes. The stack comes down, `postgres_data` is
   removed, volumes are recreated, and only then does `pg_restore` read
   the archive and fail.

### Root cause

Existence was conflated with readability, and the only check sat on the
wrong side of the irreversible step.

Measured, before the fix:

| db.dump | `[ -f ]` (the old check) | `PGDMP` header | `pg_restore --list` |
|---|---|---|---|
| valid, 419 KB | accepted | accepted | accepted |
| 0 bytes | **accepted** | rejected | rejected |
| truncated to 2 KB | **accepted** | **accepted** | rejected |
| 3-byte stub | **accepted** | rejected | rejected |
| plain text | **accepted** | rejected | rejected |

A magic-byte check is not sufficient: it accepts the truncated archive,
and truncation is the realistic failure — a partial write, a full disk,
an interrupted stream. Only reading the archive's table of contents
catches all four.

### Fix

- **`backup.sh`** — after writing the dump, `pg_restore --list` it
  inside the already-running db container. On failure the existing
  `EXIT` trap removes the incomplete backup directory, so a bad backup
  is never recorded as a good one. This is the cheap place to catch it:
  the problem is harmless at that moment.
- **`restore.sh`** — in the pre-flight, *above* the first
  `podman volume rm`, read the archive's table of contents in a
  throwaway container built from the db service's own image (the host
  deliberately has no postgres client). `--list` only reads, and the
  mount is read-only, so the check cannot alter the backup. If the
  image is unavailable the check warns loudly and proceeds, rather than
  blocking a disaster recovery on a host with no network — the same
  reasoning that already makes the safety backup best-effort.

Verified in a real container, `docker.io/library/postgres:18-alpine`,
with the exact command the fix runs:

```
good.dump   ACCEPTED
empty.dump  REJECTED
trunc.dump  REJECTED
stub.dump   REJECTED
junk.dump   REJECTED
```

### Regression test

`apps/core/tests/test_backup_integrity.py` (10 tests).

- `test_restore_verifies_the_dump_before_destroying_anything` — the
  finding itself, as an ordering assertion against `podman volume rm`.
- `test_a_failed_verification_stops_the_restore` — a warning that
  carried on anyway would protect nothing.
- `test_pg_restore_rejects_every_damaged_archive` — the mechanism, on
  real corrupt archives.
- `test_a_truncated_archive_keeps_the_magic_bytes` — why a header check
  was rejected as the fix.

Mutation-checked: making the verification advisory instead of fatal
fails the suite.

One test in that file was itself wrong on the first run and is worth
recording, because it is the failure mode this project keeps meeting.
The ordering assertion searched the raw script text, found the phrase
`podman volume rm` inside the *comment* explaining the new check, and
concluded the check ran too late. It now strips comment lines first —
an ordering assertion has to look at commands, not at prose about
commands.

### Not covered

A full restore against a live stack. That needs the production compose
stack and real volumes, so it remains a manual step in
`docs/TESTING_INSTRUCTIONS.md`.

---

## QA-002 — A timesheet's rows do not add up to its own total

**Severity:** LOW
**Status:** DOCUMENTED, characterization test added, deliberately not changed
**Files:** `apps/jobs/templates/jobs/time_clock.html`, `apps/jobs/models.py` (`TimeEntry.hours`), `apps/jobs/crew.py` (`hours_in_period`)

### Description

`time_clock.html` prints `entry.hours` for each row, each rounded to two
places on its own, under a `<tfoot>` labelled **Total** holding
`week_hours`, which is rounded once from the summed durations.

Three ten-minute stretches display as `0.17`, `0.17`, `0.17` above a
total of `0.50`. The column adds to `0.51`.

### Reproduction

Clock three separate ten-minute entries in one week and open
`/time-clock/`. Asserted in
`test_the_timesheet_rows_do_not_always_add_up_to_its_own_total`.

### Root cause

Two different — and individually correct — rounding points.
`hours_in_period` sums durations in the database and rounds **once**,
which is the right order and the reason pay is exact.
`TimeEntry.hours` rounds each entry for display. Both are right; shown
together they look wrong.

### Why it is not fixed

Nothing is miscalculated and nobody is mispaid. The total is the
authoritative figure and is what `crew.payroll` computes pay from —
verified in `test_pay_is_computed_from_the_unrounded_period_total`.

Every available fix trades this for something worse:

- summing the displayed values would put rounding drift into pay;
- re-spreading the rounding residue across rows would print hours
  against a stretch the person did not actually work, on a document
  they are checking precisely to see what they worked;
- showing more decimal places makes a timesheet harder to read in
  exchange for hundredths of an hour.

The audit brief says to document an ambiguity rather than invent a
business rule, and the right answer here is a product decision — most
likely showing durations as hours and minutes (`0:10`) and keeping the
decimal total for pay. That is a UI change, not an audit fix.

### Characterization test

`test_the_timesheet_rows_do_not_always_add_up_to_its_own_total` asserts
the current behaviour, so changing it is a decision rather than an
accident, plus
`test_the_timesheet_page_really_does_show_both_figures`, without which
the first test would be a claim about a template nobody had checked.

---

## Triaged, not defects

### bandit B608 ×3 — "possible SQL injection"

`apps/jobs/migrations/0002_seed_service_catalog.py:53`,
`apps/jobs/migrations/0003_fold_leads_and_deals.py:174`,
`apps/messaging/migrations/0002_default_channels.py:34`.

All three are `schema_editor.execute(f"DELETE FROM {table} WHERE id = ANY(%s)", [pks])`
where `table` is `schema_editor.quote_name(Model._meta.db_table)` — a
quoted identifier from Django's own model metadata, never from a
request — and the values are parameterised. No user input reaches
either position. CI already excludes migrations from its bandit run
(`.github/workflows/security.yml`), so these do not appear there.

### pip-audit — 11 advisories in `urllib3` and `virtualenv`

Neither package ships. The production image installs
`requirements.txt` only (`Containerfile:18`), which is Django,
psycopg2-binary, python-dotenv, gunicorn and Pillow;
`pip-audit -r requirements.txt` reports **no known vulnerabilities**.
`urllib3` arrives via `requests` and `virtualenv` via `pre-commit`,
both local development tooling. CI audits `requirements.txt`, which is
the correct scope.

Worth keeping an eye on rather than acting on: these are dev-machine
advisories, so a `pip install -U -r requirements-dev.txt` clears them
when convenient.

---

## Checked and found sound

Recorded so a later audit does not have to re-derive it, and so the
absence of findings is legible as coverage rather than as silence.

| Area | Evidence |
|---|---|
| Anonymous access to all 94 app routes | Not one route outside a 9-entry public allowlist answers 200 while signed out. Mutation-checked by stripping a guard. |
| Role enforcement with no role assigned | Only their own account, the PWA shell and an intentionally-empty dashboard. |
| Row scoping (IDOR) | A crew member gets 404, not 403, for another crew's job and its photos. |
| XSS escape hatches | **Zero** uses of `mark_safe`, `\|safe`, `format_html`, `eval`, `exec`, `subprocess`, `os.system` or `pickle` in application code. |
| Raw SQL | One `connection.cursor()` in the whole app: `SELECT 1` in the health check. |
| Money arithmetic | Line totals exact to 4dp, sums never pre-rounded, no row multiplication across annotated sums, fractional invoices settle on a realistic payment. 15 tests. |
| Payroll | Durations summed before rounding; a missing rate reported, never guessed as zero. |
| N+1 queries | 14 list and aggregate pages load with 3 rows and with 18; none grew more than 3 queries. Mutation-checked by dropping a `select_related` (grew by exactly 15). |
| Database constraints | All 26 Django-declared constraints exist in `pg_constraint`; none `NOT VALID`. All 87 FKs `NO ACTION`, as `CLAUDE.md` documents. |
| Migrations | 45 apply forward on a genuinely empty database; **every app reverses cleanly to zero**. |
| Production settings | `manage.py check --deploy` reports no issues. |
| Frontend | 342 page loads (57 pages × 3 roles × 3 widths) under production CSP: 0 violations, 0 console errors, 0 failed requests, 0 server errors, no horizontal overflow. Positive-controlled. |
| End-to-end workflow | Enquiry → address → estimate → accept → schedule → complete → invoice → payment → paid, with the month's figures asserted. |
| Shell scripts | All 6 POSIX-clean, executable, `set -e`. No pipeline masks a failure that matters. |
| Placeholders | No TODO, FIXME, XXX or HACK anywhere. The two `NotImplementedError`s are intentional abstract methods. |
