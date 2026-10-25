"""Money figures for the dashboard and Financials. Every figure is a
database aggregate — nothing loads invoice rows into Python to add up.

Definitions (one place, so every page agrees) — ADR 0013 moved these
off invoices and onto the work itself, because this business is paid
before a job is finished and issues no invoices:
- **Revenue**: line totals of jobs **completed** in the period, dated
  by `completed_at`. Invoice status has nothing to do with it.
- **Collected**: payments by the date received. A payment against a
  voided invoice is not income; a payment with no invoice at all is
  the normal case.
- **Outstanding**: completed work whose payments do not cover its
  value, aged by how long ago it was finished. Should normally be
  empty here, which makes it an exception report.
- **Net**: revenue − expenses (a cash-basis owner's view, not an
  accountant's profit and loss).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Count, DateField, Q, Sum, Value
from django.db.models.functions import Coalesce, Trunc

from apps.crm.followups import add_months

from .calendar import day_bounds
from .models import (
    LINE_TOTAL,
    TOTAL_FIELD,
    ZERO,
    Expense,
    Invoice,
    Job,
    JobLineItem,
    Payment,
)

PRESETS = {"day": "Today", "week": "This week", "month": "This month", "ytd": "Year to date"}
MAX_CUSTOM_DAYS = 5 * 366


def _money(expression, **filter_kwargs):
    return Coalesce(Sum(expression, **filter_kwargs), Value(ZERO), output_field=TOTAL_FIELD)


def _completed_lines(first, last):
    """The line items of work **finished** between two local dates.

    ADR 0013: revenue is completed work, not sent invoices. This
    business is paid before a job is finished and issues no invoices,
    so an invoice-based figure reported nothing however much work was
    sold and paid for.

    Dated by `completed_at`, never by `status` alone — the same rule
    every other count of finished work in this app follows, and the
    reason a reopened job takes its value back out of the period.
    `day_bounds` because `completed_at` is a datetime and the period
    is a pair of local dates.
    """
    start, end = day_bounds(first, last)
    return JobLineItem.objects.filter(
        job__status=Job.Status.COMPLETED,
        job__completed_at__gte=start,
        job__completed_at__lt=end,
    )


def completed_revenue(first, last):
    """Σ line totals of work finished between two dates (inclusive)."""
    return _completed_lines(first, last).aggregate(total=_money(LINE_TOTAL))["total"]


def outstanding():
    """Work that is finished and not paid for, and how many jobs.

    ADR 0013. This business takes payment before the work is done, so
    this should normally be empty — which makes it an exception report
    rather than a routine one, and worth looking at when it is not.

    It was the unpaid balance of sent invoices, which reported nothing
    at all for a business that issues none.
    """
    return _unpaid().aggregate(total=_money("balance_amount"), count=Count("pk"))


def _unpaid():
    """Completed jobs whose payments do not cover their value.

    Status only. An earlier version also required `completed_at`, on
    the grounds that a job with no date has nothing to age it by —
    but that hid money the business is owed, which is worse than
    having nowhere tidy to put it. Such a job is bad data (the admin
    could write it before `JobAdmin.save_model` started stamping), and
    `aging` puts it in the oldest bucket so the buckets still add up
    to the total. Sourcery caught it on PR #174.
    """
    return (
        Job.objects.filter(status=Job.Status.COMPLETED).with_balances().filter(balance_amount__gt=0)
    )


# ---------- Periods ----------


@dataclass(frozen=True)
class Period:
    preset: str
    first: date
    last: date

    @property
    def label(self):
        if self.preset in PRESETS:
            return PRESETS[self.preset]
        return f"{_short(self.first)} – {_short(self.last)}"


def _short(day):
    return f"{day:%b} {day.day}, {day.year}"


def report_period(preset, start, end, today):
    """(Period, error message or None). A bad custom range falls back to
    this month and says why."""
    if preset == "custom":
        if start is None or end is None:
            error = "Pick both a start and an end date."
        elif start > end:
            error = "The start date is after the end date."
        elif (end - start).days > MAX_CUSTOM_DAYS:
            error = "Pick a range of five years or less."
        else:
            return Period("custom", start, end), None
        return report_period("month", None, None, today)[0], error
    if preset == "day":
        return Period("day", today, today), None
    if preset == "week":
        return Period("week", today - timedelta(days=today.weekday()), today), None
    if preset == "ytd":
        return Period("ytd", today.replace(month=1, day=1), today), None
    return Period("month", today.replace(day=1), today), None


# ---------- Figures for a period ----------


def summary(period):
    first, last = period.first, period.last
    revenue = completed_revenue(first, last)
    expenses = Expense.objects.filter(date__range=(first, last)).aggregate(total=_money("amount"))[
        "total"
    ]
    start, end = day_bounds(first, last)
    # The jobs revenue is made of, so the count and the average cannot
    # describe a different set from the total above them. `invoice_count`
    # and `average_invoice` used to sit here and counted sent invoices
    # — a second definition of "how much work was there", and one that
    # reported nothing for a business that does not invoice (ADR 0013).
    completed = Job.objects.filter(
        status=Job.Status.COMPLETED, completed_at__gte=start, completed_at__lt=end
    ).count()
    return {
        "revenue": revenue,
        "collected": Payment.objects.filter(received_on__range=(first, last))
        .exclude(invoice__status=Invoice.Status.VOID)
        .aggregate(total=_money("amount"))["total"],
        "expenses": expenses,
        "net": revenue - expenses,
        "jobs_completed": completed,
        "average_job": (revenue / completed).quantize(ZERO) if completed else None,
    }


def _with_share(rows, given=None):
    whole = _whole(rows, given)
    for row in rows:
        row["share"] = round(row["total"] / whole * 100) if whole else 0
    return rows


def revenue_by_service(period, revenue=None):
    rows = list(
        _completed_lines(period.first, period.last)
        .values("service_type__name", "service_type__tone")
        .annotate(total=_money(LINE_TOTAL))
        .order_by("-total", "service_type__name")
    )
    return _with_share(rows, revenue)


def _whole(rows, given):
    """What the shares are a share of. Taken from the rows themselves
    unless a caller insists, so a change between the two queries can't
    leave shares that don't add up."""
    return sum((row["total"] for row in rows), ZERO) if given is None else given


