from datetime import date, timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs import reports
from apps.jobs.models import Expense, Invoice, Job, Payment
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"
TODAY = date(2026, 9, 29)  # a Tuesday


class ReportPeriodTests(SimpleTestCase):
    def period(self, preset, start=None, end=None):
        return reports.report_period(preset, start, end, TODAY)

    def test_presets(self):
        cases = {
            "day": (TODAY, TODAY),
            "week": (date(2026, 9, 28), TODAY),
            "month": (date(2026, 9, 1), TODAY),
            "ytd": (date(2026, 1, 1), TODAY),
            "nonsense": (date(2026, 9, 1), TODAY),
        }
        for preset, expected in cases.items():
            period, error = self.period(preset)
            self.assertEqual(((period.first, period.last), error), (expected, None), preset)

    def test_custom_range_and_its_errors(self):
        period, error = self.period("custom", date(2026, 1, 5), date(2026, 3, 1))
        self.assertEqual(
            (period.first, period.last, error), (date(2026, 1, 5), date(2026, 3, 1), None)
        )
        self.assertEqual(period.label, "Jan 5, 2026 – Mar 1, 2026")
        for start, end in ((None, TODAY), (TODAY, date(2026, 1, 1)), (date(2010, 1, 1), TODAY)):
            period, error = self.period("custom", start, end)
            self.assertEqual(period.preset, "month")
            self.assertTrue(error)


class FigureTests(TestCase):
    """Exact totals against fixed fixtures (plan: financial aggregates
    against fixed fixtures)."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("rep", first_name="Sam", last_name="Rivera"), Role.SALES_REP)
        customer = f.contact(self.owner)
        sold = f.job(customer, self.owner, sales_rep=self.rep)
        house = f.job(customer, self.owner)
        f.invoice(sold, lines=[(Decimal("2"), Decimal("100"))], issued=date(2026, 9, 3))
        other = f.invoice(house, lines=[(Decimal("1"), Decimal("50"))], issued=date(2026, 9, 20))
        f.invoice(sold, issued=date(2026, 9, 21), status=Invoice.Status.DRAFT)
        f.invoice(sold, issued=date(2026, 9, 22), status=Invoice.Status.VOID)
        f.invoice(sold, issued=date(2026, 8, 31))  # previous month
        Payment.objects.create(
            invoice=other,
            amount=Decimal("30"),
            received_on=date(2026, 9, 25),
            recorded_by=self.owner,
        )
        for day, amount, category in (
            (3, "40", "fuel"),
            (10, "60", "fuel"),
            (15, "25", "supplies"),
        ):
            Expense.objects.create(
                date=date(2026, 9, day),
                amount=Decimal(amount),
                category=category,
                recorded_by=self.owner,
            )
        self.period = reports.report_period("month", None, None, TODAY)[0]

    def test_summary(self):
        s = reports.summary(self.period)
        self.assertEqual(
            (s["revenue"], s["collected"], s["expenses"], s["net"], s["invoice_count"]),
            (Decimal("250"), Decimal("30"), Decimal("125"), Decimal("125"), 2),
        )
        self.assertEqual(s["average_invoice"], Decimal("125"))

    def test_breakdowns(self):
        by_rep = reports.revenue_by_rep(self.period, Decimal("250"))
        self.assertEqual(
            [(r["name"], r["total"], r["share"], r["jobs"]) for r in by_rep],
            [("Sam Rivera", Decimal("200"), 80, 1), ("Unassigned", Decimal("50"), 20, 1)],
        )
        (service,) = reports.revenue_by_service(self.period, Decimal("250"))
        self.assertEqual(
            (service["service_type__name"], service["share"]), ("Gutter Cleaning", 100)
        )
        by_category = reports.expenses_by_category(self.period, Decimal("125"))
        self.assertEqual(
            [(r["label"], r["total"]) for r in by_category],
            [("Fuel & vehicle", Decimal("100")), ("Supplies & chemicals", Decimal("25"))],
        )

    def test_trend_includes_empty_days(self):
        kind, buckets = reports.trend(self.period)
        self.assertEqual((kind, len(buckets)), ("day", 29))
        by_day = {b["start"]: b for b in buckets}
        self.assertEqual(by_day[date(2026, 9, 3)]["revenue"], Decimal("200"))
        self.assertEqual(by_day[date(2026, 9, 3)]["expenses"], Decimal("40"))
        self.assertEqual(by_day[date(2026, 9, 4)]["revenue"], Decimal("0"))
        chart = reports.chart_bars(kind, buckets)
        tallest = min(chart["bars"], key=lambda b: b["revenue_y"])
        self.assertEqual((tallest["start"], tallest["revenue_y"]), (date(2026, 9, 3), 8.0))
        self.assertEqual(chart["axis_labels"], ["Sep 1", "Sep 8", "Sep 15", "Sep 22", "Sep 29"])

    def test_long_ranges_group_by_week_then_month(self):
        ytd = reports.report_period("ytd", None, None, TODAY)[0]
        self.assertEqual(reports.trend(ytd)[0], "month")
        self.assertEqual(len(reports.trend(ytd)[1]), 9)
        quarter = reports.report_period("custom", date(2026, 7, 1), TODAY, TODAY)[0]
        self.assertEqual(reports.trend(quarter)[0], "week")


class AgingTests(TestCase):
    def test_buckets_by_days_past_due(self):
        owner = f.user("boss")
        job = f.job(f.contact(owner), owner)
        today = timezone.localdate()
        # issued so that due_on (issued + 14) lands in each bucket
        for days_late, amount in ((-5, "10"), (10, "20"), (45, "40"), (75, "80"), (120, "160")):
            f.invoice(
                job,
                lines=[(Decimal("1"), Decimal(amount))],
                issued=today - timedelta(days=14 + days_late),
            )
        paid = f.invoice(
            job, lines=[(Decimal("1"), Decimal("999"))], issued=today - timedelta(days=200)
        )
        Payment.objects.create(
            invoice=paid, amount=Decimal("999"), received_on=today, recorded_by=owner
        )

        buckets = {b["key"]: b["total"] for b in reports.aging(today)}
        self.assertEqual(
            buckets,
            {
                "current": Decimal("10"),
                "days_30": Decimal("20"),
                "days_60": Decimal("40"),
                "days_90": Decimal("80"),
                "older": Decimal("160"),
            },
        )
        self.assertEqual(reports.outstanding()["total"], Decimal("310"))
        self.assertEqual(reports.oldest_unpaid()[0].total, Decimal("160"))


class FinancialsPageTests(TestCase):
    def test_owner_only(self):
        for username, role, expected in (
            ("boss", Role.OWNER, 200),
            ("rep", Role.SALES_REP, 403),
            ("crew", Role.CLEANER, 403),
        ):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(
                self.client.get(reverse("jobs:financials")).status_code, expected, username
            )

    def test_renders_every_preset_and_explains_a_bad_range(self):
        owner = grant_role(f.user("boss"), Role.OWNER)
        job = f.job(f.contact(owner), owner, status=Job.Status.COMPLETED)
        f.invoice(job, issued=timezone.localdate())
        self.client.login(username="boss", password=PASSWORD)
        for preset in ("day", "week", "month", "ytd"):
            response = self.client.get(reverse("jobs:financials"), {"range": preset})
            self.assertEqual(response.status_code, 200, preset)
            self.assertContains(response, "$175.00")
        response = self.client.get(
            reverse("jobs:financials"),
            {"range": "custom", "start": "2026-05-01", "end": "2026-04-01"},
        )
        self.assertContains(response, "The start date is after the end date.")
        self.assertEqual(response.context["period"].preset, "month")
