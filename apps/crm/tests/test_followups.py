from datetime import date, timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.followups import add_months, due_follow_ups, generate_follow_ups
from apps.crm.models import Activity, Contact, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

TODAY = date(2026, 9, 29)


def _completed_job(contact, owner, days_ago, service_slug="gutter-cleaning"):
    """A completed job `days_ago` before TODAY (gutters: 6-month interval)."""
    start = timezone.make_aware(
        timezone.datetime.combine(TODAY - timedelta(days=days_ago), timezone.datetime.min.time())
    ) + timedelta(hours=9)
    job = f.job(
        contact,
        owner,
        start=start,
        primary_service_type=f.service(service_slug),
        status=Job.Status.COMPLETED,
    )
    Job.objects.filter(pk=job.pk).update(completed_at=job.scheduled_end)
    return job


class AddMonthsTests(TestCase):
    def test_clamps_to_month_end_and_rolls_the_year(self):
        self.assertEqual(add_months(date(2026, 8, 31), 6), date(2027, 2, 28))
        self.assertEqual(add_months(date(2027, 8, 31), 6), date(2028, 2, 29))
        self.assertEqual(add_months(date(2026, 12, 15), 1), date(2027, 1, 15))
        self.assertEqual(add_months(date(2026, 1, 31), 12), date(2027, 1, 31))


class GenerateFollowUpsTests(TestCase):
    def setUp(self):
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.customer = f.contact(self.rep, owner=self.rep)

    def test_due_after_the_service_interval_not_before(self):
        _completed_job(self.customer, self.rep, days_ago=150)  # < 6 months
        self.assertEqual(generate_follow_ups(TODAY), [])
        _completed_job(self.customer, self.rep, days_ago=400)  # latest still 150 days ago
        self.assertEqual(generate_follow_ups(TODAY), [])

        other = f.contact(self.rep, "Due", "Customer", owner=self.rep)
        _completed_job(other, self.rep, days_ago=200)  # > 6 months
        (task,) = generate_follow_ups(TODAY)
        self.assertEqual(
            (task.kind, task.contact, task.assigned_to), ("follow_up", other, self.rep)
        )
        self.assertEqual(task.service_type.slug, "gutter-cleaning")
        self.assertEqual(task.due_date, TODAY)

    def test_idempotent(self):
        _completed_job(self.customer, self.rep, days_ago=200)
        self.assertEqual(len(generate_follow_ups(TODAY)), 1)
        self.assertEqual(generate_follow_ups(TODAY), [])
        self.assertEqual(Task.objects.filter(kind=Task.Kind.FOLLOW_UP).count(), 1)

    def test_a_recent_contact_touch_resets_the_clock(self):
        _completed_job(self.customer, self.rep, days_ago=200)
        touch = Activity.objects.create(
            activity_type="call", subject="Checked in", contact=self.customer, created_by=self.rep
        )
        Activity.objects.filter(pk=touch.pk).update(
            created_at=timezone.now() - timedelta(days=(timezone.localdate() - TODAY).days + 30)
        )
        self.assertEqual(generate_follow_ups(TODAY), [])

    def test_dismissed_follow_up_is_not_recreated_until_new_work(self):
        _completed_job(self.customer, self.rep, days_ago=200)
        (task,) = generate_follow_ups(TODAY)
        Task.objects.filter(pk=task.pk).update(status=Task.Status.CANCELLED)
        self.assertEqual(generate_follow_ups(TODAY), [])
        self.assertEqual(generate_follow_ups(TODAY + timedelta(days=60)), [])

    def test_skips_leads_inactive_customers_and_services_without_an_interval(self):
        lead = f.contact(self.rep, "A", "Lead", status=Contact.Status.LEAD, owner=self.rep)
        gone = f.contact(self.rep, "Gone", "Away", is_active=False, owner=self.rep)
        _completed_job(lead, self.rep, days_ago=400)
        _completed_job(gone, self.rep, days_ago=400)
        _completed_job(self.customer, self.rep, days_ago=900, service_slug="tree-removal")
        self.assertEqual(due_follow_ups(TODAY), [])

    def test_unowned_contact_falls_back_to_an_owner(self):
        boss = grant_role(f.user("boss"), Role.OWNER)
        orphan = f.contact(self.rep, "No", "Owner")
        _completed_job(orphan, self.rep, days_ago=200)
        (task,) = generate_follow_ups(TODAY)
        self.assertEqual(task.assigned_to, boss)

    def test_contact_ids_limits_generation(self):
        other = f.contact(self.rep, "Other", "One", owner=self.rep)
        _completed_job(self.customer, self.rep, days_ago=200)
        _completed_job(other, self.rep, days_ago=200)
        (task,) = generate_follow_ups(TODAY, contact_ids=[other.pk])
        self.assertEqual(task.contact, other)


