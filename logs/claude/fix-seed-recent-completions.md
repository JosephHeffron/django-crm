# Fix — the demo seed clocked no time before mid-morning

Not part of any unit. Found while investigating a test failure on a
branch whose only change since a green run was documentation.

## The bug

`seed_demo.time_entries()` carried this docstring:

> Clocked time for the crew over the last fortnight, on the jobs they
> actually worked — so Payroll and the time clock show a real week
> rather than an empty one.

The promise only held after about half past nine in the morning.

Clocked time came from `Job.objects.filter(status=COMPLETED,
completed_at__gte=now - 14 days)`. The seed's historical jobs
(`history()`) all finish well before that window, so the only
completions inside it are **today's** — created by `upcoming()` at 8am,
11am and 2pm with their status read from the clock. Before the first of
them has ended there is nothing completed in the window, so no time is
clocked at all: Payroll seeds empty and the time clock has no history.

Measured rather than reasoned about. A fresh seed at 09:14:

| | |
| --- | --- |
| completed jobs | 104 |
| most recent completion | 17 days ago |
| completed within the fortnight | 0 |
| time entries | 0 |

The 8am job's duration is at least 1.5 hours, so it finishes at 09:30 —
which is where the threshold comes from.

## Why it surfaced now

`test_populates_every_area_with_real_data` asserts clocked time exists.
It had been passing, and failed on a branch carrying only a
documentation merge. That looked like the branch and was the hour: the
run happened to land before 09:30 for the first time.

A calendar- or clock-dependent test is worse than a failing one,
because it teaches you to distrust the suite.

## The first fix was wrong, and review caught it

The first attempt kept the fortnight filter and added a fallback to the
most recently finished jobs whenever they were. It made the test pass
and delivered nothing.

**Payroll reports a period.** Hours dated to a job that finished two
months ago leave the current week exactly as empty. The test asserted
only that an entry existed *somewhere*, so it went green on a fix that
changed nothing a user would see.

Two further findings on that attempt, both real:

- `Job.objects.filter(status=COMPLETED)` is not scoped to demo data, so
  the fallback could clock hours against a **real** person's payroll —
  and `remove_demo_data()` deletes entries for demo users only, so such
  a row would survive a reset;
- on PostgreSQL a NULL `completed_at` sorts *ahead* of real dates under
  `order_by("-completed_at")`, so an undated job could be selected as
  the most recent work.

## The fix that works

`recent_completions()` seeds finished work on the last few weekdays, so
the fortnight filter has something real in it and the hours land inside
the week Payroll shows. The fallback is gone, which removes the other
two problems with it; the query is scoped to demo accounts and excludes
NULL completion dates anyway, since neither should depend on which rows
happen to be selected.

## The test that actually proves it

This is the part worth remembering. My mutation checks of the broken
behaviour **passed**, and I nearly accepted that.

They passed because they ran at ten in the morning, by which time
today's 8am job has finished and the bug cannot manifest. Every test
here runs at whatever hour CI happens to run, so none of them could
have failed.

So one test pins the clock to a Wednesday at 6am and asks the seed for
data again:

```python
dawn = timezone.make_aware(datetime(2026, 10, 7, 6, 0))  # a Wednesday
with mock.patch.object(timezone, "localtime", return_value=dawn):
    with mock.patch.object(timezone, "now", return_value=dawn):
        call_command("seed_demo", "--force", "--reset", verbosity=0)
```

With the clock pinned, both failure modes are caught: removing
`recent_completions()` fails it, and so does reinstating the fallback.
Neither was detectable before.

Four tests in total: clocked time exists and names its job; the hours
fall where Payroll looks and `crew.payroll` reports them; every entry
belongs to a demo account; and none comes from an undated job.

## What is deliberately not promised

On a Monday morning, before the first job of the day ends, Payroll's
current week is still empty — and that is correct: nobody has clocked
time that week yet. The bug was it being empty on every morning of
every day. Written into the docstring so the next person does not
"fix" it.

## Verification

$ `manage.py test` — 953 tests, OK.
$ `ruff` / `ruff format --check` / `makemigrations --check` — clean.
$ Seeding still never contacts OpenStreetMap: unchanged, and still
  asserted by patching both the lookup and the opener.

## Git

Branch: `fix/seed-recent-time-entries`. Commits: `02e4864` (the
first attempt) and `fb50ddd` (the fix that works). PR: #145, merged
as `8ea9c87`.

Its own pull request rather than folded into a unit: it was failing CI
for every branch in flight, and it belongs to none of them.
