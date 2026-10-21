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
    # status and move controls only where there is a job to move.
    job_id: int | None = None

    @property
    def starts_at(self):
        """The start as a datetime-local input wants it, so the move
        box opens showing when the job currently runs."""
        return timezone.localtime(self.start).strftime("%Y-%m-%dT%H:%M")


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


# Booking from the day schedule (Phase 21): the grid of times you can
# click. Half-hour steps, because that is the shortest job anyone here
# books, and 6am-8pm because that is the working day for exterior work.
SLOT_MINUTES = 30
DAY_OPENS_AT = time(6)
DAY_CLOSES_AT = time(20)


def _local_naive(moment):
    """An aware datetime as naive local time.

    The grid is built in naive local time throughout, for two
    reasons, neither of which is DST arithmetic: the value each slot
    hands to the job form is a naive local string, and comparing
    everything on the wall clock means the busy flags match the
    labels beside them rather than the instants behind them.

    An earlier version of this comment claimed an aware grid would
    drift an hour across a DST change. **It would not** — `zoneinfo`
    datetimes add timedeltas to their naive fields, so an aware grid
    steps by wall clock too, and mutating this function to return
    `localtime(moment)` passes every test in `DaySlotTests`. Left
    recorded because a comment giving a wrong mechanism is worse than
    no comment.

    One real edge is accepted rather than solved: on the spring-
    forward morning, 2:00-3:00am does not exist locally, so a slot
    labelled 2:30 AM would open the form at another time. The grid
    only reaches down there if a booking already sits at 2am on that
    one night of the year.
    """
    return timezone.localtime(moment).replace(tzinfo=None)


def _floor_to_slot(moment):
    return moment.replace(
        minute=(moment.minute // SLOT_MINUTES) * SLOT_MINUTES, second=0, microsecond=0
    )


def _ceil_to_slot(moment):
    floored = _floor_to_slot(moment)
    return floored if floored == moment else floored + timedelta(minutes=SLOT_MINUTES)


def day_slots(day, events):
    """Half-hour slots across `day`, each marked if a booking covers it.

    6am-8pm is a **floor**, not the window: it widens to take in the
    earliest and latest booking of the day, clamped to the day itself.
    A fixed window would show 06:00 as free while a 05:30 job was
    already out — the agenda above lists that job, so a grid claiming
    the morning was empty would contradict the same page.

    `busy` is a flag, not a size. Sizing a slot by duration needs
    inline styles, which the CSP forbids (see the module docstring),
    and a busy slot stays clickable regardless: two crews can be out
    at once, and the job form would accept the booking anyway.
    """
    step = timedelta(minutes=SLOT_MINUTES)
    midnight = datetime.combine(day, time.min)
    tomorrow = midnight + timedelta(days=1)

    opens = datetime.combine(day, DAY_OPENS_AT)
    closes = datetime.combine(day, DAY_CLOSES_AT)
    spans = []
    for event in events:
        start = _local_naive(event.start)
        # A site visit has no end (Event.end is None for a quote), so
        # it holds the half hour it starts in and no more. Left as
        # None it would read as free and the grid would offer a time
        # the sales rep is already driving to.
        #
        # The end is the end of the slot the visit starts in, not
        # thirty minutes after the visit: a visit at 14:10 plus half
        # an hour runs to 14:40 and marks the 14:30 slot as well,
        # which contradicts the one-slot rule above. Caught by
        # Sourcery on PR #166 — the first test used 14:00 exactly, so
        # it agreed with the claim without checking it.
        end = _local_naive(event.end) if event.end else _floor_to_slot(start) + step
        spans.append((start, end))
        opens = min(opens, start)
        closes = max(closes, end)

    opens = max(midnight, _floor_to_slot(opens))
    closes = min(tomorrow, _ceil_to_slot(closes))

    slots = []
    at = opens
    while at < closes:
        slot_end = at + step
        slots.append(
            {
                "value": at.strftime("%Y-%m-%dT%H:%M"),
                "label": at.strftime("%-I:%M %p"),
                # Half-open on both sides. A job ending at exactly
                # 11:00 must not mark the 11:00 slot: with `<=` every
                # back-to-back booking paints an extra half hour, and
                # a rendered page looks plausible either way, which is
                # why this has a test of its own.
                "busy": any(start < slot_end and end > at for start, end in spans),
            }
        )
        at = slot_end
    return slots


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
