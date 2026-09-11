# 0002 — PostgreSQL as the only database backend

## Context

Django ships SQLite support out of the box and it's the path of least
resistance for local development. The CRM also needs a production database
suitable for concurrent writes, real constraints, and a straightforward
backup/restore story on a Raspberry Pi.

## Alternatives considered

- **SQLite in development, PostgreSQL in production**. Rejected: the two
  engines diverge on constraint enforcement, concurrency behavior, and
  some SQL semantics — bugs caused by that divergence would only surface
  in production, which defeats the purpose of a development environment.
- **MySQL/MariaDB**. Rejected: no concrete advantage over PostgreSQL for
  this project, and PostgreSQL has stronger constraint/indexing features
  the CRM's relational data (companies/contacts/deals) benefits from.
- **A managed cloud database**. Rejected: contradicts the self-hosted,
  single-Raspberry-Pi deployment goal, and introduces an external
  dependency and cost with no matching requirement.

## Decision

Use PostgreSQL as the only supported database backend, in every
environment (development, test, production), with `psycopg2-binary` as
the driver.

## Reason

Eliminates dev/prod parity risk, gives the CRM real constraint enforcement
and indexing, and PostgreSQL runs comfortably on a Raspberry Pi 5.

## Consequences

- Local development requires a running PostgreSQL instance (documented in
  `README.md`), rather than a zero-setup SQLite file.
- `pg_hba.conf` needed a scoped `scram-sha-256` rule for the app role,
  since the system default is `ident` for local TCP connections (see
  `logs/system/2026-09-10-pg-hba-scram-auth.md`).
- Backups, restore testing, and disaster recovery (later phases) are
  planned around `pg_dump`/`pg_restore`, not a file-copy story.

## Date

2026-09-10
