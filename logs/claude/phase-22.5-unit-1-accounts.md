# PHASE 22.5 UNIT 1: ACCOUNTS, AND THE DEPLOYMENT TARGET

Started: 2026-10-28
Ended: 2026-11-02

PRs #186 (VPS audit), #188 (email + password reset), #187 (VPS plan),
#193 (owner-set passwords), #194 (email reset removed), #195 (Raspberry
Pi target dropped), #191/#192 (ruff 0.17.3), and this close-out.
Three ADRs: **0019** (email via Gmail — written, then superseded),
**0021** (passwords set by the owner), **0015** (x86-64 VPS replaces
the Pi).

Unit 1 of the roadmap entry is *"outbound email and password reset,
in-app team member creation (Owner-only), a rate limit on both login
pages, an Ubuntu x86-64 deployment guide, and alerting for a backup
that stops running."* Two of those five are done. The rate limit, the
deployment guide and the backup alerting are not started.

## The thing worth reading

**A feature was built, merged, and removed four days later.** Email
password reset shipped in #188 on 2026-10-28 — four routes, six
templates, a three-hour link lifetime, 12 tests, all green, all
reviewed. On 2026-11-02 the owner established that **DigitalOcean
blocks outbound SMTP on ports 25, 465 and 587 by default on Droplets**,
Gmail included. The feature could never have delivered a single email
on the host this project is moving to.

Nothing was wrong with the code. ADR 0019 rested on an assumption
nobody had tested — that the application could open an SMTP connection
from the production host — and the ADR itself never labelled it as an
assumption. `docs/VPS_AUDIT.md` labels every finding Verified,
Assumption or Open precisely because that distinction matters, and the
ADR written two days after the audit did not carry the discipline over.

What made it cheap to reverse: the settings were read from the
environment, so no code was provider-specific; the tests were
behavioural, so deleting the feature deleted its tests cleanly; and the
ADR existed, so the reversal had something to supersede rather than a
silent rewrite.

**The cost was not zero.** For four days `main` carried a sign-in page
telling a locked-out person to check their inbox for mail that could
not arrive, and `docs/SECURITY_REVIEW.md:168` — which states the auth
surface is login, logout and an authenticated password change —
was false and nobody noticed. That claim is now asserted by a test.

## What was built, in order

### #186 — the audit (2026-10-28)

`docs/VPS_AUDIT.md`, 365 lines, every finding labelled Verified,
Assumption or Open. Findings that drove everything after it:

| Finding | What it established |
|---|---|
| F-VPS-1 | Rootless Caddy cannot bind 80/443 on a default Ubuntu host; nothing in the repo sets the sysctl |
| F-VPS-6 | The deployment guide gave Raspberry Pi OS package commands for a host that will run Ubuntu |
| F-VPS-7 | **Nothing in the build is ARM-specific** — no `--platform`, no arch-conditional logic |
| F-VPS-8 | `--workers 3` was sized for a 4-core Pi; memory, not CPU, is the constraint to watch |
| F-CRM-2 | No in-app account creation and no reset: recovery meant the Django admin |
| F-CRM-3 | No `EMAIL_BACKEND` anywhere in `config/settings/` |

F-VPS-7 is the finding that made #195 safe to do in one pass, and
F-CRM-2 is the one that made #193 necessary.

Also established, and narrower than the audit first said: **the Owner
role grants no Django admin access.** `demo_owner` is `is_staff=False`,
`is_superuser=False`. So "the owner can use the admin" was never true —
account management was superuser-and-a-shell only.

### #188 — email and password reset (2026-10-28, since removed)

Gmail SMTP from the environment, console backend in development, four
routes, a `CRM_SITE_HOST` setting so the emailed link could not point
at the website's hostname, and `PASSWORD_RESET_TIMEOUT` at three hours.
CodeRabbit found that one: the setting was unset, so Django used its
**three-day** default while the email, the sent page and the user guide
all promised "a few hours".

### #193 — the owner sets passwords (2026-11-02)

The replacement, built before the removal so `main` never had a gap.
`people:member_create` for adding somebody (username, name, role and
first password in one step — there is no invite email to send), and a
set-password section on each person's page using Django's
`SetPasswordForm`, so `AUTH_PASSWORD_VALIDATORS` applies exactly as it
does to a self-service change. Saving a new password invalidates that
person's sessions, which is the point when the reason for the reset is
a shared or stolen password.

Already present and not rebuilt: role changes and the "Can sign in"
toggle, both shipped in Phase 17.5 (`MemberAccessForm`). The audit had
implied all of account management was missing; only creation and
passwords were.

### #194 — the email path removed (2026-11-02)

Four routes, six templates, `apps/users/password_reset.py`, its 12
tests, the `EMAIL_*` block in `production.py`, `CRM_SITE_HOST`,
`PASSWORD_RESET_TIMEOUT` and the `.env.example` section. The
development console backend stayed, re-commented as a guard rather
than a feature: nothing on a workstation can reach a real person.

### #195 — the Raspberry Pi target dropped (2026-11-02)

`docs/ARM64_REVIEW.md`, `docs/ARM64_TESTING.md`,
`scripts/test-arm64.sh`, the `make arm64` target and roadmap Phase 25,
with `CLAUDE.md`, `README.md`, `docs/ARCHITECTURE.md` and the
deployment guides rewritten to the real host. The owner confirmed the
intent explicitly, since this edits the development contract itself.

