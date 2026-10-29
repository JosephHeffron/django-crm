"""Moving a job to a different time (Phase 18 unit 4).

One rule, in one place, because there are two ways in: the "move"
controls on the day schedule, which need no JavaScript, and dragging a
chip on the week or month view, which is an enhancement on top of them.

**The duration is kept, not recalculated.** A job booked for three
hours is still three hours when it moves to Thursday. Asking for a new
start and a new end would be two fields to disagree, and the database
refuses an end before a start (`job_ends_after_it_starts`), so a move
that only knows the start cannot produce an invalid row.

**Status is not touched.** Moving a finished job back into next week
would be odd, but it is not this function's business to decide, and
`completed_at` is what every count of finished work reads — see
`apps/jobs/status.py`. A move that quietly re-opened a job would make
it vanish from the figures.
"""

from datetime import timedelta

from django.utils import timezone

# How far a nudge moves a job, for the buttons on the day schedule.
NUDGES = (
    ("-1d", "Back a day", timedelta(days=-1)),
    ("+1d", "On a day", timedelta(days=1)),
    ("+7d", "On a week", timedelta(days=7)),
)
NUDGE_BY_KEY = {key: delta for key, _, delta in NUDGES}


def _to_minute(value):
    return value.replace(second=0, microsecond=0)


def move_job(job, start):
    """Move `job` to start at `start`. Returns `(job, error)`.

    The same `(object, error)` shape the time clock and the status
    change use, so the views read alike.
    """
    if start is None:
        return None, "That isn't a date and time."
    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    length = job.scheduled_end - job.scheduled_start
    # Compared to the minute, which is the precision the control
    # offers. A stored start carries seconds, so an exact comparison
    # never matched and submitting the box unchanged — or dragging a
    # chip back where it was — wrote a pointless row to the change log
    # and moved the job by a few hundred milliseconds.
    if _to_minute(start) == _to_minute(job.scheduled_start):
        return job, None
    job.scheduled_start = start
    job.scheduled_end = start + length
    # `updated_at` is auto_now, and an auto_now field is only written
    # when it is named in update_fields.
    job.save(update_fields=["scheduled_start", "scheduled_end", "updated_at"])
    return job, None


def nudge_job(job, key):
    """Move a job by one of the named steps. Returns `(job, error)`."""
    delta = NUDGE_BY_KEY.get(key)
    if delta is None:
        return None, "That isn't a move this can make."
    # Added in local time, not UTC. "On a day" means the same time on
    # the next day, and across a clock change those are an hour apart:
    # in UTC, a 12:35 job on the Saturday before the clocks go back
    # landed at 11:35 on the Sunday. Python adds a timedelta to a
    # zone-aware datetime in wall-clock terms, so this keeps 12:35.
    return move_job(job, timezone.localtime(job.scheduled_start) + delta)


def describe(job):
    """When a job runs, for a message after it has moved."""
    start = timezone.localtime(job.scheduled_start)
    return f"{start:%a %-d %b} at {start:%-I:%M %p}".replace(" 0", " ")