class CompletingAFollowUpTests(TestCase):
    """Completion must log the contact touch — otherwise the next
    generator run would recreate the follow-up immediately."""

    def setUp(self):
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password="correct-horse-battery")
        self.customer = f.contact(self.rep, owner=self.rep)
        _completed_job(self.customer, self.rep, days_ago=200)
        (self.task,) = generate_follow_ups(TODAY)

    def test_one_click_complete_logs_a_touch_and_stops_regeneration(self):
        self.client.post(reverse("crm:task_complete", args=[self.task.pk]))
        self.task.refresh_from_db()
        self.assertEqual((self.task.status, self.task.completed_by), ("completed", self.rep))
        touch = Activity.objects.get(contact=self.customer)
        self.assertEqual(touch.activity_type, Activity.ActivityType.FOLLOW_UP)
        self.assertEqual(touch.subject, "Checked in about gutter cleaning")
        self.assertEqual(generate_follow_ups(timezone.localdate()), [])

    def test_edit_form_completion_logs_once_and_reopening_clears_completed_by(self):
        url = reverse("crm:task_update", args=[self.task.pk])
        data = {
            "title": self.task.title,
            "assigned_to": self.rep.pk,
            "contact": self.customer.pk,
            "priority": "medium",
            "status": "completed",
        }
        self.client.post(url, data)
        self.client.post(url, data)  # re-saving a completed task
        self.assertEqual(Activity.objects.filter(contact=self.customer).count(), 1)

        self.client.post(url, {**data, "status": "pending"})
        self.task.refresh_from_db()
        self.assertIsNone(self.task.completed_by)
        self.assertIsNone(self.task.completed_at)

    def test_clearing_a_follow_ups_customer_is_a_form_error_not_a_500(self):
        response = self.client.post(
            reverse("crm:task_update", args=[self.task.pk]),
            {"title": "x", "assigned_to": self.rep.pk, "priority": "medium", "status": "pending"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A follow-up needs its customer.")
        self.task.refresh_from_db()
        self.assertEqual(self.task.contact, self.customer)

    def test_general_tasks_log_no_touch(self):
        general = Task.objects.create(
            title="Order supplies", contact=self.customer, assigned_to=self.rep, created_by=self.rep
        )
        self.client.post(reverse("crm:task_complete", args=[general.pk]))
        self.assertFalse(Activity.objects.filter(contact=self.customer).exists())


class GenerateFollowUpsCommandTests(TestCase):
    def test_reports_what_it_created(self):
        rep = grant_role(f.user("rep"), Role.SALES_REP)
        _completed_job(f.contact(rep, owner=rep), rep, days_ago=200)
        out = StringIO()
        call_command("generate_followups", "--date", TODAY.isoformat(), stdout=out)
        self.assertIn("Created 1 follow-up task(s) for 2026-09-29.", out.getvalue())

    def test_rejects_a_bad_date(self):
        with self.assertRaises(CommandError):
            call_command("generate_followups", "--date", "tomorrow", stdout=StringIO())
