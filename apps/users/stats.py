"""Profile stats over a window of days (Phase 17 unit 3d). Every figure is
a database aggregate.

Crew (anyone with job assignments):
- jobs completed — their assignments on jobs completed in the window;
- hours logged, and hours per week over the window;
- average job value — the mean total of those jobs;
- average customer rating on those jobs.

Sales (Owner and Sales Rep):
- quotes sent — quotes they prepared, sent in the window;
- sold, and value won — count and Σ totals of their quotes **accepted**
  in the window. One pair, from one queryset: "sold 4 jobs worth
  $2,100" has to be about the same four jobs;
- close rate — accepted ÷ (accepted + declined + expired) among quotes
  they prepared that were **created** in the window and have been
  decided. Deliberately a different basis from `sold`: a close rate
  dated by acceptance would flatter itself, counting wins in the window
  against a denominator that excludes the quotes still pending from it;
- follow-ups completed — follow-up tasks they completed in the window.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.utils import timezone

from apps.crm.models import Task
from apps.jobs.models import Job, JobAssignment, Quote

WINDOWS = (30, 90, 365)
DEFAULT_WINDOW = 90

# The stats sheet's periods, newest first — the owner's own list: "the
# past week/1mo/3mo/6mo/12mo". Shown together rather than one at a time
# behind tabs, because the useful question is not "how many this month"
# but "is this month better than the last three".
PERIODS = (
    (7, "This week"),
    (30, "1 month"),
    (90, "3 months"),
    (180, "6 months"),
    (365, "12 months"),
)


def crew_stats(user, days, now=None):
    """`now` is captured by the caller so a sheet's five rows share one
    clock, and bounds every period **above** as well as below.

    Without the upper bound a completion stamped in the future — a bad
    import, an admin edit, a clock skew — lands in every period whose
    start it follows, inflating all of them at once. `__gte` alone
    makes "this week" include work dated next year.
    """
    now = now or timezone.now()
    since = now - timedelta(days=days)
    done = JobAssignment.objects.filter(
        user=user,
        job__status=Job.Status.COMPLETED,
        job__completed_at__gte=since,
        job__completed_at__lt=now,
    )
    totals = done.aggregate(count=Count("pk"), hours=Sum("hours_worked"))
    jobs = Job.objects.filter(pk__in=done.values("job_id"))
    money = jobs.with_totals().aggregate(avg=Avg("total_amount"), total=Sum("total_amount"))
    value = money["avg"]
    hours = totals["hours"] or Decimal("0")
    return {
        "jobs_completed": totals["count"],
        "hours": hours,
        "hours_per_week": (hours / Decimal(days) * 7).quantize(Decimal("0.1")),
        # What the work they did was worth, not just the average job —
        # "cleaned x jobs costing over $y".
        "value": (money["total"] or Decimal("0")).quantize(Decimal("0.01")),
        "average_job_value": value.quantize(Decimal("0.01")) if value is not None else None,
        "average_rating": jobs.aggregate(avg=Avg("customer_rating"))["avg"],
        # Deliberately unbounded above: "upcoming" means everything
        # still to come, not everything in the window.
        "upcoming": JobAssignment.objects.filter(
            user=user, job__status=Job.Status.SCHEDULED, job__scheduled_start__gte=now
        ).count(),
    }


def sales_stats(user, days, now=None):
    """See `crew_stats` on `now`: one clock per sheet, and every period
    bounded above as well as below."""
    now = now or timezone.now()
    since = now - timedelta(days=days)
    mine = Quote.objects.filter(prepared_by=user)
    decided = mine.filter(
        created_at__gte=since, created_at__lt=now, status__in=Quote.DECIDED_STATUSES
    ).aggregate(won=Count("pk", filter=Q(status=Quote.Status.ACCEPTED)), total=Count("pk"))
    # What they sold *in* the period, counted and valued from one
    # queryset so the two cannot disagree.
    #
    # They used to. `won` below is a cohort figure — of the quotes
    # raised in this window, how many closed — while `value_won` has
    # always been "accepted in this window". Those are different sets,
    # and a quote raised in spring and signed last Tuesday put the page
    # in the position of reading "sold 0 jobs, worth $500.00" for the
    # last seven days. Measured, on the existing page, before this was
    # split out.
    #
    # Both figures are kept, because both are real questions. `sold`
    # and `value_won` answer "how did this month go"; `won`, `decided`
    # and `close_rate` answer "of what I quoted then, how much came
    # in", which is the honest way to measure a close rate and the
    # reason it is dated by creation.
    accepted = mine.filter(
        status=Quote.Status.ACCEPTED, accepted_at__gte=since, accepted_at__lt=now
    )
    sold = accepted.with_totals().aggregate(count=Count("pk"), total=Sum("total_amount"))
    return {
        "quotes_sent": mine.filter(sent_at__gte=since, sent_at__lt=now).count(),
        "sold": sold["count"],
        "decided": decided["total"],
        "won": decided["won"],
        "close_rate": round(decided["won"] / decided["total"] * 100) if decided["total"] else None,
        "value_won": sold["total"] or Decimal("0"),
        "follow_ups_completed": Task.objects.filter(
            kind=Task.Kind.FOLLOW_UP,
            status=Task.Status.COMPLETED,
            completed_by=user,
            completed_at__gte=since,
            completed_at__lt=now,
        ).count(),
        "open_quotes": mine.filter(status__in=Quote.OPEN_STATUSES).count(),
    }


def crew_sheet(user):
    """What this person did, over each of `PERIODS`.

    One row per period, so the trend is readable at a glance instead of
    requiring five page loads. Every row is `crew_stats` for that
    window, which keeps one definition of "jobs completed" rather than
    a second implementation that could drift from the cards above it —
    `test_the_sheet_agrees_with_the_single_window_figures` holds them
    together.

    Five calls means five times the queries, measured rather than
    guessed at. The first version of this note gave 45 queries for "an
    Owner's profile", which was the **sheets alone** — review caught
    that it understated the request, so these are whole-request
    figures against the demo data (137 jobs, 203 assignments):

        a Cleaner's profile          33 queries    47 ms
        a Sales Rep's profile        40 queries    32 ms
        both sheets at once          64 queries    75 ms

    The last row had to be arranged: no demo user has both, so an
    assignment was given to the Owner, measured, and removed. Call it
    200-350 ms on a Pi for the worst case.

    One page, not a list, and every query is an aggregate on an indexed
    column — `Job.completed_at` included, since `jobs/0005` added the
    index it had been missing. That field is filtered in fifteen places
    outside tests and had none.

    Conditional aggregation would collapse it to one query per metric,
    at the cost of a second definition of each figure. `CLAUDE.md` says
    not to optimise a speculative problem, and 75 ms is not a problem.
    Worth revisiting if a profile ever feels slow, and worth
    re-measuring first.

    One known limitation, raised in review and accepted rather than
    fixed: a row is several queries, so another request completing a
    job or accepting a quote mid-row can leave two figures describing
    different committed states — "0 jobs worth $x" for an instant.
    PostgreSQL's default READ COMMITTED gives each query its own
    snapshot, and the only real fixes are one aggregate per row, which
    would mean a second definition of every figure and lose the
    agreement with the cards, or a higher isolation level for a profile
    page. For a single-operator business reading its own profile the
    window is milliseconds and the cost of closing it is a worse
    design. Noted so the next person does not rediscover it as a bug.
    """
    now = timezone.now()
    return [
        {"days": days, "label": label, **crew_stats(user, days, now=now)} for days, label in PERIODS
    ]


def sales_sheet(user):
    """What this person sold, over each of `PERIODS`. See `crew_sheet`."""
    now = timezone.now()
    return [
        {"days": days, "label": label, **sales_stats(user, days, now=now)}
        for days, label in PERIODS
    ]
