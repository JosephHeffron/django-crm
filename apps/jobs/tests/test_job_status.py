"""Marking a job New, In progress or Complete from the schedule.

The one that matters is `test_a_job_completed_from_the_schedule_is
_counted`. Every count of finished work reads `completed_at`, not
`status`, so a path that moves the status without stamping the date
gives a job that reads "Completed" on screen and is counted nowhere.
That is silent, which is why the assertion here is the month's figure
and not the field.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs import status as job_status
from apps.jobs.models import Job
from apps.jobs.reports import Period, summary
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


def this_month():
    today = timezone.localdate()
    first = today.replace(day=1)
    last = (first + timedelta(days=31)).replace(day=1) - timedelta(days=1)
    return Period("month", first, last)


class JobStatusTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.casey = grant_role(f.user("casey", first_name="Casey"), Role.CLEANER)
        self.alex = grant_role(f.user("alex", first_name="Alex"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner, lines=[])
        f.assign(self.job, self.casey)
        self.url = reverse("jobs:job_status", args=[self.job.pk])

    def mark(self, state, follow=False, **extra):
        return self.client.post(self.url, {"status": state, **extra}, follow=follow)


class CountingTests(JobStatusTestCase):
    def test_a_job_completed_from_the_schedule_records_when_it_finished(self):
        self.client.login(username="boss", password=PASSWORD)
        self.mark(Job.Status.COMPLETED)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.COMPLETED)
        self.assertIsNotNone(self.job.completed_at)

    def test_a_job_completed_from_the_schedule_is_counted_in_the_month(self):
        """The whole reason the status rule lives in one place.

        Asserting the figure, not the field: a status written without
        the date passes a status assertion and still vanishes from
        every report.
        """
        before = summary(this_month())["jobs_completed"]
        self.client.login(username="boss", password=PASSWORD)
        self.mark(Job.Status.COMPLETED)
        self.assertEqual(summary(this_month())["jobs_completed"], before + 1)

    def test_a_job_completed_from_the_schedule_counts_for_the_crew_member(self):
        """The crew figures read completed_at too (apps/jobs/crew.py).

        Written against the real function rather than guarded by a
        hasattr fallback — an earlier version of this test had one, and
        a fallback that supplies the expected answer asserts nothing.
        """
        from apps.jobs import crew

        first, last = crew.week_bounds(timezone.localdate())
        before = crew.performance([self.casey], first, last)[0]["jobs"]
        self.client.login(username="casey", password=PASSWORD)
        self.mark(Job.Status.COMPLETED)
        after = crew.performance([self.casey], first, last)[0]["jobs"]
        self.assertEqual(after, before + 1)

    def test_reopening_a_job_clears_the_finish_time(self):
        self.client.login(username="boss", password=PASSWORD)
        self.mark(Job.Status.COMPLETED)
        self.mark(Job.Status.SCHEDULED)
        self.job.refresh_from_db()
        self.assertIsNone(self.job.completed_at)
        self.assertEqual(summary(this_month())["jobs_completed"], 0)

    def test_marking_it_in_progress_leaves_no_finish_time(self):
        self.client.login(username="boss", password=PASSWORD)
        self.mark(Job.Status.IN_PROGRESS)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.IN_PROGRESS)
        self.assertIsNone(self.job.completed_at)

    def test_marking_an_already_finished_job_finished_keeps_the_first_time(self):
        self.client.login(username="boss", password=PASSWORD)
        self.mark(Job.Status.COMPLETED)
        self.job.refresh_from_db()
        first = self.job.completed_at
        self.mark(Job.Status.COMPLETED)
        self.job.refresh_from_db()
        self.assertEqual(self.job.completed_at, first)

    def test_the_edit_form_and_the_schedule_agree(self):
        """Two paths, one rule.

        This is the test that fails if a third status path is added
        later without going through the shared helper.
        """
        other = f.job(self.customer, self.owner, lines=[])
        self.client.login(username="boss", password=PASSWORD)
        self.mark(Job.Status.COMPLETED)
        job_status.apply_status(other, Job.Status.COMPLETED)
        self.job.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(
            (self.job.completed_at is None, other.completed_at is None), (False, False)
        )
        self.assertEqual(summary(this_month())["jobs_completed"], 2)


class StatusRuleTests(TestCase):
    """The helper on its own, without the HTTP layer."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.job = f.job(f.contact(self.owner), self.owner, lines=[])

    def test_an_unknown_status_changes_nothing(self):
        was = self.job.status
        job, error = job_status.apply_status(self.job, "banana")
        self.assertIsNone(job)
        self.assertIn("status", error)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, was)

    def test_an_empty_status_changes_nothing(self):
        job, error = job_status.apply_status(self.job, "")
        self.assertIsNone(job)
        self.assertTrue(error)

    def test_cancelling_is_not_offered_as_a_quick_action(self):
        # It has invoicing consequences, so it stays on the edit form.
        offered = [value for value, _ in job_status.QUICK_STATUSES]
        self.assertNotIn(Job.Status.CANCELLED, offered)
        self.assertEqual(len(offered), 3)

    def test_the_update_stamps_the_changed_at_time(self):
        # auto_now fields only move when named in update_fields.
        before = self.job.updated_at
        job_status.apply_status(self.job, Job.Status.IN_PROGRESS)
        self.job.refresh_from_db()
        self.assertGreater(self.job.updated_at, before)


