# Application logging review

Phase 12 unit 2 — the review named in the roadmap: what this project
logs, what it never does, and whether anything sensitive ends up in
logs. Same format as `docs/DATABASE_REVIEW.md`/`docs/SECURITY_REVIEW.md`/
`docs/BACKUP_DR_AUDIT.md`: findings checked empirically, fixed where
safe, deferred with reasoning where not.

## Method

- Read Django's actual default logging behavior from its own source
  (`django.utils.log.DEFAULT_LOGGING`, `django.utils.log.log_response`,
  `django.utils.log.request_logger`) rather than from memory or
  documentation summaries.
- Grepped the entire codebase for existing `logging`/`logger` usage
  and any stray `print()` calls that would bypass the logging
  framework entirely.
- **Simulated Django's own exception-logging call directly** (the
  exact call `django.utils.log.log_response` makes on every unhandled
  view exception — confirmed by reading its source, not assumed) under
  both `config.settings.development` and `config.settings.production`,
  via `manage.py shell`, and observed what actually printed.
- Considered how log output actually reaches an operator in production
  today — journald via the container runtime, the same mechanism every
  prior phase's live testing has already relied on and confirmed
  working for gunicorn/Caddy/PostgreSQL's own output.

## HIGH

### 1. Unhandled exceptions logged nowhere at all in production

Django's own default logging (`django.utils.log.DEFAULT_LOGGING`,
active in full since this project defined no `LOGGING` setting of its
own) gates its only console handler behind
`django.utils.log.RequireDebugTrue`. Its one production-active
handler, `mail_admins`, is a silent no-op without `ADMINS`/email
settings configured — which this project has never set.

**Confirmed live, not assumed from reading Django's source**: called
`logging.getLogger("django.request").error(..., exc_info=True)` —
exactly what `django.utils.log.log_response` calls on every unhandled
view exception (verified by reading `log_response`'s own source: its
default `logger` parameter is `django.utils.log.request_logger`, which
`is` `logging.getLogger("django.request")`) — via `manage.py shell`
under real `config.settings.production`. **Zero output.** The same
call under `config.settings.development` printed a full traceback, as
expected. A real production 500 error, today, would leave literally no
trace anywhere an operator could find it — not in `journalctl`, not
anywhere — only the generic 500 page the site visitor sees.

**Status: FIXED.** Added a `LOGGING` setting to `config/settings/
base.py` (shared by both environments): the `django` logger gets its
own unconditional (not DEBUG-gated) `StreamHandler`, `propagate=False`
so it isn't double-handled; everything else (this project's own
module-level loggers, e.g. `apps/core/views.py`'s health-check
failure log) reaches a root-level `StreamHandler` via normal Python
logging propagation. No file handler, no custom formatter, no
third-party log-shipping — a plain stream to stdout is enough, since
journald (via the container runtime) already timestamps and persists
everything this container prints, the same mechanism this project's
gunicorn/Caddy/PostgreSQL logs already reach an operator through.

Re-verified live after the fix, via the real settings modules (not a
manual `dictConfig` simulation): both `django.request` and an
`apps.core.views`-style app logger now produce output under
`config.settings.production`, each exactly once (checked specifically
for the duplicate-logging failure mode a first draft of this fix
produced under `config.settings.development` — see Errors, below).
Regression tests added in `apps/core/tests/test_logging_settings.py`,
using `assertLogs` to verify real propagation through the actual
configured logger tree, not just that `settings.LOGGING`'s dict
happens to contain the right-looking keys.

## Checked and confirmed solid (not just assumed)

- **No sensitive data appears in what gets logged.** Django's
  `django.request` logging (`log_response`) only ever includes the
  request path, method, and status code — never the request body, so
  POST credentials (the login form) never appear. No application code
  anywhere logs a password, token, or session identifier — confirmed
  by grepping every `logging`/`logger` call in the codebase (the one
  health-check call logs only "could not reach the database").
