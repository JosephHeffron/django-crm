# Testing instructions

How to run everything the QA audit ran, and the manual procedures for
the things it could not. Written for whoever picks this project up
next, including a future me.

Companion documents: `docs/QA_REPORT.md` (what was found),
`docs/BUG_LOG.md` (each issue), `docs/TEST_COVERAGE.md` (what is and is
not covered).

## 1. Environment

Development workstation: Fedora Linux, Python 3.12 via pyenv,
PostgreSQL, Podman.

```sh
pyenv local 3.12.6            # .python-version already pins this
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

`requirements-dev.txt` includes `requirements.txt`, so this installs
both the application and the tooling (ruff, bandit, pip-audit,
pre-commit).

`.env` is required and is **never** committed. Copy
`.env.example` and fill it in; it holds the database credentials,
`DJANGO_SECRET_KEY`, and `CRM_SUPPORT_EMAIL`. `manage.py` loads it via
`python-dotenv`, which is why no shell export is needed.

PostgreSQL is the only supported database — never SQLite, in
development or anywhere else (`CLAUDE.md`).

## 2. Database

```sh
python manage.py migrate
python manage.py seed_demo          # a realistic year of demo data
```

`seed_demo` prints a generated password for the demo accounts once. Set
`DEMO_USER_PASSWORD` to choose one instead.

Test databases are created and destroyed automatically by the test
runner and may be treated as disposable.

## 3. The test suite

The project uses **Django's own test runner**, not pytest. `pytest` is
present as a transitive dependency but no test is written against it,
and the audit did not change that.

```sh
python manage.py test                       # everything, ~11 minutes
python manage.py test apps.jobs             # one app
python manage.py test apps.core.tests.test_access_sweep
python manage.py test apps.jobs.tests.test_end_to_end_workflow -v 2
```

### Capturing the result correctly

**Do not pipe the runner into `tail` or `head`.** In a pipeline the
shell reports the *last* command's exit status, so a failing suite can
look like a success — and a test that prints to stdout (`seed_demo`
does) can push the summary out of a `tail` window. This caught the
audit out once.

```sh
python manage.py test > /tmp/suite.txt 2>&1; echo "exit=$?"
grep -E "^(Ran |OK|FAILED)" /tmp/suite.txt
```

### Don't move the tree under a running suite

Merging, checking out or editing files while the suite is reading them
produces failures that are real-looking and not real. Let it finish.

## 4. Gates

All four must pass before a merge.

```sh
ruff check .
ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py test
```

`make lint`, `make test`, `make check` and `make security` wrap these.

## 5. Security audit

```sh
# Static analysis, same scope as CI
bandit -r apps config -x '*/tests/*,*/migrations/*'

# Production dependencies — this is the scope that matters
pip-audit -r requirements.txt

# The whole local environment, including dev tooling
pip-audit

# Production settings, with the deployment checklist
DJANGO_ALLOWED_HOSTS=crm.example.com \
  DJANGO_SETTINGS_MODULE=config.settings.production \
  python manage.py check --deploy
