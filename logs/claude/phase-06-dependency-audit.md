# PHASE 06: DEPENDENCY SECURITY AUDIT (UNIT 3)

Started: 2026-09-13
Ended: 2026-09-13

## Objective

Third and final unit of Phase 6, per the roadmap: a dependency
security audit. Same severity-ranked review format as
`docs/DATABASE_REVIEW.md`/`docs/USABILITY_REVIEW.md`/
`docs/SECURITY_REVIEW.md`.

## Method

- `pip-audit -r requirements.txt` (already run before every commit
  throughout this project via `make security`) as the primary
  vulnerability scan.
- `gh api repos/.../dependabot/alerts` — GitHub's own Dependabot
  security alerts, distinct from the version-bump PRs, to check for
  anything open beyond what `pip-audit` itself sees.
- Reviewed and merged all 6 Dependabot PRs that had been open
  throughout the project (a recurring "not blocking anything" note in
  `docs/PROJECT_STATE.md` since early on, never actually resolved).
- For the 4 PRs touching real Python packages (`ruff`, `bandit`,
  `pytest-django`, `pre-commit`) — installed each new version locally
  and re-ran the actual check (`ruff check`/`format --check`, a full
  `bandit` scan, the full `manage.py test` suite) against the
  **current** codebase, rather than trusting each PR's own CI run from
  2026-09-11 against a much smaller codebase.
- `pip index versions <package>` for every pinned dependency in both
  `requirements.txt` and `requirements-dev.txt`.

## Files created / changed

- `docs/DEPENDENCY_AUDIT.md` — new, the audit document.
- `.github/dependabot.yml` — added the `pre-commit` ecosystem (see
  Errors below).
- `requirements-dev.txt` — `ruff` synced to `0.16.7` (see Errors
  below); also carries the four Dependabot-driven bumps from PRs
  #3/#5/#6/#7 (`pre-commit` 4.6.2, `pytest-django` 4.14.0, `bandit`
  1.9.4, plus the ruff sync).
- `.github/workflows/{ci,security}.yml` — `actions/setup-python`
  5→7 and `actions/checkout` 4→7, from Dependabot PRs #1/#2.

## Commands

$ Checked all 6 open Dependabot PRs' CI/mergeability, then updated
  each branch against current `main` one at a time
  (`gh api .../pulls/<n>/update-branch`), waiting for CI to re-run
  before merging — required because `main` had moved substantially
  since these PRs were opened and branch protection requires
  up-to-date branches (`strict: true`).
Result: PRs #1, #2, #3, #5, #6 merged cleanly in sequence.