def revenue_by_rep(period, revenue=None):
    """Credited to the job's sales rep; jobs with none are "Unassigned".

    One join shorter than it was: the lines belong to the job now, not
    to an invoice for the job.
    """
    rows = list(
        _completed_lines(period.first, period.last)
        .values(
            "job__sales_rep",
            "job__sales_rep__first_name",
            "job__sales_rep__last_name",
            "job__sales_rep__username",
        )
        .annotate(total=_money(LINE_TOTAL), jobs=Count("job", distinct=True))
        .order_by("-total")
    )
    for row in rows:
        full = " ".join(
            filter(
                None,
                (row["job__sales_rep__first_name"], row["job__sales_rep__last_name"]),
            )
        )
        row["name"] = full or row["job__sales_rep__username"] or "Unassigned"
    return _with_share(rows, revenue)


def expenses_by_category(period, expenses=None):
    labels = dict(Expense.Category.choices)
    rows = list(
        Expense.objects.filter(date__range=(period.first, period.last))
        .values("category")
        .annotate(total=_money("amount"))
        .order_by("-total", "category")
    )
    for row in rows:
        row["label"] = labels.get(row["category"], row["category"])
    return _with_share(rows, expenses)


# ---------- Outstanding, as of today ----------

# Aged by how long ago the work was finished, not by a due date on a
# document (ADR 0013). There is no "not yet due" bucket any more:
# payment is expected before the work is done here, so anything in
# this table is already money that should have arrived. The first
# bucket is a week rather than a day so that finishing a job on Friday
# and banking the cheque on Monday does not look like a problem.
AGING_BUCKETS = (
    ("days_7", "Finished this week"),
    ("days_30", "8–30 days ago"),
    ("days_60", "31–60 days ago"),
    ("days_90", "61–90 days ago"),
    ("older", "Over 90 days ago"),
)


