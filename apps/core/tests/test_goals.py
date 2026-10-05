from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.goals import progress
from apps.core.models import Goal
from apps.crm.models import Contact
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
URL = reverse("core:goals")


class GoalAccessTests(TestCase):
    def test_owner_only(self):
        for username, role in (("rep", Role.SALES_REP), ("crew", Role.CLEANER)):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(self.client.get(URL).status_code, 403)
            self.assertEqual(self.client.post(URL, {"jobs": "5"}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(URL).status_code, 302)
        self.assertFalse(Goal.objects.exists())


class GoalFormTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)

    def test_saving_targets(self):
        response = self.client.post(URL, {"revenue": "12000", "jobs": "40", "customers": "8"})
        self.assertRedirects(response, URL)
        self.assertEqual(
            dict(Goal.objects.values_list("metric", "target")),
            {
                "revenue": Decimal("12000.00"),
                "jobs": Decimal("40.00"),
                "customers": Decimal("8.00"),
            },
        )

    def test_a_blank_field_stops_tracking_that_target(self):
        self.client.post(URL, {"revenue": "12000", "jobs": "40"})
        self.client.post(URL, {"revenue": "15000"})
        self.assertEqual(
            dict(Goal.objects.values_list("metric", "target")), {"revenue": Decimal("15000.00")}
        )

    def test_a_negative_target_is_refused(self):
        response = self.client.post(URL, {"jobs": "-3"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "greater than or equal to 0")
        self.assertFalse(Goal.objects.exists())

    def test_saved_targets_come_back_in_the_form(self):
        self.client.post(URL, {"revenue": "9000.50", "jobs": "25"})
        page = self.client.get(URL).content.decode()
        self.assertIn('value="9000.50"', page)
        self.assertIn('value="25"', page)  # a count, not 25.00

    def test_the_page_says_so_when_nothing_is_set(self):
        self.assertContains(self.client.get(URL), "No goals set yet")


class GoalProgressTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.today = timezone.localdate()
        self.month_first = self.today.replace(day=1)

    def test_no_targets_means_nothing_to_show(self):
        self.assertEqual(progress(self.today), [])

    def test_revenue_progress_counts_this_month_only(self):
        Goal.objects.create(metric=Goal.Metric.REVENUE, target=Decimal("1000"))
        job = f.job(f.contact(self.owner), self.owner)
        f.invoice(job, lines=[(Decimal("1"), Decimal("400"))], issued=self.month_first)
        f.invoice(
            job,
            lines=[(Decimal("1"), Decimal("999"))],
            issued=self.month_first - timedelta(days=1),  # last month
        )
        row = progress(self.today)[0]
        self.assertEqual(
            (row.actual, row.target, row.percent), (Decimal("400"), Decimal("1000"), 40)
        )
        self.assertEqual(row.remaining, Decimal("600"))
        self.assertFalse(row.is_met)
        self.assertTrue(row.is_money)

    def test_a_met_goal_caps_the_bar_at_full(self):
        Goal.objects.create(metric=Goal.Metric.REVENUE, target=Decimal("100"))
        job = f.job(f.contact(self.owner), self.owner)
        f.invoice(job, lines=[(Decimal("1"), Decimal("250"))], issued=self.today)
        row = progress(self.today)[0]
        self.assertEqual((row.percent, row.remaining), (100, Decimal("0")))
        self.assertTrue(row.is_met)

    def test_jobs_and_customers_count_records_from_this_month(self):
        Goal.objects.create(metric=Goal.Metric.JOBS, target=Decimal("2"))
        Goal.objects.create(metric=Goal.Metric.CUSTOMERS, target=Decimal("4"))
        customer = f.contact(self.owner)
        job = f.job(customer, self.owner)
        job.status = Job.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        # A lead isn't a customer yet, so it isn't counted.
        Contact.objects.filter(pk=customer.pk).update(status=Contact.Status.CUSTOMER)
        f.contact(self.owner, "Lee", "Lead", status=Contact.Status.LEAD)

        rows = {row.metric: row for row in progress(self.today)}
        self.assertEqual(rows["jobs"].actual, Decimal("1"))
        self.assertEqual(rows["customers"].actual, Decimal("1"))
        self.assertFalse(rows["jobs"].is_money)

    def test_a_zero_target_never_divides_by_zero(self):
        Goal.objects.create(metric=Goal.Metric.JOBS, target=Decimal("0"))
        row = progress(self.today)[0]
        self.assertEqual(row.percent, 0)
        self.assertFalse(row.is_met)


class GoalDashboardTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)

    def test_the_dashboard_invites_the_owner_to_set_goals(self):
        self.assertContains(self.client.get(reverse("core:index")), "No goals set")

    def test_the_dashboard_shows_progress_once_a_goal_exists(self):
        Goal.objects.create(metric=Goal.Metric.JOBS, target=Decimal("10"))
        page = self.client.get(reverse("core:index")).content.decode()
        self.assertIn("Jobs completed", page)
        self.assertIn("progress-fill", page)  # the bar is drawn

    def test_a_sales_rep_sees_no_goals_card(self):
        Goal.objects.create(metric=Goal.Metric.JOBS, target=Decimal("10"))
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        self.assertNotContains(self.client.get(reverse("core:index")), "goal-list")
