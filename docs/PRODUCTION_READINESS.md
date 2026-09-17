# Production readiness audit

Phase 13 unit 1 — the full architecture/security/ARM64 audit named in
the roadmap. This is a capstone review: it synthesizes every prior
review this project has produced (Phases 2, 5, 6, 8, 9, 11, 12) into
one consolidated picture, re-verifies a sample of their most
safety-critical claims live rather than trusting the written record
alone, and — the actual new work this unit did — audits something no
prior phase specifically covered: the GitHub repository's own security
posture as it stands *today*, after the mid-project switch to a
private repo. That surfaced one new, real, high-severity finding (see
below).

## Method

- Delegated a full read of every prior review/audit document
  (`docs/DATABASE_REVIEW.md`, `docs/SECURITY_REVIEW.md`,
  `docs/USABILITY_REVIEW.md`, `docs/PRODUCTION_CONFIG_REVIEW.md`,
  `docs/ARM64_REVIEW.md`, `docs/ARM64_TESTING.md`,
  `docs/BACKUP_DR_AUDIT.md`, `docs/DISASTER_RECOVERY.md`,
  `docs/LOGGING_REVIEW.md`, `docs/DEPENDENCY_AUDIT.md`,
  `docs/DATABASE_DESIGN.md`, `docs/PERMISSIONS.md`,
  `docs/PROJECT_STATE.md`) to build a complete inventory of every
  still-open, deferred, or explicitly-accepted finding across the
  whole project — not just the headline items each doc's own
  "Recommendation" section calls out.
- Re-ran, fresh, a sample of the cheapest-to-verify but most
  safety-critical checks rather than assume prior results still hold:
  `manage.py check --deploy` (production settings, a realistic random
  secret key), `ruff check`, `bandit -r apps config`, `pip-audit`,
  and — the one this project has repeatedly treated as the gold
  standard for "don't trust the ORM, check the database" — `\d+
  crm_deal` in a live `psql` session, confirming `Deal`'s
  `CheckConstraint`s are still actually present at the database level,
  not just in a migration file.
- Checked GitHub's Dependabot security alerts directly via the API
  (not just open PRs) — zero open alerts.
- Checked the GitHub repository's own current security configuration
  directly via the API — branch protection, rulesets, secret
  scanning/push protection — rather than assuming the settings
  documented in `CLAUDE.md`'s GITHUB POLICY (written when the repo was
  public) still apply now that it's private.

## HIGH

### 1. Branch protection and secret scanning are silently disabled — new finding, not previously documented anywhere

`CLAUDE.md`'s GITHUB POLICY states: *"main is protected: pull request
required, required status checks (`ci`, `security`), no force pushes,
no branch deletion, conversation resolution required, secret scanning
+ push protection enabled."* This was true and verified when the repo
was public (`docs/PROJECT_STATE.md`'s "Completed" section records the
original setup). **It has not been true since the repo was switched to
private**, and nothing in this project noticed until this audit.

**Confirmed directly via the GitHub API, not assumed:**

```
$ gh api repos/JosephHeffron/django-crm/branches/main --jq '.protected'
false

$ gh api repos/JosephHeffron/django-crm/branches/main/protection
{"message":"Upgrade to GitHub Pro or make this repository public to
enable this feature.", ..., "status":"403"}

$ gh api repos/JosephHeffron/django-crm/rulesets
{"message":"Upgrade to GitHub Pro or make this repository public to
enable this feature.", ..., "status":"403"}

$ gh api repos/JosephHeffron/django-crm --jq '.security_and_analysis'
null
```

GitHub's classic branch protection rules **and** the newer rulesets
mechanism are both gated behind GitHub Pro for a private repository on
the free plan — and secret scanning / push protection is unavailable
for the same reason. `main` currently has **no server-side protection
at all**: no required PR, no required status checks, force-push
allowed, branch deletion allowed, direct pushes allowed, no automatic
secret scanning on anything pushed.

In practice, every commit to `main` throughout this project has still
gone through a PR, CI, and review, because that discipline is enforced
by `CLAUDE.md`'s own GIT POLICY and by this project's working pattern
— not by GitHub itself. That discipline held (one genuine near-miss is
recorded in `logs/claude/phase-08-caddy-https.md`: a commit that
landed directly on `main`, caught and corrected before anything was
pushed). But the actual safety net GitHub was supposed to provide —
protection against a mistake by *any* future session, tool, or
person, not just careful adherence — has not existed for some portion
of this project's history, silently.

