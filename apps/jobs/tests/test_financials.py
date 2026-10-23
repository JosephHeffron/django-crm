from datetime import date, datetime, timedelta
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


class UnguardedFigureTests(TestCase):
    """The four summary figures a mutation pass found nothing holding.

    Each rule here was already correct and had **nothing asserting
    it**: taking it out passed all 1,226 tests. `FigureTests` above is
    why, and it is worth seeing how — its fixture has no payment
    against a void invoice, no expense outside the window, a revenue
    that divides evenly (250 over 2), and no completed jobs at all. So
    each of these rules was invisible to the test that looked closest
    to covering it.

    One rule, one fixture, one assertion each, so a failure names the
    thing that broke.
    """

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner, lines=[])
        self.period = reports.report_period("month", None, None, TODAY)[0]

    def pay(self, invoice, amount, on=date(2026, 9, 25)):
        return Payment.objects.create(
            invoice=invoice,
            amount=Decimal(amount),
            received_on=on,
            recorded_by=self.owner,
        )

    def test_a_payment_against_a_void_invoice_is_not_collected(self):
        """Money taken on an invoice that was later voided is not
        income. Both payments are inside the period, so the date
        filter cannot be what separates them — only the invoice's
        status can."""
        sent = f.invoice(self.job, lines=[(Decimal("1"), Decimal("30"))], issued=date(2026, 9, 3))
        voided = f.invoice(
            self.job,
            lines=[(Decimal("1"), Decimal("70"))],
            issued=date(2026, 9, 4),
            status=Invoice.Status.VOID,
        )
        self.pay(sent, "30")
        self.pay(voided, "70")
        self.assertEqual(reports.summary(self.period)["collected"], Decimal("30"))

    def test_an_expense_outside_the_period_is_not_counted(self):
        """And `net` has to move with it, because `net` is the figure
        someone acts on."""
        for day, amount in ((date(2026, 9, 10), "40"), (date(2026, 8, 10), "500")):
            Expense.objects.create(
                date=day, amount=Decimal(amount), category="fuel", recorded_by=self.owner
            )
        figures = reports.summary(self.period)
        self.assertEqual(figures["expenses"], Decimal("40"))
        self.assertEqual(figures["net"], Decimal("-40"))

    def test_the_average_invoice_is_rounded_to_money(self):
        """Three invoices worth 50 average 16.666..., which **rounds**
        to 16.67 and **truncates** to 16.66 — so this fails for either
        mistake. The fixture above divides 250 by 2 exactly, so the
        rounding never showed at all.

        The first version of this test used 250 over 3. That is
        83.333..., which rounds and truncates to the same 83.33, so it
        asserted two decimal places and called it rounding — caught by
        Sourcery on PR #171.
        """
        for day, amount in ((3, "20"), (10, "20"), (17, "10")):
            f.invoice(
                self.job,
                lines=[(Decimal("1"), Decimal(amount))],
                issued=date(2026, 9, day),
            )
        average = reports.summary(self.period)["average_invoice"]
        self.assertEqual(average, Decimal("16.67"), "16.66 means it was truncated, not rounded")
        self.assertEqual(average.as_tuple().exponent, -2, "two decimal places, not a long third")

    def test_jobs_completed_counts_only_what_was_finished_in_the_period(self):
        """`completed_at`, not `status`, is what every count of
        finished work reads — the rule the whole app depends on, and
        the one with nothing holding it here. The job finished in
        August still has status COMPLETED, so counting by status alone
        would find two."""
        august = f.job(self.customer, self.owner, lines=[])
        for job, when in (
            (self.job, timezone.make_aware(datetime(2026, 9, 15, 10))),
            (august, timezone.make_aware(datetime(2026, 8, 15, 10))),
        ):
            job.status = Job.Status.COMPLETED
            job.completed_at = when
            job.save(update_fields=["status", "completed_at"])
        f.job(self.customer, self.owner, lines=[])  # still scheduled
        self.assertEqual(reports.summary(self.period)["jobs_completed"], 1)


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
