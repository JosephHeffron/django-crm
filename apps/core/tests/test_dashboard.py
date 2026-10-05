import datetime
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.core.views import _greeting
from apps.crm.followups import add_months
from apps.crm.models import Activity, Company, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Invoice, Job, Payment, Quote
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"


def at_today(hour, days=0):
    day = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(datetime.datetime.combine(day, datetime.time(hour)))


class DashboardTestCase(TestCase):
    role = Role.SALES_REP

    def setUp(self):
        self.user = grant_role(f.user("alice"), self.role)
        self.client.login(username="alice", password=PASSWORD)

    def get(self):
        return self.client.get(reverse("core:index"))


class NoRoleDashboardTests(TestCase):
    def test_no_role_sees_only_the_notice(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "No role assigned yet")
        self.assertNotIn("todays_jobs", response.context)


class OwnerDashboardTests(DashboardTestCase):
    role = Role.OWNER

    def test_revenue_counts_sent_invoices_by_issue_date(self):
        customer = f.contact(self.user)
        job = f.job(customer, self.user)
        today = timezone.localdate()
        monday = today - timedelta(days=today.weekday())
        f.invoice(job, lines=[(Decimal("2"), Decimal("100"))], issued=today)
        f.invoice(job, lines=[(Decimal("1"), Decimal("50"))], issued=monday)
        f.invoice(job, issued=today, status=Invoice.Status.DRAFT)  # not billed yet
        f.invoice(job, issued=today, status=Invoice.Status.VOID)  # never owed
        f.invoice(job, issued=monday - timedelta(days=1))  # last week

        context = self.get().context
        self.assertEqual(
            context["revenue_today"], Decimal("250") if today == monday else Decimal("200")
        )
        self.assertEqual(context["revenue_week"], Decimal("250"))

    def test_outstanding_is_the_unpaid_balance_of_sent_invoices(self):
        job = f.job(f.contact(self.user), self.user)
        partly = f.invoice(job, lines=[(Decimal("1"), Decimal("300"))])
        Payment.objects.create(
            invoice=partly,
            amount=Decimal("100"),
            received_on=partly.issued_on,
            recorded_by=self.user,
        )
        paid = f.invoice(job, lines=[(Decimal("1"), Decimal("80"))])
        Payment.objects.create(
            invoice=paid, amount=Decimal("80"), received_on=paid.issued_on, recorded_by=self.user
        )
        f.invoice(job, status=Invoice.Status.DRAFT)

        outstanding = self.get().context["outstanding"]
        self.assertEqual((outstanding["total"], outstanding["count"]), (Decimal("200"), 1))

    def test_owner_sees_every_open_quote_and_follow_up(self):
        rep = grant_role(f.user("rep"), Role.SALES_REP)
        customer = f.contact(self.user)
        f.quote(customer, rep, status=Quote.Status.SENT)
        f.quote(customer, self.user, status=Quote.Status.DRAFT)
        f.quote(customer, rep, status=Quote.Status.ACCEPTED)  # not open
        Task.objects.create(
            title="Follow up",
            kind=Task.Kind.FOLLOW_UP,
            contact=customer,
            service_type=f.service(),
            assigned_to=rep,
            created_by=rep,
            due_date=timezone.localdate() - timedelta(days=2),
        )
        context = self.get().context
        self.assertEqual(context["open_quotes"]["count"], 2)
        self.assertEqual(context["open_quotes"]["total"], Decimal("200"))
        self.assertEqual((context["follow_ups_due"], context["follow_ups_overdue"]), (1, 1))


