"""Profile stats over a window of days (Phase 17 unit 3d). Every figure is
a database aggregate.

Crew (anyone with job assignments):
- jobs completed — their assignments on jobs completed in the window;
- hours logged, and hours per week over the window;
- average job value — the mean total of those jobs;
- average customer rating on those jobs.

Sales (Owner and Sales Rep):
- quotes sent — quotes they prepared, sent in the window;
- close rate — accepted ÷ (accepted + declined + expired) among quotes
  they prepared that were created in the window and have been decided;
- value won — Σ totals of their quotes accepted in the window;
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


def crew_stats(user, days):
    since = timezone.now() - timedelta(days=days)
    done = JobAssignment.objects.filter(
        user=user, job__status=Job.Status.COMPLETED, job__completed_at__gte=since
    )
    totals = done.aggregate(count=Count("pk"), hours=Sum("hours_worked"))
    jobs = Job.objects.filter(pk__in=done.values("job_id"))
    value = jobs.with_totals().aggregate(avg=Avg("total_amount"))["avg"]
    hours = totals["hours"] or Decimal("0")
    return {
        "jobs_completed": totals["count"],
        "hours": hours,
        "hours_per_week": (hours / Decimal(days) * 7).quantize(Decimal("0.1")),
        "average_job_value": value.quantize(Decimal("0.01")) if value is not None else None,
        "average_rating": jobs.aggregate(avg=Avg("customer_rating"))["avg"],
        "upcoming": JobAssignment.objects.filter(
            user=user, job__status=Job.Status.SCHEDULED, job__scheduled_start__gte=timezone.now()
        ).count(),
    }


def sales_stats(user, days):
    since = timezone.now() - timedelta(days=days)
    mine = Quote.objects.filter(prepared_by=user)
    decided = mine.filter(created_at__gte=since, status__in=Quote.DECIDED_STATUSES).aggregate(
        won=Count("pk", filter=Q(status=Quote.Status.ACCEPTED)), total=Count("pk")
    )
    won_value = (
        mine.filter(status=Quote.Status.ACCEPTED, accepted_at__gte=since)
        .with_totals()
        .aggregate(total=Sum("total_amount"))["total"]
    )
    return {
        "quotes_sent": mine.filter(sent_at__gte=since).count(),
        "decided": decided["total"],
        "won": decided["won"],
        "close_rate": round(decided["won"] / decided["total"] * 100) if decided["total"] else None,
        "value_won": won_value or Decimal("0"),
        "follow_ups_completed": Task.objects.filter(
            kind=Task.Kind.FOLLOW_UP,
            status=Task.Status.COMPLETED,
            completed_by=user,
            completed_at__gte=since,
        ).count(),
        "open_quotes": mine.filter(status__in=Quote.OPEN_STATUSES).count(),
    }