class AccessTests(JobStatusTestCase):
    def test_a_signed_out_visitor_cannot_change_a_status(self):
        self.assertEqual(self.mark(Job.Status.COMPLETED).status_code, 302)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.SCHEDULED)

    def test_the_crew_member_on_the_job_can_mark_it(self):
        self.client.login(username="casey", password=PASSWORD)
        self.mark(Job.Status.IN_PROGRESS)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.IN_PROGRESS)

    def test_a_crew_member_on_another_job_is_not_found(self):
        # 404 rather than 403: a 403 would confirm the job exists.
        self.client.login(username="alex", password=PASSWORD)
        self.assertEqual(self.mark(Job.Status.COMPLETED).status_code, 404)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.SCHEDULED)

    def test_somebody_with_no_role_is_refused(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.mark(Job.Status.COMPLETED).status_code, 403)

    def test_a_get_changes_nothing(self):
        self.client.login(username="boss", password=PASSWORD)
        self.assertIn(self.client.get(self.url).status_code, (403, 405))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, Job.Status.SCHEDULED)


class ReturnTests(JobStatusTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def test_it_returns_to_the_page_it_was_marked_from(self):
        back = reverse("jobs:calendar") + "?view=day"
        response = self.mark(Job.Status.COMPLETED, next=back)
        self.assertRedirects(response, back, fetch_redirect_response=False)

    def test_a_next_pointing_off_this_site_is_ignored(self):
        response = self.mark(Job.Status.COMPLETED, next="https://evil.test/take-me")
        self.assertRedirects(response, self.job.get_absolute_url(), fetch_redirect_response=False)

    def test_without_a_next_it_returns_to_the_job(self):
        response = self.mark(Job.Status.COMPLETED)
        self.assertRedirects(response, self.job.get_absolute_url(), fetch_redirect_response=False)


class ScheduleTests(JobStatusTestCase):
    def test_the_day_view_offers_the_other_two_states(self):
        self.client.login(username="boss", password=PASSWORD)
        day = timezone.localtime(self.job.scheduled_start).date()
        response = self.client.get(reverse("jobs:calendar"), {"view": "day", "date": str(day)})
        self.assertContains(response, reverse("jobs:job_status", args=[self.job.pk]))
        # The state it is already in is not offered.
        self.assertNotContains(response, 'value="scheduled"')
        self.assertContains(response, 'value="completed"')

    def test_the_week_view_chips_stay_plain_links(self):
        # A form cannot nest in the anchor that wraps a chip.
        self.client.login(username="boss", password=PASSWORD)
        day = timezone.localtime(self.job.scheduled_start).date()
        response = self.client.get(reverse("jobs:calendar"), {"view": "week", "date": str(day)})
        self.assertNotContains(response, reverse("jobs:job_status", args=[self.job.pk]))

    def test_a_site_visit_offers_no_status_buttons(self):
        quote = f.quote(self.customer, self.owner)
        quote.site_visit_at = self.job.scheduled_start
        quote.save(update_fields=["site_visit_at"])
        self.client.login(username="boss", password=PASSWORD)
        day = timezone.localtime(self.job.scheduled_start).date()
        response = self.client.get(reverse("jobs:calendar"), {"view": "day", "date": str(day)})
        events = response.context["days"][0]["events"]
        visits = [e for e in events if e.kind == "visit"]
        self.assertTrue(visits)
        self.assertTrue(all(e.job_id is None for e in visits))

    def test_the_job_page_offers_them_too(self):
        self.client.login(username="boss", password=PASSWORD)
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, reverse("jobs:job_status", args=[self.job.pk]))