def aging(today):
    d7, d30, d60, d90 = (today - timedelta(days=n) for n in (7, 30, 60, 90))
    # `completed_at` is a datetime, so each boundary is the start of
    # that local day — comparing a datetime against a date would
    # quietly drop everything finished after midnight on the edge.
    at7, at30, at60, at90 = (day_bounds(d, d)[0] for d in (d7, d30, d60, d90))
    # The five buckets partition the set, so their totals always add
    # up to `outstanding()["total"]`. Two deliberate edges:
    #
    # - A job with **no** completion date goes in `older`. It is bad
    #   data rather than old work, but it is money owed, and dropping
    #   it would leave the buckets short of the total with nothing on
    #   the page to say why.
    # - A completion date in the **future** falls in `days_7`, which
    #   is not bounded above. Also bad data; the alternative is a row
    #   that belongs to no bucket and disappears from the table while
    #   still counting in the headline.
    filters = {
        "days_7": Q(completed_at__gte=at7),
        "days_30": Q(completed_at__lt=at7, completed_at__gte=at30),
        "days_60": Q(completed_at__lt=at30, completed_at__gte=at60),
        "days_90": Q(completed_at__lt=at60, completed_at__gte=at90),
        "older": Q(completed_at__lt=at90) | Q(completed_at__isnull=True),
    }
    totals = _unpaid().aggregate(
        **{key: _money("balance_amount", filter=q) for key, q in filters.items()}
    )
    return [{"key": key, "label": label, "total": totals[key]} for key, label in AGING_BUCKETS]


def oldest_unpaid(limit=10):
    """Longest-finished first — the work waiting on money the longest.

    `completed_at` nulls sort first on PostgreSQL ascending, which
    suits this list: a job with no date is the one to look at.
    """
    return _unpaid().select_related("contact").order_by("completed_at", "pk")[:limit]


# ---------- Trend ----------


def _granularity(period):
    days = (period.last - period.first).days + 1
    if days <= 31:
        return "day"
    if days <= 184:
        return "week"
    return "month"


def _bucket_starts(period, kind):
    if kind == "day":
        current, step = period.first, lambda d: d + timedelta(days=1)
    elif kind == "week":
        current, step = (
            period.first - timedelta(days=period.first.weekday()),
            lambda d: d + timedelta(days=7),
        )
    else:
        current, step = period.first.replace(day=1), lambda d: add_months(d, 1)
    while current <= period.last:
        yield current
        current = step(current)


def trend(period):
    """Revenue and expenses per day / week / month across the period —
    including empty buckets, so gaps show as gaps."""
    kind = _granularity(period)
    revenue = {
        row["bucket"]: row["total"]
        for row in _completed_lines(period.first, period.last)
        .annotate(bucket=Trunc("job__completed_at", kind, output_field=DateField()))
        .values("bucket")
        .annotate(total=_money(LINE_TOTAL))
    }
    expenses = {
        row["bucket"]: row["total"]
        for row in Expense.objects.filter(date__range=(period.first, period.last))
        .annotate(bucket=Trunc("date", kind, output_field=DateField()))
        .values("bucket")
        .annotate(total=_money("amount"))
    }
    return kind, [
        {"start": start, "revenue": revenue.get(start, ZERO), "expenses": expenses.get(start, ZERO)}
        for start in _bucket_starts(period, kind)
    ]


# SVG geometry for the trend chart, computed here because the CSP forbids
# inline styles — the template only copies numbers into SVG attributes.
CHART_WIDTH, CHART_HEIGHT, CHART_TOP = 600, 180, 8
# The SVG stretches to the card's width, which would distort text inside
# it, so a few evenly spaced date labels sit in a row underneath instead.
AXIS_LABELS = 5