- **No stray `print()` statements** anywhere in `apps/`/`config/`
  (excluding tests/migrations) that would bypass the logging framework
  and its now-consistent behavior entirely.
- **`django.security.*` loggers** (CSRF failures, disallowed hosts,
  etc.) are children of `django`, so they're covered by this fix's
  handler the same way `django.request` is — no separate configuration
  needed.
- **`django.server`** (the `runserver` dev-server's own request
  logging) was never affected by the gap this unit fixed — Django's
  own default gives it an always-on handler already, unrelated to the
  `DEBUG` gating that affected `django`/`django.request`. Irrelevant to
  production anyway, since gunicorn (not `runserver`) serves production
  traffic.
- **gunicorn's own access/error logs** (`Containerfile`'s
  `--access-logfile - --error-logfile -`) and **Caddy's/PostgreSQL's**
  own logging were already reaching an operator correctly via journald
  — established and repeatedly confirmed throughout Phases 7-11's own
  live testing, unaffected by (and unrelated to) this unit's fix, which
  is specifically about *Django's own* internal logging.
- **`AuditLogEntry`** (Phase 4) is a distinct, database-stored
  mechanism — who changed which Company/Contact/Lead/Deal record, and
  when — not routed through Python's `logging` framework at all, and
  out of this review's scope for that reason. Already reviewed for its
  own concerns (XSS in the history display, cross-user visibility)
  during Phase 4's own adversarial review pass.

## LOW

### 2. 4xx responses now also log as warnings in production (an expected side effect, not a problem)

`django.request`'s `log_response` logs 5xx responses as errors and 4xx
as warnings by default. Since the `django` logger's `level` is `INFO`
(admits `WARNING` and above), this unit's fix means a 403 (permission
denied, Phase 6) or an anonymous scanner's 404 now also produces a
journald line, where before it produced nothing (same root cause as
the HIGH finding — it was never really "intentionally suppressed," it
was silently dropped along with everything else).

**Status: not a defect, informational only** — this is a small,
low-traffic self-hosted CRM, not a public high-traffic site; the
resulting log volume is modest, and journald handles it without any
special configuration. Worth noting explicitly so a future reader
comparing before/after log volume understands why it changed, rather
than mistaking it for a new problem.

### 3. No log level is configurable per-environment beyond what's hardcoded

`LOGGING`'s `level: "INFO"` is fixed in `config/settings/base.py`, not
read from an environment variable. **Status: not fixed, deferred** —
no concrete need for this has come up (this project doesn't yet run
anywhere that would want, say, `DEBUG`-level logging turned on
temporarily without a code change), and adding an env-var-driven log
level for a need that doesn't exist yet would be exactly the kind of
speculative addition CLAUDE.md's "do not overengineer" rule asks to
avoid. Revisit if a real operational need for it shows up.

## Errors

One real bug found and fixed while designing this unit's own fix — not
from an automated review (repo is private, so Sourcery doesn't review
it; this unit's own live verification, run twice — once to find the
gap, once to find the fix's own bug — already served that purpose):

1. A first draft of the `LOGGING` fix added a root-level console
   handler *without* also setting `propagate: False` on the `django`
   logger. Confirmed live: under `config.settings.development`, a
   simulated `django.request` error printed **twice** — once via
   Django's own (DEBUG-gated) console handler, once via propagation to
   the new root handler. Fixed by explicitly redefining the `django`
   logger with its own unconditional handler and `propagate: False`,
   then re-verified live that both environments now produce each
   message exactly once.

## Recommendation

One real HIGH finding, found and fixed in this unit: production
silently dropped every unhandled exception's log output, with no
operator-visible trace anywhere. Confirmed live, not assumed — both
the original gap and the fix, including a real duplicate-logging bug
the fix's own first draft introduced and then had fixed and
re-verified. Everything else checked (sensitive-data exposure, other
loggers, how logs actually reach an operator) came back solid. The two
LOW items are informational/deliberately deferred, not silent gaps.