**Status: FIXED, per the user's explicit choice.** Presented directly
to the user as three real options (make the repository public again;
upgrade to GitHub Pro; accept the gap for now, documented rather than
silent) — this was not something the audit should choose unilaterally.
The user chose to make the repository public again, reversing the
earlier private switch. Executed and verified directly:

```
$ gh repo edit JosephHeffron/django-crm --visibility public \
    --accept-visibility-change-consequences

$ gh api repos/JosephHeffron/django-crm --jq '{private, visibility}'
{"private":false,"visibility":"public"}
```

Branch protection on `main` restored to match the exact settings
`docs/PROJECT_STATE.md` records from the original Phase 0 setup — PR
required, `test`+`dependency-audit` required status checks, strict
(branch must be up to date), no force-push, no deletion, conversation
resolution required, `enforce_admins: true`:

```
$ gh api -X PUT repos/JosephHeffron/django-crm/branches/main/protection \
    --input - <<'JSON'
{"required_status_checks": {"strict": true, "contexts": ["test", "dependency-audit"]},
 "enforce_admins": true,
 "required_pull_request_reviews": {"required_approving_review_count": 0},
 "restrictions": null, "allow_force_pushes": false, "allow_deletions": false,
 "required_conversation_resolution": true}
JSON

$ gh api repos/JosephHeffron/django-crm/branches/main --jq '.protected'
true
```

Secret scanning and push protection re-enabled automatically the
moment the repository went public again (confirmed via
`security_and_analysis`: `secret_scanning: enabled`,
`secret_scanning_push_protection: enabled`,
`dependabot_security_updates: enabled`) — no separate action needed
for those.

