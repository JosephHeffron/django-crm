"""The Reports page (Phase 17.5 step 9).

A short catalogue of questions the business actually asks, each answered
over a period you choose, shown as a table and downloadable as CSV. The
money ones reuse `apps/jobs/reports.py`, so a report and the Profit page
can never disagree about what a month earned.

A report declares its columns, and what each column holds — text, money,
a count, or a percentage. The page renders from that, and the CSV
exports the same values, so the two can't drift apart.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncMonth

from apps.crm.models import Contact, Task

from . import crew, reports
from .models import Job, JobAssignment, Quote

TEXT, MONEY, NUMBER, PERCENT, HOURS = "text", "money", "number", "percent", "hours"


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    kind: str = TEXT


@dataclass(frozen=True)
class Report:
    slug: str
    title: str
    blurb: str
    icon: str
    columns: tuple
    build: object
    owner_only: bool = False
    note: str = ""

    def rows(self, period):
        return self.build(period)


@dataclass
class Table:
    report: Report
    rows: list
    totals: dict = field(default_factory=dict)


def _name(first, last, username):
    return " ".join(filter(None, (first, last))) or username or "Unassigned"


# ---------- The money ones ----------


def _revenue_by_service(period):
    return [
        {
            "name": row["service_type__name"],
            "total": row["total"],
            "share": row["share"],
        }
        for row in reports.revenue_by_service(period)
    ]


def _revenue_by_rep(period):
    return [
        {"name": row["name"], "jobs": row["jobs"], "total": row["total"], "share": row["share"]}
        for row in reports.revenue_by_rep(period)
    ]


def _expenses_by_category(period):
    return [
        {"name": row["label"], "total": row["total"], "share": row["share"]}
        for row in reports.expenses_by_category(period)
    ]


def _bucket_label(start, kind):
    return f"{start:%b %Y}" if kind == "month" else f"{start:%b %-d}"


def _profit_by_month(period):
    """Revenue, expenses and what's left, month by month. The same
    definitions the Profit page uses."""
    kind, buckets = reports.trend(period)
    rows = []
    for bucket in buckets:
        revenue, expenses = bucket["revenue"], bucket["expenses"]
        rows.append(
            {
                "name": _bucket_label(bucket["start"], kind),
                "revenue": revenue,
                "expenses": expenses,
                "profit": revenue - expenses,
            }
        )
    return rows


# ---------- The work ----------


def _jobs_by_status(period):
    first, last = reports.day_bounds(period.first, period.last)
    rows = list(
        Job.objects.filter(scheduled_start__gte=first, scheduled_start__lt=last)
        .values("status")
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    labels = dict(Job.Status.choices)
    whole = sum(row["count"] for row in rows)
    return [
        {
            "name": labels.get(row["status"], row["status"]),
            "count": row["count"],
            "share": round(row["count"] / whole * 100) if whole else 0,
        }
        for row in rows
    ]


def _jobs_by_service(period):
    first, last = reports.day_bounds(period.first, period.last)
    rows = list(
        Job.objects.filter(scheduled_start__gte=first, scheduled_start__lt=last)
        .values("primary_service_type__name")
        .annotate(
            count=Count("pk"),
            finished=Count("pk", filter=Q(status=Job.Status.COMPLETED)),
            rating=Avg("customer_rating"),
        )
        .order_by("-count")
    )
    return [
        {
            "name": row["primary_service_type__name"],
            "count": row["count"],
            "finished": row["finished"],
            "rating": round(row["rating"], 1) if row["rating"] is not None else None,
        }
        for row in rows
    ]


def _crew_hours(period):
    """Hours clocked and what they cost, per person — the same figures
    Payroll shows, in a form you can keep.

    Anyone who clocked time in the period is included, even if they've
    since left or changed role: a report about last spring shouldn't
    quietly drop the people who did the work.
    """
    people = crew.people_who_worked(period.first, period.last)
    rows = crew.payroll(people, period.first, period.last)
    out = []
    for row in rows:
        jobs = JobAssignment.objects.filter(
            user=row["person"],
            job__status=Job.Status.COMPLETED,
            job__completed_at__gte=reports.day_bounds(period.first, period.last)[0],
            job__completed_at__lt=reports.day_bounds(period.first, period.last)[1],
        ).count()
        out.append(
            {
                "name": _name(
                    row["person"].first_name, row["person"].last_name, row["person"].get_username()
                ),
                "hours": row["hours"],
                "jobs": jobs,
                "pay": row["pay"],
            }
        )
    return out


# ---------- Customers and estimates ----------


def _new_customers(period):
    first, last = reports.day_bounds(period.first, period.last)
    rows = list(
        Contact.objects.filter(created_at__gte=first, created_at__lt=last)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            count=Count("pk"),
            customers=Count("pk", filter=Q(status=Contact.Status.CUSTOMER)),
        )
        .order_by("month")
    )
    return [
        {
            "name": f"{row['month']:%b %Y}",
            "count": row["count"],
            "customers": row["customers"],
        }
        for row in rows
    ]


def _customers_by_source(period):
    first, last = reports.day_bounds(period.first, period.last)
    labels = dict(Contact.LeadSource.choices)
    rows = list(
        # Customers, not every contact: a lead that came from a referral
        # and never bought isn't where a customer came from.
        Contact.objects.filter(
            created_at__gte=first, created_at__lt=last, status=Contact.Status.CUSTOMER
        )
        .values("lead_source")
        .annotate(count=Count("pk"))
        .order_by("-count")
    )
    whole = sum(row["count"] for row in rows)
    return [
        {
            "name": labels.get(row["lead_source"], row["lead_source"] or "Not recorded"),
            "count": row["count"],
            "share": round(row["count"] / whole * 100) if whole else 0,
        }
        for row in rows
    ]


def _estimate_outcomes(period):
    """How estimates written in the period turned out, by whoever wrote
    them. Win rate counts only the decided ones — an estimate still out
    hasn't been lost."""
    first, last = reports.day_bounds(period.first, period.last)
    rows = list(
        Quote.objects.filter(created_at__gte=first, created_at__lt=last)
        .values("prepared_by__first_name", "prepared_by__last_name", "prepared_by__username")
        .annotate(
            written=Count("pk"),
            won=Count("pk", filter=Q(status=Quote.Status.ACCEPTED)),
            decided=Count("pk", filter=Q(status__in=Quote.DECIDED_STATUSES)),
        )
        .order_by("-written")
    )
    return [
        {
            "name": _name(
                row["prepared_by__first_name"],
                row["prepared_by__last_name"],
                row["prepared_by__username"],
            ),
            "written": row["written"],
            "won": row["won"],
            "rate": round(row["won"] / row["decided"] * 100) if row["decided"] else None,
        }
        for row in rows
    ]


