# PHASE 18 UNIT 4: MOVING A JOB TO ANOTHER TIME

Started: 2026-10-10
Ended: 2026-10-10

(Written during the Phase 18 close-out, from PR #150 and the commit.
Unit 4 merged without its own log at the time.)

## Objective

Reschedule a job, by form or by dragging.

## The non-drag route is the baseline, not a fallback

The move controls on the day schedule are ordinary form fields: a date
and time box that opens showing when the job currently runs, plus *back
a day*, *on a day* and *on a week*. They work on a keyboard, with a
screen reader, and with no JavaScript at all.

Dragging a chip on the week or month view is built on top, posting to
the same endpoint. Only the date moves — dragging across a week grid
says nothing about the hour, and guessing would move an 8am job to the
middle of the afternoon.

Chips are only draggable for someone who may reschedule, so nobody
drags one and is then refused.

## Files created / changed

- `apps/jobs/scheduling.py` — `move_job()`, `nudge_job()`, `NUDGES`,
  `describe()`. The single front door for a move.
- The day, week and month calendar views, `static/js/reschedule.js`,
  and `apps/jobs/tests/test_reschedule.py`.

## Two invariants, checked rather than trusted

**The job keeps its length.** A three-hour job is still three hours on
Thursday. Only the start is asked for, which is also why a move cannot
produce an end before a start and trip `job_ends_after_it_starts`.

**A move leaves the status and the completion date alone.** That date
is what the dashboard, the monthly goal, Financials and a crew
member's week all read, so a move that quietly re-opened a job would
make it vanish from the figures with nothing on screen to say so.

## A real bug my own tests caught

The date box offers minute precision while a stored start carries
seconds, so an exact comparison never matched: submitting the box
unchanged always wrote, and so did dragging a chip back where it
started. Both are recognised as no-ops now, rather than writing a
pointless row to the change log and shifting the job by a few hundred
milliseconds.

## Who may

Crews cannot reschedule, though they can mark a job finished. Saying a
job is done reports what happened; moving a customer's appointment is a
different kind of decision, and it is the same rule the calendar
already uses to decide who sees "New job".

## Two details about the enhancement

- it submits a **server-rendered form** rather than fetching, because
  `CSRF_COOKIE_HTTPONLY` means no script in this app can read the
  token;
- the move URL comes from **Django's routing**, not assembled in
  JavaScript, which would have worked right up until the route changed
  and then failed silently.

## Verification

| check | result |
| --- | --- |
| Full suite on the merged tree | 1084 pass, 30 new |
| Mutation: recalculate the length instead of keeping it | fails 1 test |
| Mutation: let a move re-open a finished job | fails 1 test |
| Mutation: let crews reschedule | fails 1 test |

No migrations.

## Commit

PR #150.