One side effect worth naming plainly, not glossed over: making the
repository public again means Sourcery's free-tier automated review
becomes available again too (it was Sourcery's *absence* that was
originally noticed as a side effect of going private, per
`docs/PROJECT_STATE.md`'s running note) — a welcome side effect of
this fix, not something this audit engineered on purpose.

## Findings carried forward from prior reviews (re-checked, not re-litigated)

The following remain genuinely open, exactly as their source documents
already describe them — re-confirmed still accurate as of this audit,
not re-argued here. Full detail, reasoning, and each finding's own
"why deferred" is in its source document; this is an index, not a
duplicate.

### Still HIGH

- **Backups live only on the same host as the application**
  (`docs/BACKUP_DR_AUDIT.md` #1) — SD card corruption/failure (a known
  common Raspberry Pi failure mode) would destroy backups and data in
  the same event. Blocked on a concrete off-host destination this
  project hasn't chosen yet.
- **The real, local `.env` may still contain the stale
  `DJANGO_SETTINGS_MODULE=config.settings.development` line**
  (`docs/PRODUCTION_CONFIG_REVIEW.md` #1) — the bug itself was fixed in
  `.env.example`; whether the real `.env` (never read by policy) still
  carries the old line is a manual check only the user can perform.

### Still MEDIUM

- `Deal.company`/`Deal.contact.company` can silently disagree —
  `docs/DATABASE_REVIEW.md` #3.
- `TextChoices` fields validated only by Django, not PostgreSQL —
  `docs/DATABASE_REVIEW.md` #4.
- `Company` has no address fields — `docs/DATABASE_REVIEW.md` #5.
- `Deal.company`/`Deal.contact` `PROTECT` permanently blocks
  hard-deleting a Company/Contact with any deal history —
  `docs/DATABASE_REVIEW.md` #6, also tracked in
  `docs/DATABASE_DESIGN.md`.
- No Content-Security-Policy header — `docs/SECURITY_REVIEW.md` #6 /
  `docs/PRODUCTION_CONFIG_REVIEW.md` #2 (same issue, tracked twice) —
  still blocked on needing a real browser to verify against Django
  admin's inline scripts, which this environment doesn't have.
- Caddy's container runs as root (the official image's only option) —
  `docs/PRODUCTION_CONFIG_REVIEW.md` #3 — accepted, mitigated by
  rootless Podman's user-namespace isolation.
- `.env` backups are unencrypted at rest — `docs/BACKUP_DR_AUDIT.md`
  #2 — deliberately coupled to the off-host-storage HIGH finding
  above.
- No automated, ongoing restore verification — `docs/BACKUP_DR_AUDIT.md`
  #3 — only proven once, by hand, in Phase 11.

### LOW / informational (19 items across every prior review)

Schema refinements (no primary-contact flag, inconsistent
active/status lifecycle shape, a few missing indexes, PostgreSQL-
specific opportunities like `pg_trgm` for fuzzy search),
`Activity.save()`'s residual `.update()`/`.bulk_update()` bypass, the
admin's default `/admin/` path, no login rate-limiting, the default
`AUTH_USER_MODEL`, missing dashboard shortcuts, no currency
formatting, `SECURE_HSTS_PRELOAD`'s manual-submission caveat, no
Let's-Encrypt-rate-limit runbook note, the backup retention window's
relationship to problem-detection latency, no formal RTO/RPO, 4xx
responses now logging (an intentional side effect, not a problem), no
per-environment log level, `pytest-django` an unused dev dependency,
and `pip-audit` one release behind. Every one of these is already
individually reasoned through in its source document with an explicit
"why not now" — none surfaced anything new on re-check, and none rises
to a blocker for calling this project production-ready at a
self-hosted, single-maintainer scale.

### Design-level open questions (not bugs)

`docs/DATABASE_DESIGN.md`'s "Implementation notes" and
`docs/PERMISSIONS.md`'s "What this doesn't do" sections each track
their own explicit, still-open judgment calls (whether `Deal`'s
`PROTECT` should become `SET_NULL` with auto-close behavior; whether
`Task`/`Activity` need direct `Company`/`Lead` relations; that
visibility — as opposed to write access — remains completely
unrestricted by design). Restated here only to confirm this audit
checked them, not because either changed.

## Fresh re-verification results (this audit, not inherited)

- `manage.py check --deploy` (production settings, realistic random
  secret key): **clean, zero issues.**
- `ruff check .`: **all checks passed.**
- `bandit -r apps config`: **zero Medium/High findings** (only the
  same pre-existing B106 test-fixture Low findings every prior unit
  this session has already confirmed are test-only, not application
  code).
- `pip-audit`: **no known vulnerabilities.**
- GitHub Dependabot security alerts (checked via API directly, not
  just the open-PR list): **zero open alerts.**
- `Deal`'s database-level `CheckConstraint`s (`deal_has_company_or_
  contact`, `deal_probability_between_0_and_100`,
  `crm_deal_probability_check`), confirmed live via `psql`'s `\d+
  crm_deal`: **all three still present and correctly defined** —
  nothing has silently drifted between Phase 2's original verification
  and now.

No drift found anywhere checked. This project's state matches what its
own documentation already claims.

## What this audit did not (and could not) do

- No physical Raspberry Pi hardware exists yet — every ARM64 and
  disaster-recovery claim in this project remains emulation/
  workstation-verified only, exactly as `docs/ARM64_REVIEW.md`,
  `docs/ARM64_TESTING.md`, and `docs/DISASTER_RECOVERY.md` already
  state plainly. This audit doesn't change that; Phase 13 unit 2's
  clean-environment end-to-end test is still workstation-based for the
  same reason.
- This audit did not attempt to fix any MEDIUM or LOW finding — the
  roadmap scopes this phase to "remediation of critical/high
  findings." The one HIGH finding within this audit's own power to
  fix (branch protection/secret scanning) was fixed, once the user
  made the underlying trade-off decision; the two that remain
  (off-host backups, the residual `.env` check) require either a
  concrete infrastructure choice this project hasn't made yet or
  access to the real `.env`, which project policy never grants —
  neither was fixable by this audit regardless of scope.

## Recommendation

This project's own prior review discipline has held up well under
re-checking — nothing inherited from Phases 2 through 12 turned out to
be stale, wrong, or silently regressed. The one genuinely new finding
this audit surfaced — branch protection and secret scanning silently
disabled since the repo went private — was real, and has now been
fixed: presented to the user as a trade-off (cost vs. visibility vs.
accepted risk) that belonged to the repository owner, not to this
audit, and resolved by the user's own choice to make the repository
public again, with branch protection restored to its original
documented settings and secret scanning re-enabled automatically.

Two HIGH items remain genuinely open: off-host backup storage
(`docs/BACKUP_DR_AUDIT.md` #1) and the residual manual check of the
real `.env` for a stale settings-module line
(`docs/PRODUCTION_CONFIG_REVIEW.md` #1). Both were already correctly
identified by earlier phases as blocked on something outside this
audit's reach — a concrete off-host destination this project hasn't
chosen, and direct access to the real `.env`, which project policy
never grants. Neither is new code this project could write its way out
of; both are concrete next steps for the user, not silent gaps.