def _follow_ups(period):
    first, last = reports.day_bounds(period.first, period.last)
    rows = list(
        Task.objects.filter(kind=Task.Kind.FOLLOW_UP, created_at__gte=first, created_at__lt=last)
        .values("service_type__name")
        .annotate(
            raised=Count("pk"),
            done=Count("pk", filter=Q(status=Task.Status.COMPLETED)),
        )
        .order_by("-raised")
    )
    return [
        {
            "name": row["service_type__name"] or "No service",
            "raised": row["raised"],
            "done": row["done"],
            "rate": round(row["done"] / row["raised"] * 100) if row["raised"] else 0,
        }
        for row in rows
    ]


CATALOGUE = (
    Report(
        "revenue-by-service",
        "Revenue by service",
        "Which work brings the money in.",
        "dollar",
        (
            Column("name", "Service"),
            Column("total", "Revenue", MONEY),
            Column("share", "Share", PERCENT),
        ),
        _revenue_by_service,
        owner_only=True,
        note="Counts sent invoices by the date issued. Drafts aren't billed "
        "yet; voided ones were never owed.",
    ),
    Report(
        "revenue-by-rep",
        "Revenue by sales rep",
        "Who sold the work that got invoiced.",
        "users",
        (
            Column("name", "Sales rep"),
            Column("jobs", "Jobs", NUMBER),
            Column("total", "Revenue", MONEY),
            Column("share", "Share", PERCENT),
        ),
        _revenue_by_rep,
        owner_only=True,
        note="Credited to the job's sales rep. Jobs with nobody credited show as Unassigned.",
    ),
    Report(
        "profit-by-month",
        "Profit over time",
        "Revenue against expenses, period by period.",
        "trend-up",
        (
            Column("name", "Period"),
            Column("revenue", "Revenue", MONEY),
            Column("expenses", "Expenses", MONEY),
            Column("profit", "Profit", MONEY),
        ),
        _profit_by_month,
        owner_only=True,
    ),
    Report(
        "expenses-by-category",
        "Expenses by category",
        "Where the money goes.",
        "wallet",
        (
            Column("name", "Category"),
            Column("total", "Spent", MONEY),
            Column("share", "Share", PERCENT),
        ),
        _expenses_by_category,
        owner_only=True,
    ),
    Report(
        "crew-hours",
        "Crew hours and pay",
        "Clocked time and what it cost, per person.",
        "clock",
        (
            Column("name", "Person"),
            Column("hours", "Hours", HOURS),
            Column("jobs", "Jobs finished", NUMBER),
            Column("pay", "Pay", MONEY),
        ),
        _crew_hours,
        owner_only=True,
        note="Pay is clocked hours times their rate. Anyone without a rate shows no pay.",
    ),
    Report(
        "jobs-by-status",
        "Jobs by status",
        "How the work in a period ended up.",
        "briefcase",
        (
            Column("name", "Status"),
            Column("count", "Jobs", NUMBER),
            Column("share", "Share", PERCENT),
        ),
        _jobs_by_status,
    ),
    Report(
        "jobs-by-service",
        "Jobs by service",
        "What you did most of, and how it was rated.",
        "calendar",
        (
            Column("name", "Service"),
            Column("count", "Booked", NUMBER),
            Column("finished", "Finished", NUMBER),
            Column("rating", "Avg rating", NUMBER),
        ),
        _jobs_by_service,
    ),
    Report(
        "new-customers",
        "New customers",
        "How many you gained, month by month.",
        "user-plus",
        (
            Column("name", "Month"),
            Column("count", "Added", NUMBER),
            Column("customers", "Now customers", NUMBER),
        ),
        _new_customers,
    ),
    Report(
        "customers-by-source",
        "Where customers come from",
        "Which way of finding you actually works.",
        "share",
        (
            Column("name", "Source"),
            Column("count", "Customers", NUMBER),
            Column("share", "Share", PERCENT),
        ),
        _customers_by_source,
    ),
    Report(
        "estimate-outcomes",
        "Estimate outcomes",
        "How many you win, and who wins them.",
        "briefcase",
        (
            Column("name", "Prepared by"),
            Column("written", "Written", NUMBER),
            Column("won", "Won", NUMBER),
            Column("rate", "Win rate", PERCENT),
        ),
        _estimate_outcomes,
        note="Win rate counts only estimates that have been decided — one "
        "still out hasn't been lost.",
    ),
    Report(
        "follow-ups",
        "Follow-ups",
        "Raised against done, by service.",
        "refresh",
        (
            Column("name", "Service"),
            Column("raised", "Raised", NUMBER),
            Column("done", "Done", NUMBER),
            # A distinct label: the CSV keys on it, so two "Done"
            # columns would overwrite each other in the file.
            Column("rate", "Done rate", PERCENT),
        ),
        _follow_ups,
    ),
)

