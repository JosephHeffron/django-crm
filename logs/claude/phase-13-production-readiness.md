# PHASE 13: PRODUCTION READINESS AUDIT (UNIT 1)

Started: 2026-09-17
Ended: 2026-09-17

## Objective

First of two Phase 13 units, per the roadmap: a full architecture/
security/ARM64 audit (`docs/PRODUCTION_READINESS.md`) and remediation
of any critical/high findings.

## Files created / changed

- `docs/PRODUCTION_READINESS.md` — new. Synthesis of every prior
  review, fresh live re-verification, and one new finding (below).
- GitHub repository settings (not a file in this repo, but a real
  production-relevant change): visibility restored to public, branch
  protection on `main` restored, secret scanning/push protection
  re-enabled.

## Commands

$ Delegated a full read of every prior review/audit document
  (`docs/DATABASE_REVIEW.md`, `docs/SECURITY_REVIEW.md`,
  `docs/USABILITY_REVIEW.md`, `docs/PRODUCTION_CONFIG_REVIEW.md`,
  `docs/ARM64_REVIEW.md`, `docs/ARM64_TESTING.md`,
  `docs/BACKUP_DR_AUDIT.md`, `docs/DISASTER_RECOVERY.md`,
  `docs/LOGGING_REVIEW.md`, `docs/DEPENDENCY_AUDIT.md`,
  `docs/DATABASE_DESIGN.md`, `docs/PERMISSIONS.md`,
  `docs/PROJECT_STATE.md`) to a subagent, to build a complete inventory
  of every still-open, deferred, or accepted finding across the whole
  project without missing any buried in a document's own body rather
  than its "Recommendation" section. Returned 2 HIGH, 8 MEDIUM, 19
  LOW/informational items, plus design-level open questions in
  `docs/DATABASE_DESIGN.md`/`docs/PERMISSIONS.md`.

$ Fresh, live re-verification of a sample of the cheapest-but-most-
  safety-critical claims, rather than trusting the written record:
  - `manage.py check --deploy` (production settings, realistic random
    secret key) — clean.
  - `ruff check .` / `bandit -r apps config` / `pip-audit` — clean.
  - `\d+ crm_deal` in a live `psql` session — confirmed `Deal`'s three
    `CheckConstraint`s are still actually present at the database
    level, not just in a migration file.
  - GitHub Dependabot security alerts via the API directly (not just
    the open-PR list) — zero open alerts.
Result: no drift found anywhere checked — this project's actual state
still matches what its own documentation already claims.

$ Checked the GitHub repository's own current security configuration
  directly via the API — something no prior phase specifically
  covered.
Result: **found a new, real HIGH finding**. `gh api .../branches/main
--jq '.protected'` → `false`. `gh api .../branches/main/protection`
and `gh api .../rulesets` both → `403 "Upgrade to GitHub Pro or make
this repository public to enable this feature."` `gh api ... --jq
'.security_and_analysis'` → `null`. Branch protection and secret
scanning/push protection had been silently disabled on `main` ever
since the repo switched to private (both are gated behind GitHub Pro
for a private repo on the free plan) — confirmed directly, not
inferred from `CLAUDE.md`'s GITHUB POLICY, which was written when the
repo was still public and had gone stale without anyone noticing.

$ Presented the finding to the user as three real trade-off options
  (accept the gap while staying private; upgrade to GitHub Pro; make
  the repository public again) via `AskUserQuestion` — this was not
  something the audit should decide unilaterally. **User chose to
  make the repository public again.**

$ Executed and verified the fix:
  - `gh repo edit JosephHeffron/django-crm --visibility public
    --accept-visibility-change-consequences`, confirmed via `gh api
    ... --jq '{private, visibility}'` → `{"private":false,
    "visibility":"public"}`.
  - `gh api -X PUT .../branches/main/protection` with the exact
    settings `docs/PROJECT_STATE.md` records from the original Phase 0
    setup (PR required, `test`+`dependency-audit` required status
    checks, strict, no force-push, no deletion, conversation
    resolution required, `enforce_admins: true`) — confirmed via `gh
    api .../branches/main --jq '.protected'` → `true`.
  - Confirmed secret scanning, push protection, and Dependabot
    security updates all re-enabled automatically the moment the repo
    went public again (`security_and_analysis`), with no separate
    action needed for those.

$ `ruff check .` / `ruff format --check .` / `manage.py check`
Result: PASS (this unit is a review doc plus a GitHub settings change,
no application code).

$ `python manage.py test` (full suite)
Result: PASS — 303 tests (unchanged).

## Tests

`python manage.py test` — 303 passed, 0 failures.

## Decisions

- Presented the branch-protection finding to the user rather than
  choosing a remediation path unilaterally — `CLAUDE.md`'s own GITHUB
  POLICY says Claude "does not modify branch protection or repository
  security settings without explicit instruction," and this decision
  genuinely trades off cost vs. visibility vs. accepted risk in a way
  only the repository owner can weigh.
- Restored branch protection to the *exact* settings
  `docs/PROJECT_STATE.md` already recorded from the original setup,
  rather than reasoning out new settings from scratch — this is a
  restoration of known-good prior configuration, not a fresh design
  decision.
- Scoped this unit to synthesis, live re-verification, and remediation
  of HIGH findings only, per the roadmap's own wording
  ("remediation of critical/high findings") — deliberately did not
  attempt to fix any MEDIUM/LOW finding from prior reviews, even where
  a fix might have been technically straightforward, to avoid
  expanding this unit's scope beyond what was asked.

## Errors

None in the sense of a bug introduced or a broken assumption corrected
— this unit's "error" was substantive but different in kind from prior
units: not a defect in code, but a real configuration drift
(silently-lost GitHub protections) that had gone unnoticed since
whenever the repo switched to private, found only because this audit
specifically checked something no prior phase's scope covered.

## Lessons learned

- A written policy document (`CLAUDE.md`'s GITHUB POLICY) can silently
  go stale when the environment it describes changes (public → private
  repo) in a way nobody thought to re-verify against that policy —
  worth periodically checking policy claims against live reality, not
  just once at the time they were first established.
- GitHub's plan-gated features (branch protection, rulesets, secret
  scanning) fail *silently* from an API consumer's perspective in the
  sense that nothing actively breaks or alerts — a protected-looking
  workflow (PRs, CI, review) can keep functioning identically whether
  or not the underlying protection is actually being enforced, which
  is exactly why this went unnoticed for a while.
- A "final" audit's real value isn't just re-confirming what's already
  documented (though that's worth doing, and this unit found zero
  drift there) — it's also checking things genuinely outside every
  prior phase's stated scope, which is where this unit's one real
  finding came from.

## Git

Branch: `feature/production-readiness-audit`
Commit: `93c6c38`
Merged to `main`: `5909e9e` (regular merge commit, PR #74 — CI green:
`test` + `dependency-audit` both pass; Sourcery reviewed this PR too
(the repo is public again) but hit its free-tier review-budget limit
before producing line-level comments — only a summary/reviewer's
guide, no findings; this unit's own live verification already served
as the equivalent scrutiny regardless)

## Next

Phase 13 unit 2 — a clean-environment end-to-end test. Phase 13 is not
yet complete — `docs/ROADMAP.md` stays unchecked until unit 2 also
merges.
