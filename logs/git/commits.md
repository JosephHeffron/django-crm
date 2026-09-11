# Commit log

One entry per meaningful commit. Format:

```
YYYY-MM-DD
Branch: <branch>
Commit: <short hash>
Message: <first line of commit message>
Tests: <N passed>
Migration: <migration filename, or "none">
Reviewer: Human
Status: READY
```

## Entries

2026-09-10
Branch: main
Commit: 7fd6941
Message: Establish development contract and git baseline
Tests: none yet (docs only)
Migration: none
Reviewer: Human
Status: READY

2026-09-10
Branch: main
Commit: 9226fd4
Message: Add architecture and roadmap documentation
Tests: none yet (docs only)
Migration: none
Reviewer: Human
Status: READY

2026-09-10
Branch: main
Commit: 33a3b2f
Message: Bootstrap Django project with PostgreSQL
Tests: 0 passed (no tests exist yet)
Migration: none (built-in Django migrations only)
Reviewer: Human
Status: READY

2026-09-11
Branch: main
Commit: 7849b9d
Message: Establish formal AI development governance rules
Tests: 0 passed (no tests exist yet)
Migration: none
Reviewer: Human
Status: READY

2026-09-11
Branch: main
Commit: 10a6768
Message: Add CI, pre-commit, and dev tooling foundation
Tests: 0 passed; ruff check/format, pip-audit, bandit all pass
Migration: none
Reviewer: Human
Status: READY

2026-09-11
Branch: main
Commit: f3f8b18
Message: Add architectural decision records and durable project state
Tests: none yet (docs only)
Migration: none
Reviewer: Human
Status: READY

2026-09-11
Branch: main
Commit: ac992da
Message: Apply ruff formatting to existing Phase 0/1 code
Tests: 0 passed (manage.py check/test re-verified unchanged)
Migration: none
Reviewer: Human
Status: READY

2026-09-11
Branch: main
Commit: 55c3bdf
Message: Backfill commit log and finalize this phase's log
Tests: none (docs only)
Migration: none
Reviewer: Human
Status: READY