class SalesRepDashboardTests(DashboardTestCase):
    def test_no_money_figures_for_a_sales_rep(self):
        response = self.get()
        self.assertNotIn("revenue_today", response.context)
        self.assertNotContains(response, "Revenue")
        self.assertNotContains(response, "Outstanding")

    def test_quotes_follow_ups_and_visits_are_the_reps_own(self):
        other = grant_role(f.user("other"), Role.SALES_REP)
        customer = f.contact(self.user)
        mine = f.quote(customer, self.user, status=Quote.Status.SENT, site_visit_at=at_today(15, 2))
        f.quote(customer, other, status=Quote.Status.SENT, site_visit_at=at_today(15, 2))
        f.quote(customer, self.user, status=Quote.Status.SENT, site_visit_at=at_today(15, 9))
        for assignee in (self.user, other):
            Task.objects.create(
                title="Follow up",
                kind=Task.Kind.FOLLOW_UP,
                contact=f.contact(self.user, first=assignee.username),
                service_type=f.service(),
                assigned_to=assignee,
                created_by=assignee,
                due_date=timezone.localdate(),
            )
        context = self.get().context
        self.assertEqual(context["open_quotes"]["count"], 2)
        self.assertEqual(list(context["site_visits"]), [mine])  # 9 days out is excluded
        self.assertEqual((context["follow_ups_due"], context["follow_ups_overdue"]), (1, 0))

    def test_todays_schedule_lists_todays_jobs_in_time_order(self):
        customer = f.contact(self.user)
        late = f.job(customer, self.user, start=at_today(14))
        early = f.job(customer, self.user, start=at_today(8))
        f.job(customer, self.user, start=at_today(9, days=1))
        f.job(customer, self.user, start=at_today(10), status=Job.Status.CANCELLED)
        context = self.get().context
        self.assertEqual(list(context["todays_jobs"]), [early, late])
        self.assertEqual(context["todays_job_count"], 2)


class CleanerDashboardTests(DashboardTestCase):
    role = Role.CLEANER

    def test_only_own_jobs_and_no_business_data(self):
        owner = f.user("boss")
        customer = f.contact(owner)
        mine = f.job(customer, owner, start=at_today(9))
        f.assign(mine, self.user)
        f.job(customer, owner, start=at_today(11))  # someone else's
        tomorrow = f.job(customer, owner, start=at_today(9, days=1))
        f.assign(tomorrow, self.user)

        response = self.get()
        self.assertEqual(list(response.context["todays_jobs"]), [mine])
        self.assertEqual(list(response.context["upcoming_jobs"]), [tomorrow])
        self.assertNotIn("open_quotes", response.context)
        self.assertNotIn("recent_activities", response.context)
        self.assertNotContains(response, "Recent activity")

    def test_hours_and_jobs_done_this_week(self):
        owner = f.user("boss")
        customer = f.contact(owner)
        done = f.job(customer, owner, status=Job.Status.COMPLETED)
        Job.objects.filter(pk=done.pk).update(completed_at=timezone.now())
        f.assign(done, self.user, hours=Decimal("2.5"))
        old = f.job(customer, owner, status=Job.Status.COMPLETED)
        Job.objects.filter(pk=old.pk).update(completed_at=timezone.now() - timedelta(days=8))
        f.assign(old, self.user, hours=Decimal("4"))

        context = self.get().context
        self.assertEqual(context["jobs_done_this_week"], 1)
        self.assertEqual(context["hours_this_week"], Decimal("2.5"))


class DashboardMyTasksTests(DashboardTestCase):
    def test_shows_only_my_pending_tasks(self):
        other = f.user("bob")
        mine = Task.objects.create(title="Mine", assigned_to=self.user, created_by=self.user)
        Task.objects.create(title="Not mine", assigned_to=other, created_by=self.user)
        Task.objects.create(
            title="Mine but done",
            assigned_to=self.user,
            created_by=self.user,
            status=Task.Status.COMPLETED,
        )
        self.assertEqual(list(self.get().context["my_tasks"]), [mine])

    def test_overdue_task_is_marked(self):
        Task.objects.create(
            title="Late task",
            assigned_to=self.user,
            created_by=self.user,
            due_date=timezone.localdate() - timedelta(days=1),
        )
        response = self.get()
        self.assertContains(response, "Late task")
        self.assertContains(response, "Overdue")

    def test_empty_state_message(self):
        self.assertContains(self.get(), "No pending tasks")

    def test_my_tasks_capped_at_dashboard_limit(self):
        from apps.core.views import DASHBOARD_LIST_LIMIT

        for i in range(DASHBOARD_LIST_LIMIT + 5):
            Task.objects.create(title=f"Task {i}", assigned_to=self.user, created_by=self.user)
        self.assertEqual(len(self.get().context["my_tasks"]), DASHBOARD_LIST_LIMIT)


