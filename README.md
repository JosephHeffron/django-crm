# Django CRM

Self-hosted CRM built as a Django monolith with server-rendered templates
and PostgreSQL. See `CLAUDE.md` for the development contract (including AI
operating rules — `docs/AI_RULES.md` has the detailed procedures), and
`docs/ARCHITECTURE.md` / `docs/ROADMAP.md` for the system design and phased
build-out plan. `docs/PROJECT_STATE.md` has the current status snapshot.

## Development setup

Requirements: Python 3.12 (via pyenv), PostgreSQL, git.

### 1. Create the virtual environment

```sh
pyenv local 3.12.6
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pre-commit install
```

`requirements-dev.txt` adds linting (`ruff`), testing (`pytest`/
`pytest-django`), and security scanning (`bandit`, `pip-audit`) on top of
the runtime dependencies. `pre-commit install` wires up the hooks in
`.pre-commit-config.yaml` so lint/format/basic secret checks run before
every commit. Or use `make setup` to do the venv + install in one step.

### 2. Create the development database

```sh
sudo -u postgres createuser --login --pwprompt django_crm
sudo -u postgres createdb -O django_crm django_crm
```

PostgreSQL's default `pg_hba.conf` uses `ident`/`peer` authentication for
local connections, which will reject password-based logins over
`localhost`. Add a `scram-sha-256` rule for this role/database above the
generic `ident` line in `/var/lib/pgsql/data/pg_hba.conf`:

```
host    django_crm      django_crm      127.0.0.1/32            scram-sha-256
host    django_crm      django_crm      ::1/128                 scram-sha-256
```

Then reload PostgreSQL: `sudo -u postgres psql -c "SELECT pg_reload_conf();"`.

### 3. Configure environment variables

```sh
cp .env.example .env
```

Edit `.env` and set:
- `DJANGO_SECRET_KEY` — generate with
  `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` — matching the role/database created above.

`.env` is loaded automatically by `manage.py` (via `python-dotenv`) and is
gitignored — never commit it.

### 4. Run migrations

```sh
python manage.py migrate
```

### 5. Create a superuser

```sh
python manage.py createsuperuser
```

### 6. Run the development server

```sh
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` for the root page and `/admin/` for the
Django admin.

## Common commands

```sh
make test       # python manage.py test
make lint       # ruff check + ruff format --check
make security   # pip-audit + bandit
make check      # manage.py check + makemigrations --check
make migrate    # manage.py migrate
make shell      # manage.py shell
```

## Git workflow

`main` is protected. Work happens on `feature/*`, `fix/*`, `chore/*`, or
`security/*` branches; changes reach `main` via pull request with CI
(`.github/workflows/ci.yml`, `security.yml`) passing. See `CLAUDE.md`'s
Git/GitHub policy for the full rules.

## Project layout

See `docs/ARCHITECTURE.md` for the full breakdown of `config/` (project
wiring) vs. `apps/` (domain apps: `core`, `users`, `crm`).
