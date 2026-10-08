"""Calendar ranges and events (Phase 17 unit 3).

Jobs come through jobs_for() — a cleaner's calendar only ever holds
their own assignments — and sales roles also see quote site visits.
Weeks start on Monday. Events are placed by the local date they start
on; the page lists them in time order rather than sizing them by
duration (sizing would need inline styles, which the CSP forbids).
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from apps.crm.followups import add_months
from apps.users.roles import SALES_ROLES, user_role

from .access import jobs_for, quotes_for
from .models import Job, JobAssignment, Quote

VIEWS = ("day", "week", "month")
DEFAULT_VIEW = "week"


@dataclass(frozen=True)
class CalendarRange:
    view: str
    anchor: date
    first: date  # inclusive
    last: date  # inclusive
    previous: date
    next: date
    title: str


def day_bounds(first, last):
    """Aware datetimes covering local dates first..last (inclusive)."""
    start = timezone.make_aware(datetime.combine(first, time.min))
    end = timezone.make_aware(datetime.combine(last + timedelta(days=1), time.min))
    return start, end


def calendar_range(view, anchor):
    if view == "day":
        return CalendarRange(
            view,
            anchor,
            anchor,
            anchor,
            anchor - timedelta(days=1),
            anchor + timedelta(days=1),
            f"{anchor:%A, %B} {anchor.day}, {anchor.year}",
        )
    if view == "week":
        first = anchor - timedelta(days=anchor.weekday())
        last = first + timedelta(days=6)
        start_label = f"{first:%b} {first.day}"
        end_label = f"{last:%b} {last.day}" if last.month != first.month else str(last.day)
        return CalendarRange(
            view,
            anchor,
            first,
            last,
            first - timedelta(days=7),
            first + timedelta(days=7),
            f"{start_label} – {end_label}, {last.year}",
        )
    month_first = anchor.replace(day=1)
    month_last = add_months(month_first, 1) - timedelta(days=1)
    return CalendarRange(
        "month",
        anchor,
        month_first - timedelta(days=month_first.weekday()),
        month_last + timedelta(days=6 - month_last.weekday()),
        add_months(month_first, -1),
        add_months(month_first, 1),
        f"{month_first:%B %Y}",
    )


@dataclass
class Event:
    kind: str  # "job" or "visit"
    start: datetime
    end: datetime | None
    title: str
    subtitle: str
    url: str
    tone_class: str
    status: str = ""
    status_label: str = ""
    crew: list = field(default_factory=list)
    # Set for jobs, left None for site visits — the day view offers
    # status buttons only where there is a job to move.
    job_id: int | None = None


def _job_events(user, start, end, crew_id):
    jobs = (
        jobs_for(user)
        .filter(scheduled_start__gte=start, scheduled_start__lt=end)
        .exclude(status=Job.Status.CANCELLED)
        .select_related("contact", "primary_service_type")
        .prefetch_related("crew")
        .order_by("scheduled_start", "pk")
    )
    if crew_id is not None:
        jobs = jobs.filter(pk__in=JobAssignment.objects.filter(user_id=crew_id).values("job_id"))
    return [
        Event(
            kind="job",
            start=job.scheduled_start,
            end=job.scheduled_end,
            title=job.primary_service_type.name,
            subtitle=str(job.contact),
            url=job.get_absolute_url(),
            tone_class=job.primary_service_type.tone_class,
            status=job.status,
            status_label=job.get_status_display(),
            job_id=job.pk,
            crew=[member.get_full_name() or member.get_username() for member in job.crew.all()],
        )
        for job in jobs
    ]


def _visit_events(user, start, end):
    quotes = (
        quotes_for(user)
        .filter(
            site_visit_at__gte=start,
            site_visit_at__lt=end,
            status__in=Quote.OPEN_STATUSES,
        )
        .select_related("contact")
        .order_by("site_visit_at", "pk")
    )
    return [
        Event(
            kind="visit",
            start=quote.site_visit_at,
            end=None,
            title="Site visit",
            subtitle=str(quote.contact),
            url=quote.get_absolute_url(),
            tone_class="event-visit",
        )
        for quote in quotes
    ]


# How many dots a day shows before it switches to "+n".
MAX_DOTS = 6


def day_indicators(events):
    """A day's shape at a glance: one colored dot per booking, and how
    many are jobs, site visits, and already finished. The month view has
    room for three events at most, so without this a busy day and a very
    busy day look the same."""
    return {
        "dots": [
            {
                "tone_class": event.tone_class,
                "label": f"{timezone.localtime(event.start):%-I:%M %p} {event.title}",
            }
            for event in events[:MAX_DOTS]
        ],
        "extra": max(0, len(events) - MAX_DOTS),
        "jobs": sum(1 for event in events if event.kind == "job"),
        "visits": sum(1 for event in events if event.kind == "visit"),
        "done": sum(1 for event in events if event.status == Job.Status.COMPLETED),
    }


def calendar_days(user, cal, crew_id=None, today=None):
    """One dict per date in the range, each with its events in time
    order. ``crew_id`` narrows jobs to one crew member (and drops site
    visits, which are sales appointments, not crew work)."""
    today = today or timezone.localdate()
    start, end = day_bounds(cal.first, cal.last)
    events = _job_events(user, start, end, crew_id)
    if crew_id is None and user_role(user) in SALES_ROLES:
        events += _visit_events(user, start, end)
    events.sort(key=lambda event: event.start)

    by_date = {}
    for event in events:
        by_date.setdefault(timezone.localdate(event.start), []).append(event)

    days = []
    current = cal.first
    while current <= cal.last:
        days.append(
            {
                "date": current,
                "events": by_date.get(current, []),
                "is_today": current == today,
                "in_month": cal.view != "month" or current.month == cal.anchor.month,
                "indicators": day_indicators(by_date.get(current, [])),
            }
        )
        current += timedelta(days=1)
    return days
