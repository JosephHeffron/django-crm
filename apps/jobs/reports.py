"""Money figures for the dashboard and Financials. Every figure is a
database aggregate — nothing loads invoice rows into Python to add up.

Definitions (one place, so every page agrees):
- **Revenue**: line totals of *sent* invoices, by issue date. A draft
  isn't billed yet, and a voided invoice was never owed.
- **Collected**: payments by the date received (not on voided invoices).
- **Outstanding**: unpaid balance of sent invoices, aged by how far past
  their due date they are as of today.
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
    InvoiceLineItem,
    Job,
    Payment,
)

PRESETS = {"day": "Today", "week": "This week", "month": "This month", "ytd": "Year to date"}
MAX_CUSTOM_DAYS = 5 * 366


def _money(expression, **filter_kwargs):
    return Coalesce(Sum(expression, **filter_kwargs), Value(ZERO), output_field=TOTAL_FIELD)


def _sent_lines(first, last):
    return InvoiceLineItem.objects.filter(
        invoice__status=Invoice.Status.SENT, invoice__issued_on__range=(first, last)
    )


def invoiced_revenue(first, last):
    """Σ line totals of sent invoices issued between two dates (inclusive)."""
    return _sent_lines(first, last).aggregate(total=_money(LINE_TOTAL))["total"]


def outstanding():
    """Unpaid balance across sent invoices, and how many are unpaid."""
    return _unpaid().aggregate(total=_money("balance_amount"), count=Count("pk"))


def _unpaid():
    return (
        Invoice.objects.filter(status=Invoice.Status.SENT)
        .with_balances()
        .filter(balance_amount__gt=0)
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
    revenue = invoiced_revenue(first, last)
    expenses = Expense.objects.filter(date__range=(first, last)).aggregate(total=_money("amount"))[
        "total"
    ]
    invoices = Invoice.objects.filter(
        status=Invoice.Status.SENT, issued_on__range=(first, last)
    ).count()
    start, end = day_bounds(first, last)
    return {
        "revenue": revenue,
        "collected": Payment.objects.filter(received_on__range=(first, last))
        .exclude(invoice__status=Invoice.Status.VOID)
        .aggregate(total=_money("amount"))["total"],
        "expenses": expenses,
        "net": revenue - expenses,
        "invoice_count": invoices,
        "average_invoice": (revenue / invoices).quantize(ZERO) if invoices else None,
        "jobs_completed": Job.objects.filter(
            status=Job.Status.COMPLETED, completed_at__gte=start, completed_at__lt=end
        ).count(),
    }


def _with_share(rows, whole):
    for row in rows:
        row["share"] = round(row["total"] / whole * 100) if whole else 0
    return rows


def revenue_by_service(period, revenue):
    rows = list(
        _sent_lines(period.first, period.last)
        .values("service_type__name", "service_type__tone")
        .annotate(total=_money(LINE_TOTAL))
        .order_by("-total", "service_type__name")
    )
    return _with_share(rows, revenue)


def revenue_by_rep(period, revenue):
    """Credited to the job's sales rep; jobs with none are "Unassigned"."""
    rows = list(
        _sent_lines(period.first, period.last)
        .values(
            "invoice__job__sales_rep",
            "invoice__job__sales_rep__first_name",
            "invoice__job__sales_rep__last_name",
            "invoice__job__sales_rep__username",
        )
        .annotate(total=_money(LINE_TOTAL), jobs=Count("invoice__job", distinct=True))
        .order_by("-total")
    )
    for row in rows:
        full = " ".join(
            filter(
                None,
                (
                    row["invoice__job__sales_rep__first_name"],
                    row["invoice__job__sales_rep__last_name"],
                ),
            )
        )
        row["name"] = full or row["invoice__job__sales_rep__username"] or "Unassigned"
    return _with_share(rows, revenue)


def expenses_by_category(period, expenses):
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

AGING_BUCKETS = (
    ("current", "Not yet due"),
    ("days_30", "1–30 days late"),
    ("days_60", "31–60 days late"),
    ("days_90", "61–90 days late"),
    ("older", "Over 90 days late"),
)


def aging(today):
    d30, d60, d90 = (today - timedelta(days=n) for n in (30, 60, 90))
    filters = {
        "current": Q(due_on__gte=today),
        "days_30": Q(due_on__lt=today, due_on__gte=d30),
        "days_60": Q(due_on__lt=d30, due_on__gte=d60),
        "days_90": Q(due_on__lt=d60, due_on__gte=d90),
        "older": Q(due_on__lt=d90),
    }
    totals = _unpaid().aggregate(
        **{key: _money("balance_amount", filter=q) for key, q in filters.items()}
    )
    return [{"key": key, "label": label, "total": totals[key]} for key, label in AGING_BUCKETS]


def oldest_unpaid(limit=10):
    return _unpaid().select_related("contact").order_by("due_on", "pk")[:limit]


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
        for row in _sent_lines(period.first, period.last)
        .annotate(bucket=Trunc("invoice__issued_on", kind, output_field=DateField()))
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
