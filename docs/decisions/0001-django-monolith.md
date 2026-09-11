# 0001 — Build the CRM as a single Django monolith

## Context

The CRM needs to serve a small number of users (initially the owner and a
handful of colleagues), with standard CRUD-heavy business workflows
(companies, contacts, leads, deals, activities, tasks). It will run on
modest hardware (a Raspberry Pi 5) with a single maintainer.

## Alternatives considered

- **Microservices** (separate services per domain area, communicating over
  HTTP/message queue). Rejected: adds network hops, service discovery,
  deployment coordination, and operational complexity with no matching
  benefit at this scale — nothing here needs independent scaling or
  independent deployment cadence.
- **Django + a separate API layer consumed by a JS frontend (SPA)**.
  Rejected: doubles the surface area (API contract, client-side state,
  build tooling) for a CRUD application that server-rendered templates
  handle natively and more simply.
- **A different backend framework** (FastAPI, Flask + extensions). Rejected:
  Django's batteries — ORM, admin, auth, forms, migrations — map directly
  onto CRM needs and reduce the amount of code written and maintained.

## Decision

Build the CRM as a single Django project: one deployable unit, one
database, server-rendered templates, Django's built-in auth and admin.

## Reason

Matches the actual scale of the problem (single maintainer, small user
count, standard CRUD workloads) and the project's own "do not overengineer"
principle. Django's built-ins directly cover most of what a CRM needs.

## Consequences

- Deployment is one container instead of several — simpler Podman/Caddy
  setup, simpler backups, simpler rollback.
- Scaling beyond a single process/host would require revisiting this
  decision — acceptable, since that's not a near-term requirement.
- All future feature work happens inside this one codebase; new
  infrastructure (queues, caches, separate services) requires the
  justification described in `CLAUDE.md`'s "do not overengineer" rule
  before being added.

## Date

2026-09-10
