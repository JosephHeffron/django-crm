# PHASE 12: APPLICATION LOGGING REVIEW (UNIT 2)

Started: 2026-09-17
Ended: 2026-09-17

## Objective

Second and final unit of Phase 12, per the roadmap: an application
logging review — what's logged, what never is.

## Files created / changed

- `config/settings/base.py` — added an explicit `LOGGING` setting (see
  below).
- `apps/core/tests/test_logging_settings.py` — new. Regression tests
  using `assertLogs` to verify real propagation through the actual
  configured logger tree.
- `docs/LOGGING_REVIEW.md` — new. Full findings write-up.

## Commands

$ Read `django.utils.log.DEFAULT_LOGGING`, `log_response`, and
  `request_logger` directly from Django's own installed source
  (`python -c "import inspect; ..."`), rather than from memory —
  confirmed `request_logger` genuinely `is`
  `logging.getLogger("django.request")`, and that Django's only
  production-active handler (`mail_admins`) requires `ADMINS` to do
  anything.

$ Grepped the whole codebase for `logging`/`logger` usage (found only
  Phase 12 unit 1's own health-check call) and for stray `print()`
  calls (found none).

$ **Simulated Django's actual exception-logging call directly**,
  under real `config.settings.production` via `manage.py shell`:
  `logging.getLogger("django.request").error(..., exc_info=True)`.
Result: **zero output**. The identical call under
`config.settings.development` printed a full traceback, as expected.
Confirmed a real, serious gap: an unhandled production view exception
today logs nowhere an operator could find it.

$ Designed a fix (an explicit `LOGGING` dict in `config/settings/
  base.py`), then **tested it live before applying it for real** —
  first as a standalone `logging.config.dictConfig()` call layered on
  top of real settings, checking exactly what Django's own
  `configure_logging` does (`dictConfig(DEFAULT_LOGGING)` then
  `dictConfig(user LOGGING)`, confirmed by reading
  `django.utils.log.configure_logging`'s source directly, not
  assumed) — this surfaced that a naive fix (just adding a root-level
  handler) would **duplicate** `django.request` log lines under
  `DEBUG=True`, since Django's own DEBUG-gated console handler and the
  new root handler would both fire. Fixed the design
  (`propagate: False` on an explicitly redefined `django` logger)
  before ever touching `base.py`, and re-verified the corrected design
  the same way — no duplication in dev, real output in production, for
  both `django.request` and a simulated `apps.core.views`-style app
  logger.

$ Applied the verified design to `config/settings/base.py`, then
  re-verified **through the real settings modules** (not a manual
  `dictConfig` layered on top) — `manage.py shell` under both
  `config.settings.development` and `config.settings.production`,
  confirming both `django.request` and `apps.core.views` messages
  print exactly once in each environment.

$ `ruff check .` / `ruff format --check .` / `bandit -r apps config
  -q` / `pip-audit` / `manage.py check` / `manage.py check --deploy`
  (realistic random secret key)
Result: PASS — pre-existing B106 test-fixture findings only from
bandit (unrelated, same baseline as every prior unit); `check
--deploy` confirms the new `LOGGING` setting introduces no deploy
warnings.

$ `python manage.py test` (full suite)
Result: PASS — 303 tests (299 + 4 new). The run itself now visibly
printed `PermissionDenied`/`Method Not Allowed` log lines from
existing tests that exercise 403/405 paths — a concrete, real-world
confirmation that the fix works, not just that the new tests pass in
isolation (this is also the LOW finding in `docs/LOGGING_REVIEW.md`
about 4xx responses now logging too, observed directly rather than
just reasoned about).

## Tests

`python manage.py test` — 303 passed, 0 failures.

## Decisions

- A plain `StreamHandler` to stdout, no file handler, no custom
  formatter, no third-party log-shipping library — journald (via the
  container runtime) already timestamps and persists everything this
  container prints, the same mechanism gunicorn/Caddy/PostgreSQL's own
  logs already reach an operator through (established and repeatedly
  confirmed throughout Phases 7-11). Adding a second log-delivery
  mechanism here would be redundant infrastructure this project's
  scale doesn't need.
- Explicitly redefined the `django` logger (with `propagate: False`)
  rather than relying purely on root-logger propagation for
  everything — the duplicate-logging bug found while *designing* the
  fix (not after shipping it) is exactly why: propagation alone was
  almost the shipped design, and would have shipped a real, if minor,
  regression (noisy duplicate tracebacks in local dev).
- Left 4xx-now-logging-too and no-configurable-log-level as
  deliberately deferred LOW items rather than "fixed" further — both
  are either an accepted, reasoned-through side effect of the real fix
  (not a new problem) or a speculative addition with no concrete need
  yet.

## Errors

One real bug, caught during this unit's own design/verification
process rather than after applying a change to the real codebase — not
from an automated review (repo is private, so Sourcery doesn't review
it; testing the fix's design live, before committing to it, served the
same purpose here even more directly than usual):

1. A first-draft fix design (root-level handler only, no `django`
   logger override) would have duplicated every `django.request` log
   line under `DEBUG=True`. Caught by testing the design itself live
   via a standalone `dictConfig` layered on real settings, before ever
   writing it into `config/settings/base.py` — the actual shipped
   change was already the corrected version.

## Lessons learned

- Testing a settings-config *design* live, before committing it to a
  settings file, catches bugs earlier and more cheaply than testing
  after the fact — this unit's duplicate-logging bug was found and
  fixed before it ever existed in `config/settings/base.py`'s history
  at all, not found-then-fixed as two separate commits.
- Reading a framework's own source for the *exact* call it makes
  (`request_logger` really is `django.request`, confirmed via
  `is`/`.name`, not inferred from documentation) is what made it
  possible to simulate the real failure precisely — a looser
  simulation ("some Django logger, error level") could easily have
  missed the specific propagation/handler-gating interaction that was
  the actual bug.
- A working test suite's own incidental output (the `PermissionDenied`
  lines that appeared once this fix was applied) can itself be a form
  of live verification — worth noticing, not just scrolling past.

## Git

Branch: `feature/logging-review`
Commit: `3efcfcb`
Merged to `main`: `46eb55a` (regular merge commit, PR #72 — CI green:
`test` + `dependency-audit` both pass; the repo is private now, so
Sourcery doesn't review it — expected, not an error, and this unit's
own live verification, including testing the fix's design before ever
writing it, already served as the equivalent scrutiny)

## Next

**Phase 12 (Logging and monitoring) is now fully complete** (both
units: health-check endpoint, application logging review). Next is
Phase 13 — Final production audit: a full architecture/security/ARM64
audit (`docs/PRODUCTION_READINESS.md`), remediation of any
critical/high findings, a clean-environment end-to-end test.
