# Dependency security audit

Phase 6 unit 3 — the final Phase 6 unit, per the roadmap. Same
severity-ranked-findings format as `docs/DATABASE_REVIEW.md`/
`docs/USABILITY_REVIEW.md`/`docs/SECURITY_REVIEW.md`, adapted to
dependencies specifically: what's currently pinned, whether any of it
has known vulnerabilities, and what was outstanding in Dependabot.

## Method

- `pip-audit -r requirements.txt` (the same command already run before
  every commit throughout this project, via `make security`) — the
  primary vulnerability-scanning tool for this audit.
- `gh api repos/.../dependabot/alerts` — GitHub's own Dependabot
  security alerts for this repo (distinct from the version-bump PRs
  Dependabot also opens), to check for anything currently open beyond
  what `pip-audit` itself would catch.
- Reviewed and merged all 6 Dependabot PRs that had been open
  throughout the project (noted repeatedly in `docs/PROJECT_STATE.md`'s
  "Currently working on" section as "not blocking anything," but never
  actually resolved until this unit).
- For the 4 PRs bumping actual Python packages used by local tooling
  (`ruff`, `bandit`, `pytest-django`, `pre-commit`) — rather than trust
  each PR's original CI run (from 2026-09-11, against a much smaller
  codebase than exists now) — installed each new version locally and
  re-ran the real check (`ruff check`/`ruff format --check`, a full
  `bandit` scan, the full `manage.py test` suite) against the **current**
  codebase before merging.
- `pip index versions <package>` for every pinned dependency (both
  `requirements.txt` and `requirements-dev.txt`) to check how current
  each pin is against what's actually available.

## Findings

### No open vulnerabilities

`pip-audit -r requirements.txt` reports **no known vulnerabilities** —
consistent with every prior run throughout this project. The one
Dependabot security alert that exists for this repo (pytest's
vulnerable tmpdir handling, medium severity) is already in the
`fixed` state — it was resolved by PR #4 (`pytest` 8.4.2 → 9.1.1)
earlier in the project, well before this unit. No currently-open
alerts.

### All three production dependencies are already at the latest available version

| Package | Pinned | Latest on PyPI |
|---|---|---|
| `Django` | 6.1.1 | 6.1.1 |
| `psycopg2-binary` | 2.9.13 | 2.9.13 |
| `python-dotenv` | 1.2.3 | 1.2.3 |

Nothing to do here — the small, deliberately minimal production
dependency list (three packages, per `docs/ARCHITECTURE.md`'s
"prefer Django's built-in functionality" philosophy) is fully current.

### Six open Dependabot PRs, all now reviewed and merged

All six were isolated, single-purpose version bumps to dev/CI tooling
— none touched a runtime dependency:

| PR | Change | Verification before merging |
|---|---|---|
| #1 | `actions/setup-python` 5 → 7 | CI-only change; merged, next CI run confirmed it works |
| #2 | `actions/checkout` 4 → 7 | Same |
| #3 | `pre-commit` 4.3.0 → 4.6.2 | `pre-commit validate-config` against the current `.pre-commit-config.yaml` |
| #5 | `ruff` 0.14.4 → 0.16.6 | `ruff check .` / `ruff format --check .` against the current codebase (not just the PR's stale 2026-09-11 CI run) |
| #6 | `pytest-django` 4.11.1 → 4.14.0 | Full `manage.py test` (296 tests) — see note below on why this bump is actually inert |
| #7 | `bandit` 1.8.6 → 1.9.4 | Full `bandit` scan against the current codebase |

All six merged (each required an explicit approval, per
`CLAUDE.md`'s GitHub Policy — "reviewed and merged like any other
PR, never auto-merged"). One genuine merge conflict came up merging
PR #7 last (`requirements-dev.txt` had already been touched by three
of the other five merges) — resolved by hand in a scratch worktree,
verified the resolved file matched exactly what had already been
locally tested, then pushed to update the PR's branch before merging
it normally.

### `pytest-django` is an unused dev dependency

Not a new finding from this unit specifically, but worth recording
here since the audit touched it directly: `requirements-dev.txt` lists
`pytest-django`, but neither the `Makefile`'s `test` target nor
`.github/workflows/ci.yml` ever invoke `pytest` — every test run in
this project, from Phase 0 onward, goes through `manage.py test`
(Django's own runner). `pytest-django`'s version bump (PR #6) was
therefore functionally inert either way. **Not removing it** in this
unit — that's a scope decision belonging to whoever set up the
original dev tooling in Phase 0, not something to unilaterally prune
during a security audit — but noted here so it's a known, documented
fact rather than something a future audit rediscovers from scratch.

### `.pre-commit-config.yaml` wasn't tracked by Dependabot at all — a real gap, now closed

`.github/dependabot.yml` only configured the `pip` and `github-actions`
ecosystems. `.pre-commit-config.yaml` pins its own tool versions
independently (`rev: v0.16.7` for `ruff-pre-commit`) — a **third**
place a version lives, invisible to every Dependabot PR reviewed
above. This had already silently drifted: `.pre-commit-config.yaml`
was pinned to ruff `v0.16.7` while `requirements-dev.txt` (post-merge)
was still on `0.16.6` — a real, if minor, inconsistency nothing would
have caught.

**Status: FIXED.** Added a `pre-commit` entry to
`.github/dependabot.yml` (Dependabot has supported this ecosystem for
exactly this purpose), and synced `requirements-dev.txt`'s `ruff` pin
to `0.16.7` to match — verified clean (`ruff check .` /
`ruff format --check .`) against the current codebase before syncing.

### One dev dependency remains one release behind the absolute latest

| Package | Pinned (now) | Latest on PyPI |
|---|---|---|
| `pip-audit` | 2.9.0 | 2.10.1 |

A very recent release Dependabot hasn't opened a PR for yet (it runs
on its own schedule). **Not bumped manually in this unit** — this
project's whole workflow already delegates routine dependency version
management to Dependabot rather than ad hoc manual bumps (the ruff fix
above was different: it corrected an actual cross-file inconsistency
already present in the repo, not just "behind latest"). Dependabot
will open a PR for this on its next scan, reviewed the same way the
six above were.

## What's solid

- `pip-audit` has been run before every single commit throughout this
  entire project (via `make security`, part of the standard
  pre-commit verification stack) — this unit didn't introduce that
  practice, it's been continuous since Phase 0.
- Dependencies are pinned to exact versions everywhere (`==`, not
  `>=`), for both `requirements.txt` and `requirements-dev.txt` —
  reproducible installs, and every version change is a deliberate,
  reviewed diff (whether from Dependabot or manual), never a silent
  drift.
- The production dependency list is deliberately minimal (three
  packages) — smaller attack surface almost by construction, not
  something this audit had to argue for.
- GitHub's secret scanning and push protection are already enabled
  (public repo default, confirmed during the original GitHub setup in
  Phase 0/1) — outside `pip-audit`'s scope, but a real part of this
  repo's dependency/supply-chain security posture.

## Recommendation

No open vulnerabilities, no HIGH or MEDIUM findings. All six
previously-open Dependabot PRs are now merged, closing out a
recurring "not blocking anything, but never resolved" item that had
been carried in `docs/PROJECT_STATE.md` since early in the project.
The two dependencies one release behind will be picked up by
Dependabot's own next scheduled scan, same as always — no ad hoc
manual bump needed now. **Phase 6 (Security hardening) is now fully
complete.**
