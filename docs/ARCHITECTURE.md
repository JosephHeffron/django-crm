# Architecture

## Overview

The CRM is a single Django monolith, server-rendering all pages, backed by a
single PostgreSQL database. There is no separate frontend build, no API
gateway, and no background task queue in the initial architecture — those are
only added later if a concrete need is demonstrated.

```
Internet / LAN
      |
      v
    Caddy            (HTTPS termination, reverse proxy, static files)
      |
      v
Django application   (Gunicorn in production, runserver in development)
      |
      v
  PostgreSQL          (single primary database)
```

## Django project structure

```
django-crm/
├── manage.py
├── config/                  # project-level configuration, no domain logic
│   ├── settings/
│   │   ├── base.py          # shared settings
│   │   ├── development.py   # local dev overrides (DEBUG=True, dev hosts)
│   │   └── production.py    # production overrides (security, hosts, TLS)
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── core/                # cross-cutting: health checks, base templates,
│   │                         #   shared utilities, error pages
│   ├── users/                # authentication, permissions, user profile
│   └── crm/                  # domain: companies, contacts, leads, deals,
│                              #   activities, tasks, search, dashboard
├── templates/                # project-level template overrides/base layout
├── static/                   # project-level CSS/JS
├── media/                    # user-uploaded files (gitignored)
├── containers/
│   ├── django/Containerfile
│   └── caddy/Caddyfile
├── compose/
│   ├── compose.dev.yml
│   └── compose.prod.yml
├── systemd/crm.service
├── scripts/{backup,restore,deploy}.sh
└── docs/
```

`config/` never contains CRM domain logic — it is wiring only. Each Django
app under `apps/` owns its own models, views, forms, templates, and tests.
`apps.core` exists for functionality that doesn't belong to a single domain
app (health endpoint, base template, shared template tags, error handlers).
`apps.users` owns authentication and permissions. `apps.crm` owns the actual
CRM domain objects.

Settings are split so that development and production never share
assumptions implicitly: `base.py` holds everything both need,
`development.py` and `production.py` each import `*` from `base` and only
override what differs (DEBUG, ALLOWED_HOSTS, security headers, static file
serving). Which module loads is controlled by the `DJANGO_SETTINGS_MODULE`
environment variable — nothing environment-specific is hardcoded into
`manage.py` or `wsgi.py`.

## Database architecture

- PostgreSQL is the only supported database backend, in every environment.
  SQLite is never used as the actual application database (Django's own
  internal tooling may reference it, but the project's `DATABASES` setting
  always points at PostgreSQL).
- Connection parameters (`NAME`, `USER`, `PASSWORD`, `HOST`, `PORT`) are read
  from environment variables at process start — never hardcoded, never
  committed.
- Every schema change goes through a Django migration. No manual schema
  edits.
- Indexes and constraints are decided per-model as CRM domain models are
  designed (see `docs/DATABASE_DESIGN.md`, written in a later phase).

## Container architecture

Three containers, run under Podman:

1. **Django application** — production image runs Gunicorn (not
   `manage.py runserver`), a non-root user, and takes all configuration from
   environment variables. No secrets baked into the image.
2. **PostgreSQL** — official PostgreSQL image, data on a named persistent
   volume so container recreation never loses data.
3. **Caddy** — terminates HTTPS, reverse-proxies to the Django container over
   the internal Podman network, serves static files efficiently, and is the
   only container that should ever be reachable from outside the host.

`podman-compose` wires these together for both local/staging use
(`compose.dev.yml`) and production (`compose.prod.yml`), with the production
file being the stricter of the two (no unnecessary host port exposure, health
checks, restart policies).

## Production deployment architecture

Production runs on a Raspberry Pi 5 (ARM64) under Podman, started and
supervised by a systemd unit (`systemd/crm.service`) so the stack survives
reboots and crashes without manual intervention. Deployment is a scripted,
non-destructive procedure (`scripts/deploy.sh`): pull the intended git
revision, build/pull ARM64 images, run migrations, restart, verify health,
and support rollback.

## Security boundaries

- Only Caddy is exposed to the LAN/Internet. Django and PostgreSQL are only
  reachable over the internal container network.
- Django never terminates HTTPS directly.
- Secrets (database credentials, `SECRET_KEY`, etc.) are supplied via
  environment variables / an untracked `.env` file, never committed and never
  baked into container images.
- Django's built-in authentication and permission system is used as-is
  unless a specific gap is found and documented.
- `DEBUG=False`, a real `ALLOWED_HOSTS`, and secure cookie/session settings
  are mandatory in production configuration.

## Backup strategy

PostgreSQL is backed up with scheduled logical dumps (`pg_dump`), stored
outside the database container, with a retention policy and periodic restore
testing (see later roadmap phases — Backups, Restore testing). Application
media files and configuration (`.env`, Caddy certificates/config) are backed
up alongside the database dump since they are equally required for recovery.

## ARM64 deployment strategy

All base images (Python, PostgreSQL, Caddy) must support `linux/arm64`.
Container builds are tested on the Fedora workstation using
`qemu-user-static` before ever being deployed to the physical Raspberry Pi,
so architecture-specific breakage is caught in development rather than in
production.
