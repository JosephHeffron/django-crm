# 0003 — Server-rendered UI with Django templates, no JS framework

## Context

The CRM's interface is standard business CRUD screens: lists, detail pages,
forms, a dashboard, search. It needs to be usable on desktop and
reasonably usable on mobile, maintained by a single developer.

## Alternatives considered

- **React/Vue SPA + a Django REST API**. Rejected: introduces a build
  toolchain (Node, bundler, package manager), a second language ecosystem
  to maintain, client-side state management, and an API contract layer —
  none of which this application's screens need. It would roughly double
  the code for the same functionality.
- **HTMX or a similar partial-page library**. Considered viable, but
  deferred: plain server-rendered templates plus small amounts of vanilla
  JS are sufficient for the initial CRUD-heavy scope. HTMX could be
  reconsidered later if specific pages need partial-page interactivity
  that plain forms/links can't express cleanly — that would need its own
  justification at the time.

## Decision

Use Django templates, HTML, CSS, and vanilla JavaScript only where
necessary (e.g. small UI affordances). No frontend framework, no separate
frontend build step, no client-side routing.

## Reason

Matches the project's own "prefer server-rendered pages" and "do not
overengineer" principles; a solo maintainer benefits from one language,
one templating system, and no build pipeline to keep working across
Fedora → Podman → Raspberry Pi.

## Consequences

- Static assets are plain CSS/JS served by Django/Caddy — no bundler, no
  `node_modules`, no separate frontend CI step.
- Interactive UI features are implemented with standard forms/links plus
  targeted vanilla JS, not component state.
- If a future page genuinely needs richer client-side interactivity, that
  requirement must be demonstrated concretely (per the "do not
  overengineer" rule) before adding any framework or library.

## Date

2026-09-10