```

`pip-audit` with no arguments reports advisories in development tooling
(`urllib3` via `requests`, `virtualenv` via `pre-commit`). Neither
ships: the production image installs `requirements.txt` only. See
`docs/BUG_LOG.md`.

`shellcheck` and `mypy` are not installed. Shell syntax was checked
with `sh -n`:

```sh
for f in scripts/*.sh; do
  if sh -n "$f"; then
    echo "OK $f"
  else
    exit 1
  fi
done
```

## 6. Browser testing

The point is to exercise the **real production Content-Security-Policy**,
which only exists in production settings, against a real browser.
Playwright lives in its own virtualenv so it never enters the project's
requirements.

### Set-up

```sh
python -m venv /tmp/pw-venv
/tmp/pw-venv/bin/pip install playwright
/tmp/pw-venv/bin/playwright install chromium
```

Create a settings module that keeps the policy and relaxes only what
plain HTTP on localhost needs. **Put it somewhere that is not garbage
collected.** It must stay out of the repository — it is a
production-settings shim and shipping it would be a mistake — but
`/tmp` is the wrong kind of "outside": a tmpfiles sweep removed both
this file and the Playwright virtualenv between two runs of the same
session. The failure that produced was misleading rather than obvious:
with its settings module gone, Django fell back to the core
`runserver`, which has no `--insecure`, so the error read
`unrecognized arguments: --insecure` and pointed at the flag instead of
at the missing file. `~/.local/share/django-crm-qa/` or similar is a
better home.

```python
# csp_test_settings.py — keep this OUTSIDE the repo
from config.settings.production import *  # noqa: F401,F403

SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]
CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:8768", "http://localhost:8768"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
```

### Running it

```sh
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost \
  PYTHONPATH=/path/to/csp-test \
  DJANGO_SETTINGS_MODULE=csp_test_settings \
  python manage.py collectstatic --noinput

DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost \
  PYTHONPATH=/path/to/csp-test \
  DJANGO_SETTINGS_MODULE=csp_test_settings \
  python manage.py runserver 127.0.0.1:8768 --noreload --insecure
```

Three things that will waste an hour if you miss them:

1. **`--insecure` is required.** With `DEBUG=False`, `runserver` serves
   nothing from `static/`, and you get dozens of MIME-type console
   errors that are the harness's fault, not the application's.
2. **`DEBUG=False` makes Django cache templates in memory.** A template
   edit does **not** take effect, even with `--noreload`. Restart the
   server. The audit's first positive control reported no violation for
   exactly this reason and nearly recorded a working check as broken.
3. **`collectstatic` first**, or the same 404s appear.

### Compare text case-insensitively

`innerText` returns text **as rendered**, and this project's tables
apply `text-transform: uppercase` to their headers and row labels. A
check for `"Jobs done"` fails against a page that renders
`JOBS DONE` — eight assertions in the Phase 20 browser pass failed that
way, all of them the harness's fault rather than the application's.
Django's `assertContains` is not affected: it reads the raw HTML, where
the original casing survives. Lower-case both sides, or assert on
`textContent` through `page.evaluate`.

### Assert on all of these

CSP violations, console errors, failed requests, any 5xx, and
horizontal overflow (`scrollWidth > innerWidth`). Visit as **Owner,
Sales Rep and Cleaner**, at **1280, 834 and 390** px. The audit ran 57
pages × 3 roles × 3 widths.

### Positive-control it, every time

A harness reporting zero problems is worthless until you have seen it
report one. Add `style="color:red"` to a template, restart the server,
reload, and confirm the violation appears. Then take it out.

### Stopping the server

By PID, never `pkill -f`:

```sh
ps -eo pid,args | awk '/manage.py runserver 127.0.0.1:8768/ && !/awk/ {print $1}' \
  | while read p; do kill "$p"; done
```

## 7. Manual procedures the automated suite cannot cover

### Restore — the most important untested path

QA-001's fix is verified for its validation step and its ordering, but
the complete restore has never been executed by a test. Do this on a
**staging host or a throwaway copy, never production**:

```sh
# 1. Take a backup. It now self-verifies; confirm you see the line.
scripts/backup.sh
#    expect: --- verifying the dump is readable ---

# 2. Confirm the dump is a real archive.
podman run --rm -v "$PWD/backups/<timestamp>:/b:ro,z" \
  docker.io/library/postgres:18-alpine pg_restore --list /b/db.dump | head

# 3. Confirm a corrupt dump is refused BEFORE anything is destroyed.
cp -a backups/<timestamp> backups/corrupt-test
head -c 2048 backups/<timestamp>/db.dump > backups/corrupt-test/db.dump
scripts/restore.sh corrupt-test --yes
#    expect: refusal, and the stack still running. If the stack comes
#    down, QA-001 has regressed.

# 4. Then a real restore, and verify the data came back.
scripts/restore.sh <timestamp> --yes
```

### Off-host backup

Needs a real `RESTIC_REPOSITORY` and credentials. See
`scripts/restore_offhost.sh` and `docs/ADMIN_GUIDE.md`.

### ARM64

```sh
sudo dnf install qemu-user-static
scripts/test-arm64.sh
```

Builds the whole image under emulation. Slow.

### Deployment

`scripts/deploy.sh`, by a human, with explicit authorization. Never
automated, never run by an assistant (`CLAUDE.md`).

## 8. The whole QA pass, in order

```sh
# 1. Gates
ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run

# 2. Suite, captured properly
python manage.py test > /tmp/suite.txt 2>&1; echo "exit=$?"
grep -E "^(Ran |OK|FAILED)" /tmp/suite.txt

# 3. Security
bandit -r apps config -x '*/tests/*,*/migrations/*'
pip-audit -r requirements.txt
DJANGO_ALLOWED_HOSTS=example.com DJANGO_SETTINGS_MODULE=config.settings.production \
  python manage.py check --deploy

# 4. Migrations on a clean database (scratch DB, dropped afterwards)
#    See docs/QA_REPORT.md for the script the audit used.

# 5. Browser pass under production settings, positive-controlled

# 6. Manual restore drill on staging
```

## 9. Writing tests for this project

Conventions worth keeping, each learned the hard way:

- **Mutation-check any test guarding something that fails silently.**
  Break the thing on purpose and confirm the test fails. Then assert
  the mutation actually applied — a `str.replace` that matched nothing
  has reported "OK" here before.
- **Never let a test supply its own expected answer.** A `hasattr`
  fallback or a recomputation of the logic under test passes
  regardless.
- **Build sweeps from introspection, not from a list.** The URL
  resolver, the template directory, the model registry. A hand-kept
  list is only as complete as its last edit, and omission is the
  failure mode.
- **Pin the clock** for anything time-dependent. A test that passes at
  10am and fails at 6am is worse than no test.
- **Watch browser selectors.** `form button[type=submit]` matched the
  sidebar's Log out button during Phase 18.5 and destroyed the session
  mid-run three times.
- **Out of scope is 404, never 403.** A 403 confirms the record exists.