BY_SLUG = {report.slug: report for report in CATALOGUE}


def visible(is_owner):
    return [report for report in CATALOGUE if is_owner or not report.owner_only]


def build(report, period):
    rows = report.rows(period)
    totals = {}
    for column in report.columns:
        if column.kind in (MONEY, NUMBER, HOURS) and column.key != "rating":
            values = [row.get(column.key) for row in rows]
            numbers = [v for v in values if isinstance(v, (int, Decimal))]
            if numbers:
                totals[column.key] = sum(numbers)
    return Table(report=report, rows=rows, totals=totals)


CENTS = Decimal("0.01")


def _for_file(value, kind):
    """Money and hours are sums of sums and arrive with more decimal
    places than they're worth; the page quantizes them through its
    filters, so the file has to as well or a download won't match what
    was on screen."""
    if value is None:
        return ""
    if kind in (MONEY, HOURS) and isinstance(value, Decimal):
        return value.quantize(CENTS)
    return value


def csv_rows(table):
    """The same values the table shows, keyed by the column labels.

    A period with nothing in it still yields one row of blanks, so the
    file carries its column headings instead of downloading as zero
    bytes — "no sales in March" is an answer, and an empty file isn't.

    Totals are deliberately left out: a spreadsheet sums a column in one
    click, and a totals row inside the data breaks sorting and filtering
    for everyone who opens it.
    """
    labels = [column.label for column in table.report.columns]
    if not table.rows:
        yield dict.fromkeys(labels, "")
        return
    for row in table.rows:
        yield {
            column.label: _for_file(row.get(column.key), column.kind)
            for column in table.report.columns
        }