$ Installed `ruff==0.16.6`, `bandit==1.9.4`, `pytest-django==4.14.0`,
  `pre-commit==4.6.2` locally (matching PRs #5, #7, #6, #3) and ran
  `ruff check .`/`ruff format --check .`, a full `bandit` scan, and
  the full `manage.py test` suite (296 tests) against the current
  codebase before merging each.
Result: PASS — all four clean against the current, much-larger
codebase than existed when Dependabot originally opened these PRs.

$ Merging PR #7 (bandit) last hit a genuine merge conflict on
  `requirements-dev.txt` (three of the other five PRs had already
  touched that file). Resolved via `git worktree add`, manually
  editing the conflicted file to keep the newest version of each
  line, committing the merge, and pushing to update the PR's branch
  before merging normally.
Result: PR #7 merged; `requirements-dev.txt` correct on `main`
afterward — verified directly, not just assumed from the merge
succeeding.

$ python manage.py test (full suite, after all 6 PRs merged and the
  venv synced to match)
Result: PASS — 296 tests, no change in count (dev-tooling bumps don't
add or remove test cases).

$ manage.py check / makemigrations --check --dry-run
Result: PASS — no schema changes this unit.

$ ruff check . / ruff format --check . / pip-audit / bandit (final
  pass, after the dependabot.yml + ruff-sync fix)
Result: PASS; no real findings.

Dev database confirmed clean throughout (no leftover test
users/companies from local verification).

## Tests

`python manage.py test` — 296 passed, 0 failures (unchanged from
before this unit — a dependency audit doesn't add test cases of its
own, beyond what each Dependabot PR's own re-verification already
exercised).

## Decisions

- Reviewed and merged all 6 open Dependabot PRs as part of this unit,
  rather than continuing to leave them open — "dependency security
  audit" is exactly the right moment to actually resolve a
  long-carried "not blocking anything" backlog item, confirmed with
  the user before proceeding (a genuine open question, not assumed).
- Re-verified each pip-tooling bump locally against the *current*
  codebase before merging, rather than trusting each PR's own
  (increasingly stale) CI run — the codebase has grown substantially
  since 2026-09-11 when these were opened, and a linter/security
  scanner/test-runner bump behaving differently against more code than
  existed at PR-creation time is a real, not hypothetical, risk.
- Did not manually bump `pip-audit` (2.9.0 → 2.10.1, one release
  behind) — this project's workflow already delegates routine version
  management to Dependabot; manually bumping ahead of it would be
  inconsistent with that. The `ruff` sync was different in kind: it
  corrected an actual cross-file inconsistency already present in the
  repo (two different pins for the same tool), not just "behind
  latest" — a real bug, not a routine update.

## Errors

**Found during this unit's own audit, not something a prior unit had
introduced:** `.github/dependabot.yml` only configured the `pip` and
`github-actions` ecosystems. `.pre-commit-config.yaml` pins its own
tool versions independently (`rev: v0.16.7` for `ruff-pre-commit`) — a
third place a version lives that no Dependabot PR reviewed in this
unit ever touched, because Dependabot wasn't watching it at all. This
had already silently drifted: `.pre-commit-config.yaml` was on ruff
`v0.16.7` while `requirements-dev.txt` (even after merging PR #5) was
still on `0.16.6`. Confirmed Dependabot does support a `pre-commit`
ecosystem for exactly this case (checked GitHub's own documentation
rather than assuming), added it, and synced the two `ruff` pins —
verified clean against the current codebase before syncing, not just
assumed safe because `0.16.6` already passed.

Also noted, not an error but worth recording: `pytest-django` is an
unused dev dependency — neither the `Makefile` nor CI ever invoke
`pytest`, every test run in this project goes through `manage.py test`.
Its version bump (PR #6) was functionally inert either way. Not
removed in this unit (a separate scope decision), but documented so a
future audit doesn't have to rediscover it.

## Lessons learned

- A repository's dependency-pinning surface can be wider than the one
  file (`requirements.txt`/`requirements-dev.txt`) a routine review
  would default to checking — `.pre-commit-config.yaml`,
  `.github/workflows/*.yml`, and any tool-specific config each pin
  their own versions independently, and a dependency audit should
  check all of them, not just the obvious one.
- Sequentially merging several Dependabot PRs that touch the same file
  will eventually produce a real merge conflict once enough of them
  land — not a sign anything is wrong, just an expected consequence of
  parallel single-line changes to a short file. Worth planning for
  rather than being surprised by.
- Mid-unit, the user changed the repository from public to private —
  this silently changed Sourcery's own access (its free tier doesn't
  cover private repos), producing a different message than its usual
  rate-limit notice ("Your private repo does not have access to
  Sourcery"). Confirmed with the user this was an intentional action
  before treating it as anything other than expected.

## Git

Branch: `security/dependency-audit` (merged, deleted)
Commit: `c81d66a`
Merged to `main`: `d24d3db` (regular merge commit, PR #47 — CI green,
`mergeStateStatus: CLEAN`; Sourcery unavailable this unit due to the
repo's visibility changing to private, not a rate-limit)

Also merged this unit (each its own separate PR/merge, not part of
`security/dependency-audit`): Dependabot PRs #1 (`actions/setup-python`
5→7), #2 (`actions/checkout` 4→7), #3 (`pre-commit` 4.3.0→4.6.2), #5
(`ruff` 0.14.4→0.16.6), #6 (`pytest-django` 4.11.1→4.14.0), #7
(`bandit` 1.8.6→1.9.4).

## Next

Phase 6 (Security hardening) is now fully complete (all 3 units:
Security audit, Role/permission model, Dependency security audit).
Next is Phase 7 — Containerization with Podman.
