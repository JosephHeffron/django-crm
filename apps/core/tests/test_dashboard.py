import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Activity, Company, Contact, Deal, Lead, Task

User = get_user_model()


class DashboardStatsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_counts_active_companies_and_contacts_only(self):
        Company.objects.create(name="Active Co", created_by=self.user, is_active=True)
        Company.objects.create(name="Inactive Co", created_by=self.user, is_active=False)
        Contact.objects.create(first_name="A", last_name="B", created_by=self.user, is_active=True)
        Contact.objects.create(first_name="C", last_name="D", created_by=self.user, is_active=False)

        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.context["company_count"], 1)
        self.assertEqual(response.context["contact_count"], 1)

    def test_open_lead_count_excludes_converted(self):
        Lead.objects.create(name="New", created_by=self.user, status=Lead.Status.NEW)
        Lead.objects.create(name="Qualified", created_by=self.user, status=Lead.Status.QUALIFIED)
        Lead.objects.create(name="Done", created_by=self.user, status=Lead.Status.CONVERTED)

        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.context["open_lead_count"], 2)

    def test_open_deal_count_and_value_exclude_closed_deals(self):
        company = Company.objects.create(name="Acme", created_by=self.user)
        Deal.objects.create(
            title="Open 1", company=company, created_by=self.user, stage="prospecting", value=1000
        )
        Deal.objects.create(
            title="Open 2", company=company, created_by=self.user, stage="proposal", value=2000
        )
        Deal.objects.create(
            title="Closed", company=company, created_by=self.user, stage="closed_won", value=5000
        )

        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.context["open_deal_count"], 2)
        self.assertEqual(response.context["open_deal_value"], 3000)

    def test_open_deal_value_is_zero_not_none_when_no_open_deals(self):
        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.context["open_deal_value"], 0)

    def test_pending_task_count_excludes_completed_and_cancelled(self):
        Task.objects.create(title="Pending", assigned_to=self.user, created_by=self.user)
        Task.objects.create(
            title="Done", assigned_to=self.user, created_by=self.user, status=Task.Status.COMPLETED
        )
        Task.objects.create(
            title="Cancelled",
            assigned_to=self.user,
            created_by=self.user,
            status=Task.Status.CANCELLED,
        )

        response = self.client.get(reverse("core:index"))
        self.assertEqual(response.context["pending_task_count"], 1)


class DashboardPipelineByStageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme", created_by=self.user)

    def test_stage_breakdown_follows_pipeline_order_not_alphabetical(self):
        # Deliberately create these out of pipeline order so an
        # alphabetical fallback (the default for .values().annotate())
        # would be caught by this test.
        Deal.objects.create(
            title="D1", company=self.company, created_by=self.user, stage="closed_won", value=100
        )
        Deal.objects.create(
            title="D2", company=self.company, created_by=self.user, stage="prospecting", value=200
        )
        response = self.client.get(reverse("core:index"))
        labels = [stage["label"] for stage in response.context["deals_by_stage"]]
        self.assertEqual(
            labels,
            [
                "Prospecting",
                "Qualification",
                "Proposal",
                "Negotiation",
                "Closed won",
                "Closed lost",
            ],
        )

    def test_stage_with_no_deals_shows_zero_count_and_value(self):
        response = self.client.get(reverse("core:index"))
        for stage in response.context["deals_by_stage"]:
            self.assertEqual(stage["count"], 0)
            self.assertEqual(stage["total_value"], 0)

    def test_stage_counts_and_values_are_correct(self):
        Deal.objects.create(
            title="D1", company=self.company, created_by=self.user, stage="proposal", value=100
        )
        Deal.objects.create(
            title="D2", company=self.company, created_by=self.user, stage="proposal", value=250
        )
        response = self.client.get(reverse("core:index"))
        proposal = next(s for s in response.context["deals_by_stage"] if s["label"] == "Proposal")
        self.assertEqual(proposal["count"], 2)
        self.assertEqual(proposal["total_value"], 350)


class DashboardMyTasksTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.other_user = User.objects.create_user("bob", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")

    def test_shows_only_my_pending_tasks(self):
        mine = Task.objects.create(title="Mine", assigned_to=self.user, created_by=self.user)
        Task.objects.create(title="Not mine", assigned_to=self.other_user, created_by=self.user)
        Task.objects.create(
            title="Mine but done",
            assigned_to=self.user,
            created_by=self.user,
            status=Task.Status.COMPLETED,
        )

        response = self.client.get(reverse("core:index"))
        tasks = list(response.context["my_tasks"])
        self.assertEqual(tasks, [mine])

    def test_overdue_task_is_marked_in_the_template(self):
        yesterday = timezone.localdate() - datetime.timedelta(days=1)
        Task.objects.create(
            title="Late task", assigned_to=self.user, created_by=self.user, due_date=yesterday
        )
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "Late task")
        self.assertContains(response, "(overdue)")

    def test_empty_state_message(self):
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "No pending tasks assigned to you")

    def test_my_tasks_capped_at_dashboard_limit(self):
        from apps.core.views import DASHBOARD_LIST_LIMIT

        for i in range(DASHBOARD_LIST_LIMIT + 5):
            Task.objects.create(title=f"Task {i}", assigned_to=self.user, created_by=self.user)
        response = self.client.get(reverse("core:index"))
        self.assertEqual(len(response.context["my_tasks"]), DASHBOARD_LIST_LIMIT)


class DashboardRecentActivityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice", password="correct-horse-battery")
        self.client.login(username="alice", password="correct-horse-battery")
        self.company = Company.objects.create(name="Acme", created_by=self.user)

    def test_shows_recent_activity(self):
        Activity.objects.create(
            activity_type=Activity.ActivityType.NOTE,
            subject="A note",
            company=self.company,
            created_by=self.user,
        )
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "A note")

    def test_empty_state_message(self):
        response = self.client.get(reverse("core:index"))
        self.assertContains(response, "No activity yet")

    def test_recent_activity_capped_at_dashboard_limit(self):
        from apps.core.views import DASHBOARD_LIST_LIMIT

        for i in range(DASHBOARD_LIST_LIMIT + 5):
            Activity.objects.create(
                activity_type=Activity.ActivityType.NOTE,
                subject=f"Note {i}",
                company=self.company,
                created_by=self.user,
            )
        response = self.client.get(reverse("core:index"))
        self.assertEqual(len(response.context["recent_activities"]), DASHBOARD_LIST_LIMIT)