class DashboardRecentActivityTests(DashboardTestCase):
    def setUp(self):
        super().setUp()
        self.company = Company.objects.create(name="Acme", created_by=self.user)

    def test_shows_recent_activity(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="A note",
            company=self.company,
            created_by=self.user,
        )
        self.assertContains(self.get(), "A note")

    def test_empty_state_message(self):
        self.assertContains(self.get(), "No activity yet")

    def test_recent_activity_capped_at_dashboard_limit(self):
        from apps.core.views import DASHBOARD_LIST_LIMIT

        for i in range(DASHBOARD_LIST_LIMIT + 5):
            Activity.objects.create(
                activity_type=Activity.ActivityType.NOTE,
                subject=f"Note {i}",
                company=self.company,
                created_by=self.user,
            )
        self.assertEqual(len(self.get().context["recent_activities"]), DASHBOARD_LIST_LIMIT)


class DashboardLayoutTests(DashboardTestCase):
    """The reference layout's own pieces (Phase 17.5 step 4)."""

    role = Role.OWNER

    def test_the_greeting_follows_the_clock(self):
        self.assertEqual(
            [_greeting(hour) for hour in (0, 9, 12, 17, 18, 23)],
            [
                "Good morning",
                "Good morning",
                "Good afternoon",
                "Good afternoon",
                "Good evening",
                "Good evening",
            ],
        )

    def test_the_greeting_uses_a_first_name(self):
        self.user.first_name = "Alex"
        self.user.save(update_fields=["first_name"])
        self.assertContains(self.get(), "Good", msg_prefix="greeting missing")
        self.assertContains(self.get(), "Alex")

    def test_the_owner_gets_four_cards_with_an_accent_each(self):
        cards = self.get().context["cards"]
        self.assertEqual(len(cards), 4)
        self.assertTrue(all(card["accent"] for card in cards))
        self.assertEqual(cards[0]["label"], "Revenue this month")

    def test_the_revenue_card_keeps_today_and_this_week(self):
        job = f.job(f.contact(self.user), self.user)
        f.invoice(job, lines=[(Decimal("1"), Decimal("120"))], issued=timezone.localdate())
        context = self.get().context
        self.assertEqual(context["revenue_today"], Decimal("120"))
        self.assertIn("today", context["cards"][0]["meta"])

    def test_the_mini_chart_appears_once_there_is_revenue(self):
        self.assertIsNone(self.get().context["revenue_spark"])
        job = f.job(f.contact(self.user), self.user)
        f.invoice(job, lines=[(Decimal("1"), Decimal("120"))], issued=timezone.localdate())
        response = self.get()
        self.assertIsNotNone(response.context["revenue_spark"])
        self.assertContains(response, "spark-bar")

    def test_revenue_is_compared_with_the_same_stretch_of_last_month(self):
        today = timezone.localdate()
        job = f.job(f.contact(self.user), self.user)
        f.invoice(job, lines=[(Decimal("1"), Decimal("200"))], issued=today)
        last_month = add_months(today.replace(day=1), -1)
        f.invoice(job, lines=[(Decimal("1"), Decimal("100"))], issued=last_month)
        self.assertEqual(self.get().context["revenue_change"], 100)

    def test_no_comparison_without_an_earlier_month(self):
        job = f.job(f.contact(self.user), self.user)
        f.invoice(job, lines=[(Decimal("1"), Decimal("200"))], issued=timezone.localdate())
        self.assertIsNone(self.get().context["revenue_change"])

    def test_quick_action_tiles_only_point_where_the_role_may_go(self):
        owner_tiles = {action["label"] for action in self.get().context["quick_actions"]}
        self.assertIn("Financials", owner_tiles)
        grant_role(f.user("crew"), Role.CLEANER)
        self.client.login(username="crew", password=PASSWORD)
        crew_tiles = {action["label"] for action in self.get().context["quick_actions"]}
        self.assertEqual(crew_tiles, {"Schedule", "Inbox"})

    def test_a_cleaner_gets_their_own_cards_and_no_money(self):
        grant_role(f.user("crew"), Role.CLEANER)
        self.client.login(username="crew", password=PASSWORD)
        response = self.get()
        self.assertEqual(
            [card["label"] for card in response.context["cards"]],
            ["Jobs today", "Done this week", "Hours this week", "Unread messages"],
        )
        self.assertNotContains(response, "Revenue")
