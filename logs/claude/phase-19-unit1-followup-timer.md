# PHASE 19 UNIT 1: THE DAILY FOLLOW-UP TIMER

Started: 2026-10-11
Ended: 2026-10-11

## Objective

The roadmap asks for "daily follow-up generation via a systemd timer
(same pattern as the backup timer)". `generate_followups` has existed
since Phase 17, idempotent and tested, and **nothing ever ran it**.

## The verification pass that came first

Asked to establish what Phase 19 had actually delivered before building
the timer. The answer was not what the roadmap entry suggested:

| Roadmap item | Reality |
|---|---|
| Daily follow-up generation | Built, 14 tests, genuinely idempotent. Only the timer missing |
| Per-service intervals | Built — but **unasserted** |
| Completion logs a contact touch | Built, 4 tests |
| Business-plan checklists | **Display only** |
| Notes | **Display only** |

**Per-service intervals is the one worth recording.** The code reads
`service.followup_interval_months`, so it works. But every existing
test used one service — gutter cleaning, six months — and replacing
that lookup with a hard-coded `6` **passes all 14 of them**. Verified
by mutation, not supposed.

The seeded catalogue spans the range deliberately (weed removal 3
months, gutters 6, pressure washing 12, tree removal never), so
`PerServiceIntervalTests` uses one customer per service at the same job
age: the interval becomes the only thing that can separate them. Three
of the six new tests fail under the hard-coding mutation.

## Files created / changed

- `scripts/followups.sh` — runs `manage.py generate_followups` inside
  the web container, because the host deliberately has no application
  environment. Follows `backup.sh`'s conventions: `SERVICE_PREFIX`
  override, `set -e`, and an explicit `podman container exists` check
  rather than letting `podman exec` produce a message about a missing
  container when the real cause is a wrong setting. Forwards `--date`.
- `systemd/crm-followups.service`, `systemd/crm-followups.timer` —
  07:00 daily, `Persistent=true`, on the `crm-backup.timer` pattern.
- `apps/crm/tests/test_followup_schedule.py` (16) — the script, and
  the units parsed by `systemd-analyze verify` rather than
  pattern-matched.
- `apps/crm/tests/test_followups.py` — `PerServiceIntervalTests` (6).
- `docs/ADMIN_GUIDE.md` — install step, the health check, and why a
  missed day is not a lost day.

## Two design decisions

**07:00, not the small hours.** The backup runs at 03:00 because
`pg_dump` competes for I/O. Generation does not — and it creates a
*notification*, so 03:00 would buzz somebody's phone about a gutter
clean in the middle of the night. A follow-up raised at 07:00 is
equally due and arrives as someone starts work.

**A skipped day is not a lost day; a broken timer is.** Whether a
customer is due is computed from "has the interval elapsed since their
last job or contact touch", not from "did we run yesterday". A customer
due yesterday is still due today, so a missed run raises the follow-up
a day late rather than never. That is the important difference from a
missed backup, which is a permanent hole.

What is *not* self-correcting is the timer being broken rather than
skipped — a renamed container, a stack that never came up, units never
enabled. Then follow-ups stop and the only symptom is their absence,
which is easy not to notice for weeks. So the script exits non-zero on
every failure path, and `ADMIN_GUIDE.md` gained
`systemctl --user list-timers 'crm-*'` as the health check with what
each symptom means.

One line in those docs matters more than it looks: **`Created 0
follow-up task(s)` is the normal healthy output most days.** Without
saying so, the first person to read the journal concludes it is broken.

## Verification

```
python manage.py test                       # 1,081 pass, 22 new
ruff check . && ruff format --check .        # clean
python manage.py makemigrations --check      # No changes detected
sh -n scripts/*.sh                           # all 7 clean
systemd-analyze verify --user <units>        # clean with %h resolved
SERVICE_PREFIX=definitely-not-a-real-stack ./scripts/followups.sh
                                             # exit 1, names SERVICE_PREFIX
```

Mutation-checked: `OnCalendar=every tuesday at teatime` is caught
(`systemd-analyze` genuinely parses it); a missing-stack check that
warns instead of failing is caught; `followup_interval_months`
hard-coded to 6 is caught by 3 of the new interval tests and **by none
of the 14 that existed before**.

## Not covered

The timer firing. That needs the production stack and a clock, so it
stays the manual `list-timers` check in `ADMIN_GUIDE.md`.

## Also fixed

`ADMIN_GUIDE.md`'s `locate_properties` example named container
`crm-web`, where compose creates `django-crm_web_1` — which
`deploy.sh` itself checks for. A copy-pasted command would have failed.

## Commit

PR #154.
