# PHASE 14: ADMIN AND DEVELOPER GUIDES (UNIT 1)

Started: 2026-09-17
Ended: 2026-09-17

## Objective

First of two Phase 14 units, per the roadmap: `docs/ADMIN_GUIDE.md`
and `docs/DEVELOPER_GUIDE.md` — the documentation half of
"Documentation and handoff," the project's final phase.

## Files created / changed

- `docs/ADMIN_GUIDE.md` — new. Task-oriented documentation for
  operating this CRM in production: first-time deployment, day-to-day
  operations, deploying updates, backups, disaster recovery, known
  limitations.
- `docs/DEVELOPER_GUIDE.md` — new. Orientation for a future
  contributor: where to start, project layout, common tasks, the
  git/PR workflow, how to use `logs/claude/`'s build history.

## Commands

$ Identified the actual gap these docs fill: `docs/CLEAN_ENVIRONMENT_
  TEST.md` (Phase 13 unit 2) already noted that `README.md` documents
  only native dev setup, with no consolidated documentation of the
  production deployment path anywhere — that path's knowledge was
  scattered across `docs/ARCHITECTURE.md`, `docs/DISASTER_RECOVERY.md`,
  `docs/BACKUP_DR_AUDIT.md`, `docs/PRODUCTION_READINESS.md`, and
  several scripts'/systemd units' own header comments. Wrote
  `docs/ADMIN_GUIDE.md` specifically to close that gap by
  consolidating, not duplicating — every non-trivial claim links back
  to whichever document already verified it.

$ Spot-checked factual claims against the actual codebase before
  writing them, rather than from memory:
  - Grepped for `JsonResponse`/`api/` across `apps/` and
    `config/urls.py` to confirm `/health/` really is the only
    JSON/API-style endpoint in the project, before stating that in
    `docs/DEVELOPER_GUIDE.md`.
  - Confirmed `CompanyListView`/`CompanyDetailView`/
    `CompanyCreateView` actually live in `apps/crm/views.py`, matching
    the example cited.
  - Diffed the exact install commands quoted for
    `systemd/crm-backup.service` against that file's own header
    comment, to avoid transcribing a stale or slightly-off command
    sequence into a doc real operators will follow verbatim.

$ `ruff check .` / `manage.py check`
Result: PASS (docs-only unit, no application code).

$ `python manage.py test` (full suite)
Result: PASS — 303 tests (unchanged).

## Tests

`python manage.py test` — 303 passed, 0 failures.

## Decisions

- Deliberately wrote both guides as *pointers with just enough
  standalone content to be useful*, not full restatements of every
  underlying document — a guide that duplicates
  `docs/DISASTER_RECOVERY.md`'s full procedure inline would drift out
  of sync with it the next time that procedure changes, whereas a
  guide that links to it stays correct by construction.
- `docs/ADMIN_GUIDE.md`'s "Known limitations" section explicitly
  defers to `docs/PRODUCTION_READINESS.md` as the single source of
  truth for the complete, current list, rather than keeping its own
  parallel copy that could silently fall out of date — it restates
  only the two items most operationally relevant to a reader about to
  actually deploy (off-host backups, no real hardware yet).
- `docs/DEVELOPER_GUIDE.md` explicitly names this project's AI-
  assisted development process and the verification discipline behind
  it, rather than treating that as an implementation detail invisible
  to a future contributor — the phase logs under `logs/claude/` are a
  real, load-bearing part of this project's documentation, and a
  reader who doesn't know they exist would miss a lot of useful
  context.

## Errors

None — this unit involved no live infrastructure testing, and the
factual spot-checks performed came back confirming what was already
known rather than surfacing anything new.

## Lessons learned

- Documentation that consolidates scattered knowledge is itself a
  form of technical debt reduction — the fact that
  `docs/CLEAN_ENVIRONMENT_TEST.md`'s own walkthrough had to hunt
  across a dozen files to reconstruct "how do I actually deploy this"
  is direct evidence this gap was real and worth closing, not a
  speculative nice-to-have.
- Even a docs-only unit benefits from the same "verify, don't assume"
  discipline this project has applied to code throughout — a wrong
  command in an admin guide is a real operational hazard the first
  time someone actually runs it during an incident, not a harmless
  typo.

## Git

Branch: `feature/admin-developer-guides`
Commit: `c441d58`
Merged to `main`: `fdc6386` (regular merge commit, PR #78 — CI green:
`test` + `dependency-audit` both pass)

## Next

Phase 14 unit 2 — final repository cleanup. Phase 14 is not yet
complete — `docs/ROADMAP.md` stays unchecked until unit 2 also merges.