2026-09-11
Branch: main (merged from chore/close-governance-phase, PR #8)
Commit: 0a4e827
Message: Close out the AI governance phase (#8)
Tests: test + dependency-audit passed on PR
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 nitpick addressed)
Status: READY

2026-09-11
Branch: main (merged from dependabot/pip/pytest-9.1.1, PR #4)
Commit: 67b0c23
Message: Bump pytest from 8.4.2 to 9.1.1 (#4)
Tests: test + dependency-audit passed on PR
Migration: none
Reviewer: Human (Dependabot PR, fixes GHSA-6w46-j5rx-g56g)
Status: READY

2026-09-11
Branch: main (merged from feature/database-design, PR #9)
Commit: 66820dd
Message: Design the CRM database schema before implementing it (#9)
Tests: test + dependency-audit passed on PR (docs-only change)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 5 findings addressed —
  2 real defects fixed, 3 clarified as accepted trade-offs)
Status: READY

2026-09-11
Branch: main (merged from chore/close-phase-2-design, PR #10)
Commit: cdc1dc6
Message: Close out Phase 2 database design (#10)
Tests: test + dependency-audit passed on PR (docs/logs only)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 2 nitpicks fixed —
  an arithmetic error and an overstated claim)
Status: READY

2026-09-11
Branch: main (merged from feature/crm-models, PR #11)
Commit: a11444c
Message: Implement CRM models from the database design (#11)
Tests: 38 passed; test + dependency-audit passed on PR
Migration: crm.0001_initial, crm.0002_deal_deal_probability_between_0_and_100
Reviewer: Human (+ sourcery-ai bot review, 2 real gaps fixed —
  Deal.probability range not enforced, Activity editable via admin)
Status: READY

2026-09-11
Branch: main (merged from chore/close-phase-2-models, PR #12)
Commit: 7c026be
Message: Close out Phase 2 model implementation (#12)
Tests: test + dependency-audit passed on PR (docs/logs only)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 finding fixed —
  stale ROADMAP.md/DATABASE_DESIGN.md status after model implementation)
Status: READY

2026-09-11
Branch: main (merged from chore/mark-session-paused, PR #13)
Commit: 70455de
Message: Mark session paused for easy resume (#13)
Tests: test + dependency-audit passed on PR (docs only)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 finding fixed —
  pause marker referenced a not-yet-created file)
Status: READY

2026-09-11
Branch: main (merged from feature/database-review, PR #14)
Commit: 4d6f920
Message: Review the implemented CRM schema against the design doc (#14)
Tests: 38 passed (unaffected); test + dependency-audit passed on PR
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 2 findings fixed —
  an unsound SET_NULL recommendation, an overly reassuring
  "nothing contradicts the design" claim)
Status: READY

2026-09-11
Branch: main (merged from chore/close-phase-2-review, PR #15)
Commit: ab8eb18
Message: Close out Phase 2 database review (#15)
Tests: test + dependency-audit passed on PR (docs/logs only)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 3 findings fixed —
  stale ROADMAP status, MEDIUM finding undercount, contradictory
  Known Issues section)
Status: READY

2026-09-11
Branch: main (merged from feature/authentication, PR #16)
Commit: 9b9f57c
Message: Add authentication and a minimal base template shell (#16)
Tests: 48 passed (10 new); test + dependency-audit passed on PR
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 real bug fixed —
  NoReverseMatch on successful password change)
Status: READY

2026-09-11
Branch: main (merged from chore/close-phase-3-unit-1, PR #17)
Commit: 76d7283
Message: Close out Phase 3 unit 1 (authentication) (#17)
Tests: test + dependency-audit passed on PR (docs/logs only)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 finding fixed —
  missing Leads/Deals unit in PROJECT_STATE's Phase 3 sequence)
Status: READY

2026-09-11
Branch: main (merged from feature/navigation-shell, PR #18)
Commit: edf4ef8
Message: Add full navigation, error pages, and styling refinement (#18)
Tests: 52 passed (14 new); test + dependency-audit passed on PR
Migration: none
Reviewer: Human (+ sourcery-ai bot review, no findings — first clean
  review in this project's history)
Status: READY

2026-09-11
Branch: main (merged from chore/close-phase-3-unit-2, PR #19)
Commit: 57b779b
Message: Close out Phase 3 unit 2 (navigation shell) (#19)
Tests: test + dependency-audit passed on PR (docs/logs only)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 finding fixed —
  test-count arithmetic error, 14 new claimed vs 4 actual)
Status: READY

2026-09-11
Branch: main (merged from feature/companies-crud, PR #20)
Commit: aa246cb
Message: Add Companies CRUD (list/detail/create/edit/delete, search, filter, pagination) (#20)
Tests: 78 passed (up from 52); test + dependency-audit passed on PR
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 real finding fixed —
  hard-delete contradicted docs/DATABASE_DESIGN.md's documented
  never-hard-delete-from-UI invariant; reworked to deactivation)
Status: READY

2026-09-11
Branch: main (merged from chore/close-phase-3-unit-3, PR #21)
Commit: 7fa1fe1
Message: Close out Phase 3 unit 3 (Companies CRUD) (#21)
Tests: test + dependency-audit passed on PR (docs/logs only)
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 1 finding fixed —
  phase log's stale "delete" wording after the deactivate rework)
Status: READY

2026-09-11
Branch: main (merged from feature/contacts-crud, PR #22)
Commit: 48fcda1
Message: Add Contacts CRUD (list/detail/create/edit/deactivate, search, filter, pagination) (#22)
Tests: 107 passed (up from 78); test + dependency-audit passed on PR
Migration: none
Reviewer: Human (+ sourcery-ai bot review, 3 real findings fixed —
  missing company-filter UI control, pagination dropping the company
  filter, 500 on a non-numeric company param)
Status: READY