def chart_bars(kind, buckets):
    if not buckets:
        return None
    peak = max(max(b["revenue"], b["expenses"]) for b in buckets)
    slot = CHART_WIDTH / len(buckets)
    bar = max(slot * 0.38, 1)
    usable = CHART_HEIGHT - CHART_TOP

    def label(day):
        return f"{day:%b %Y}" if kind == "month" else f"{day:%b} {day.day}"

    def height(value):
        return round(float(value / peak) * usable, 1) if peak else 0

    bars = []
    for index, bucket in enumerate(buckets):
        x = index * slot + slot * 0.1
        rev_h, exp_h = height(bucket["revenue"]), height(bucket["expenses"])
        bars.append(
            {
                **bucket,
                "label": label(bucket["start"]),
                "revenue_x": round(x, 1),
                "expenses_x": round(x + bar, 1),
                "width": round(bar, 1),
                "revenue_y": round(CHART_HEIGHT - rev_h, 1),
                "revenue_h": rev_h,
                "expenses_y": round(CHART_HEIGHT - exp_h, 1),
                "expenses_h": exp_h,
            }
        )
    count = min(AXIS_LABELS, len(bars))
    picks = (
        sorted({round(i * (len(bars) - 1) / (count - 1)) for i in range(count)})
        if count > 1
        else [0]
    )
    return {
        "bars": bars,
        "axis_labels": [bars[i]["label"] for i in picks],
        "width": CHART_WIDTH,
        "height": CHART_HEIGHT,
        "peak": peak,
        "kind": kind,
    }


# ---------- Mini chart for the dashboard's overview cards ----------

# A small bar strip, not the full trend chart: same CSP reasoning — the
# geometry is computed here and the template only copies numbers into
# SVG attributes.
SPARK_WIDTH, SPARK_HEIGHT = 120, 32


def sparkline(buckets, key="revenue"):
    """Bar geometry for one series across `buckets` (from trend()).

    Returns None when there's nothing to draw — every bucket empty means
    a chart of zero-height bars, which reads as a broken image rather
    than as "no money yet", so the card shows a dash instead.
    """
    values = [bucket[key] for bucket in buckets]
    peak = max(values, default=ZERO)
    if not values or peak <= 0:
        return None
    slot = SPARK_WIDTH / len(values)
    bar = max(slot * 0.6, 1)
    bars = []
    for index, value in enumerate(values):
        height = round(float(value / peak) * SPARK_HEIGHT, 1)
        bars.append(
            {
                "x": round(index * slot + (slot - bar) / 2, 1),
                "y": round(SPARK_HEIGHT - height, 1),
                "width": round(bar, 1),
                "height": height or 0.5,  # a visible floor for empty days
                "start": buckets[index]["start"],
                "value": value,
            }
        )
    return {"bars": bars, "width": SPARK_WIDTH, "height": SPARK_HEIGHT, "peak": peak}


def change(current, previous):
    """Percent change between two totals, or None when there's no
    earlier figure to compare against (a first month has no trend)."""
    if previous is None or previous <= 0:
        return None
    return int(round(float((current - previous) / previous) * 100))


# ---------- The Invoices list ----------

# What a person means when they pick a filter. "Paid" and "overdue"
# aren't stored — they follow from the payments and the due date — so
# they're expressed here as queryset filters rather than as a column
# that could drift out of step with the money.
INVOICE_FILTERS = {
    "unpaid": "Unpaid",
    "overdue": "Overdue",
    "paid": "Paid",
    "draft": "Draft",
    "void": "Void",
    "all": "All",
}


def filter_invoices(invoices, key, today):
    """`invoices` must already carry with_balances()."""
    sent = invoices.filter(status=Invoice.Status.SENT)
    if key == "unpaid":
        return sent.filter(balance_amount__gt=0)
    if key == "overdue":
        return sent.filter(balance_amount__gt=0, due_on__lt=today)
    if key == "paid":
        return sent.filter(balance_amount__lte=0)
    if key == "draft":
        return invoices.filter(status=Invoice.Status.DRAFT)
    if key == "void":
        return invoices.filter(status=Invoice.Status.VOID)
    return invoices


def invoice_totals(invoices):
    """Billed, collected, and still owed across whatever is listed."""
    return invoices.aggregate(
        billed=_money("total_amount"),
        collected=_money("paid_amount"),
        owed=_money("balance_amount", filter=Q(balance_amount__gt=0)),
        count=Count("pk"),
    )