Dated reports (`QA_REPORT`, `PRODUCTION_READINESS`, `BACKUP_DR_AUDIT`,
`DISASTER_RECOVERY`, `CLEAN_ENVIRONMENT_TEST`, `PROJECT_STATE`,
`VPS_AUDIT`) cite the deleted files; each got a dated note rather than
an edit to its findings. `logs/claude/` and `CHANGELOG.md` were left
alone entirely — rewriting a phase log would falsify the record.

**`--workers 3` kept its value and lost its justification.** Sized for
a 4-core Pi, the droplet has 2 vCPU, and F-VPS-8 records the figure as
untested with memory the real constraint. Changing it without a
measurement is the speculative optimisation `CLAUDE.md` forbids.

## Errors made, and what caught them

| What | Caught by |
|---|---|
| `extra_email_context` passed as a form kwarg → `TypeError` | the host test, before review |
| `PASSWORD_RESET_TIMEOUT` unset: docs promised hours, Django gave three days | CodeRabbit (#188) |
| New form template had no header save button | `test_save_at_the_top`, a sweep of the template directories — the full suite, not a targeted run |
| `NewMemberForm.__init__` set labels on `new_password1`; `UserCreationForm` uses `password1` | reading Django's source before running |
| Account committed before its role, so a failure left the username taken | CodeRabbit (#193) |
| `clean_username` override **shadowed Django's case-insensitive check** — `boss` and `Boss` could both exist | CodeRabbit (#193, re-review) |
| ADR 0021 and two UI strings described unit B's removal as already done | CodeRabbit (#193) |
| **A sole Owner who forgets their password has no in-app recovery** | CodeRabbit (#194) |
| Guard tests covered only the `users` namespace, and one reversed a route with no arguments so it could not fail for its stated reason | CodeRabbit (#194) |
| `Containerfile` attributed F-VPS-8 to a 4 GB host; the finding assumed 2 GB | CodeRabbit (#195) |
| ADR 0004's note said "the decision stands" while its Consequences list still required `linux/arm64` images | CodeRabbit (#195, re-review) |

Two of those were introduced **while fixing an earlier finding** — the
shadowed username check, and the premature claims in ADR 0021. Both
came from overriding framework behaviour rather than extending it.

CodeRabbit raised 16 findings across the five code PRs. Fourteen were
fixed; two were about its own stored knowledge of the repository being
stale rather than the repository being wrong, and were answered on the
thread. Sourcery was over its weekly budget for the whole stretch and
reviewed nothing.

## The owner-lockout gap

The one real regression against the email flow, and it was missed when
ADR 0021 was written: that ADR enumerated what an absent owner costs a
locked-out *employee* and never asked what happens when the **owner**
is locked out. The set-password page refuses to act on whoever is
signed in, and the self-service change page asks for the password they
have forgotten.

Documented in `docs/ADMIN_GUIDE.md`, in order of preference:

1. **Keep two Owner accounts.** Either can reset the other from the
   Team page, so recovery stays in the app. A test now proves it
   rather than leaving it inferred from the code.
2. `manage.py changepassword` inside the container, with shell access.

Losing the password *and* server access means losing administrative
control of the CRM. Stated plainly in the guide and the ADR rather than
left to be discovered.

## Verification

Full suite run without a pipe, verdict read from the exit code, after
every unit:

| Point | Result |
|---|---|
| after #188 | `Ran 1364 tests` — OK |
| after #188's review fix | `Ran 1366 tests` — OK |
| `main` after #190 (another session's DST fix) | `Ran 1371 tests` — OK |
| #193 | `Ran 1387` → `1390` → `Ran 1391 tests` — OK |
| #194 (12 email tests out, 3 guards in) | `Ran 1382 tests` — OK |
| #194's review fixes | `Ran 1383 tests` — OK |
| #195 (docs only) | `Ran 1383 tests` — OK |

Mutation checks, each asserting its anchor matched exactly once and
reading the verdict from the exit code: the reset timeout in both
directions; the `site_name` default; the self-password guard; the
create-plus-role transaction; the shadowed username check; and a reset
route mounted in the **root** URLconf, which the first version of that
guard missed entirely.

`ruff check`, `ruff format --check`, `manage.py check` and
`makemigrations --check` clean throughout. A repo-wide sweep for
dangling `docs/*.md` and `scripts/*.sh` references leaves only
references to the three deleted ARM files, each inside a document that
explains their removal.

## Where this leaves unit 1

| Item | State |
|---|---|
| Outbound email and password reset | **Reversed.** No email; the owner sets passwords (ADR 0021) |
| In-app team member creation, Owner-only | **Done** (#193) |
| Rate limit on both login pages | **Not started.** Needs the `DatabaseCache` from the plan's D4 and ADR 0020, and must land before `crm.` is exposed |
| Ubuntu x86-64 deployment guide | **Not started.** The audit's F-VPS-1 to F-VPS-5 are the content: the port sysctl, `linger`, subuid/subgid, the `podman-compose` path |
| Backup-failure alerting | **Not started** |

Next: the login rate limit, because unit 3 puts the CRM on the public
internet and there is no MFA until Phase 23.

## Owner's own items

- **Create a second Owner account** on the real deployment. It is what
  turns owner lockout from a shell-access problem into two clicks.
- **`EMAIL_HOST`, `EMAIL_HOST_USER` and `EMAIL_HOST_PASSWORD` can come
  out of `.env`**, and the Google app password can be revoked. Nothing
  reads them.
- The possibly-stale `DJANGO_SETTINGS_MODULE` line in the real `.env`
  (`docs/PRODUCTION_READINESS.md`'s remaining HIGH finding) is still
  the owner's to check — policy never grants access to that file.
