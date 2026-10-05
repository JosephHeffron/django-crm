"""The time clock, payroll and crew performance (Phase 17.5 step 7).

Clocking in and out is the only place time is written. Clocking out of a
job also tops up that crew member's assignment hours, so a job's hours
and the clock can't tell two different stories.

Payroll pays for clocked time: hours in the period × the person's rate.
Someone with no rate set is still listed, with their hours and a note
that the rate is missing — silently paying them nothing would be worse
than saying so.
"""

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Avg, Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.users.models import get_profile

from .models import Job, JobAssignment, TimeEntry

ZERO_HOURS = Decimal("0.00")


def open_entry(user):
    """The clock this person has running, if any."""
    return TimeEntry.objects.filter(user=user, ended_at__isnull=True).select_related("job").first()


def clock_in(user, job=None, notes="", now=None):
    """Start the clock. Returns (entry, error) — an error rather than an
    exception, because clocking in twice is an ordinary mistake made on
    a phone, not an exceptional one."""
    if open_entry(user) is not None:
        return None, "You're already clocked in. Clock out first."
    entry = TimeEntry.objects.create(
        user=user, job=job, notes=notes, started_at=now or timezone.now()
    )
    return entry, None


def clock_out(user, now=None):
    """Stop the clock, and put the hours on the job if it named one."""
    entry = open_entry(user)
    if entry is None:
        return None, "You're not clocked in."
    now = now or timezone.now()
    if now <= entry.started_at:
        return None, "That would end the shift before it started."
    with transaction.atomic():
        entry.ended_at = now
        entry.save(update_fields=["ended_at"])
        if entry.job_id:
            _add_hours_to_assignment(entry)
    return entry, None


def _add_hours_to_assignment(entry):
    """Top up the crew member's hours on that job, so the job's own
    record and the clock agree. Someone clocked onto a job they aren't
    assigned to gets assigned — they did the work."""
    assignment, _ = JobAssignment.objects.get_or_create(job_id=entry.job_id, user=entry.user)
    assignment.hours_worked = (assignment.hours_worked or ZERO_HOURS) + entry.hours
    assignment.save(update_fields=["hours_worked"])


def entries_for(user, first, last):
    """This person's finished entries over a range of local dates."""
    from .calendar import day_bounds

    start, end = day_bounds(first, last)
    return (
        TimeEntry.objects.filter(
            user=user, started_at__gte=start, started_at__lt=end, ended_at__isnull=False
        )
        .select_related("job", "job__primary_service_type")
        .order_by("-started_at")
    )


def _hours_expression():
    """Hours as the database sees them, so a period's total is one
    query rather than a loop over entries."""
    return Sum(
        (F("ended_at") - F("started_at")),
        filter=Q(ended_at__isnull=False),
    )


def hours_in_period(entries):
    """Total hours across a queryset of entries, to two places."""
    total = entries.aggregate(span=_hours_expression())["span"]
    if total is None:
        return ZERO_HOURS
    return (Decimal(total.total_seconds()) / Decimal("3600")).quantize(Decimal("0.01"))


def payroll(crew, first, last):
    """What each person is owed for the period: their clocked hours and
    their rate. A missing rate is reported, never guessed."""
    from .calendar import day_bounds

    start, end = day_bounds(first, last)
    rows = []
    for person in crew:
        entries = TimeEntry.objects.filter(
            user=person, started_at__gte=start, started_at__lt=end, ended_at__isnull=False
        )
        hours = hours_in_period(entries)
        rate = get_profile(person).hourly_rate
        rows.append(
            {
                "person": person,
                "hours": hours,
                "rate": rate,
                "pay": (hours * rate).quantize(Decimal("0.01")) if rate is not None else None,
                "entries": entries.count(),
            }
        )
    return rows


def payroll_total(rows):
    return sum((row["pay"] for row in rows if row["pay"] is not None), Decimal("0.00"))


def performance(crew, first, last):
    """How each crew member's work looks over the period: jobs finished,
    hours clocked, and what customers rated those jobs."""
    from .calendar import day_bounds

    start, end = day_bounds(first, last)
    rows = []
    for person in crew:
        done = JobAssignment.objects.filter(
            user=person,
            job__status=Job.Status.COMPLETED,
            job__completed_at__gte=start,
            job__completed_at__lt=end,
        )
        jobs = Job.objects.filter(pk__in=done.values("job_id"))
        figures = jobs.aggregate(
            count=Count("pk"),
            rating=Avg("customer_rating"),
        )
        value = jobs.with_totals().aggregate(total=Coalesce(Sum("total_amount"), Decimal("0.00")))[
            "total"
        ]
        hours = hours_in_period(
            TimeEntry.objects.filter(
                user=person, started_at__gte=start, started_at__lt=end, ended_at__isnull=False
            )
        )
        rows.append(
            {
                "person": person,
                "jobs": figures["count"],
                "hours": hours,
                "rating": figures["rating"],
                "value": value,
                # What an hour of this person's time brought in. Only
                # meaningful once there are hours to divide by.
                "per_hour": (value / hours).quantize(Decimal("0.01")) if hours > 0 else None,
            }
        )
    return rows


def week_bounds(today):
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)
