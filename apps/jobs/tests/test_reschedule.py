"""Moving a job to another time (Phase 18 unit 4).

Two ways in, one rule. The move controls on the day schedule are
ordinary form fields and work on a keyboard, with a screen reader and
with no JavaScript at all; dragging a chip on the week or month view
posts to the same endpoint. The non-drag route is the baseline, not a
fallback, which is why every test here exercises it directly.

Two invariants the module claims and these check rather than trust:
the job keeps its length, and its status and completion date are not
touched. The second matters because every count of finished work reads
`completed_at`, so a move that quietly re-opened a job would make it
vanish from the figures.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import AuditLogEntry
from apps.crm.tests._helpers import grant_role
from apps.jobs import scheduling
from apps.jobs.models import Job
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


def local(value):
    """A datetime-local field's value, as the browser sends it."""
    return timezone.localtime(value).strftime("%Y-%m-%dT%H:%M")


class RescheduleTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.start = timezone.now() + timedelta(days=2)
        self.job = f.job(self.customer, self.owner, start=self.start, hours=3, lines=[])
        f.assign(self.job, self.casey)
        self.url = reverse("jobs:job_reschedule", args=[self.job.pk])

    def move(self, when=None, nudge=None, **extra):
        data = dict(extra)
        if nudge:
            data["nudge"] = nudge
        else:
            data["start"] = local(when)
        return self.client.post(self.url, data)


class MovingTests(RescheduleTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def test_a_job_can_be_moved_to_a_chosen_time(self):
        when = self.start + timedelta(days=3)
        self.move(when)
        self.job.refresh_from_db()
        self.assertEqual(local(self.job.scheduled_start), local(when))

    def test_the_job_keeps_its_length(self):
        """A three-hour job is still three hours on Thursday.

        Only the start is asked for, which is also why a move cannot
        produce an end before a start and trip the database's own
        check.
        """
        was = self.job.scheduled_end - self.job.scheduled_start
        self.move(self.start + timedelta(days=5))
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_end - self.job.scheduled_start, was)
        self.assertEqual(was, timedelta(hours=3))

    def test_moving_leaves_the_status_and_the_finish_time_alone(self):
        """The invariant that protects every count of finished work.

        `completed_at` is what the dashboard, the monthly goal,
        Financials and a crew member's week all read. A move that
        re-opened a job would make it disappear from the figures with
        nothing on screen to say so.
        """
        self.job.status = Job.Status.COMPLETED
        self.job.completed_at = timezone.now()
        self.job.save(update_fields=["status", "completed_at"])
        was = (self.job.status, self.job.completed_at)
        self.move(self.start + timedelta(days=1))
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.completed_at), was)

    def test_the_changed_at_time_is_stamped(self):
        # auto_now only fires for fields named in update_fields.
        before = self.job.updated_at
        self.move(self.start + timedelta(days=1))
        self.job.refresh_from_db()
        self.assertGreater(self.job.updated_at, before)

    def test_moving_it_nowhere_changes_nothing(self):
        before = self.job.updated_at
        self.move(self.start)
        self.job.refresh_from_db()
        self.assertEqual(self.job.updated_at, before)

    def test_a_nonsense_time_is_refused_and_changes_nothing(self):
        was = self.job.scheduled_start
        response = self.client.post(self.url, {"start": "next tuesday-ish"}, follow=True)
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_start, was)
        self.assertIn("date and time", " ".join(str(m) for m in response.context["messages"]))

    def test_a_missing_time_is_refused(self):
        was = self.job.scheduled_start
        self.client.post(self.url, {})
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_start, was)

    def test_the_move_is_recorded_in_the_change_log(self):
        self.move(self.start + timedelta(days=1))
        entry = AuditLogEntry.objects.filter(content_type__model="job").latest("pk")
        self.assertIn("scheduled_start", entry.changes)

    def test_it_returns_to_the_page_it_was_moved_from(self):
        back = f"{reverse('jobs:calendar')}?view=week"
        response = self.move(self.start + timedelta(days=1), next=back)
        self.assertRedirects(response, back, fetch_redirect_response=False)

    def test_a_next_pointing_off_this_site_is_ignored(self):
        response = self.move(self.start + timedelta(days=1), next="https://evil.test/go")
        self.assertRedirects(response, self.job.get_absolute_url(), fetch_redirect_response=False)


class NudgeTests(RescheduleTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def test_a_job_can_be_pushed_on_a_day(self):
        self.move(nudge="+1d")
        self.job.refresh_from_db()
        self.assertEqual(local(self.job.scheduled_start), local(self.start + timedelta(days=1)))

    def test_a_job_can_be_pulled_back_a_day(self):
        self.move(nudge="-1d")
        self.job.refresh_from_db()
        self.assertEqual(local(self.job.scheduled_start), local(self.start - timedelta(days=1)))

    def test_a_job_can_be_pushed_on_a_week(self):
        self.move(nudge="+7d")
        self.job.refresh_from_db()
        self.assertEqual(local(self.job.scheduled_start), local(self.start + timedelta(days=7)))

    def test_a_nudge_keeps_the_time_of_day(self):
        self.move(nudge="+1d")
        self.job.refresh_from_db()
        self.assertEqual(
            timezone.localtime(self.job.scheduled_start).time(),
            timezone.localtime(self.start).time(),
        )

    def test_a_nudge_that_is_not_offered_is_refused(self):
        was = self.job.scheduled_start
        response = self.client.post(self.url, {"nudge": "+99y"}, follow=True)
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_start, was)
        self.assertIn("isn't a move", " ".join(str(m) for m in response.context["messages"]))

    def test_every_nudge_offered_actually_works(self):
        """The buttons and the accepted steps cannot drift apart."""
        for key, _, _ in scheduling.NUDGES:
            job = f.job(self.customer, self.owner, lines=[])
            response = self.client.post(
                reverse("jobs:job_reschedule", args=[job.pk]), {"nudge": key}
            )
            self.assertEqual(response.status_code, 302, key)
            was, after = job.scheduled_start, None
            job.refresh_from_db()
            after = job.scheduled_start
            self.assertNotEqual(was, after, key)


class AccessTests(RescheduleTestCase):
    def test_a_sales_rep_can_move_a_job(self):
        self.client.login(username="riley", password=PASSWORD)
        self.move(self.start + timedelta(days=1))
        self.job.refresh_from_db()
        self.assertNotEqual(self.job.scheduled_start, self.start)

    def test_a_crew_member_cannot_move_a_job_even_their_own(self):
        """Saying a job is done reports what happened; moving a
        customer's appointment is a different kind of decision."""
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.move(self.start + timedelta(days=1)).status_code, 403)
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_start, self.start)

    def test_a_signed_out_visitor_is_sent_to_sign_in(self):
        self.assertEqual(self.move(self.start + timedelta(days=1)).status_code, 302)

    def test_a_get_moves_nothing(self):
        self.client.login(username="boss", password=PASSWORD)
        self.assertIn(self.client.get(self.url).status_code, (403, 405))
        self.job.refresh_from_db()
        self.assertEqual(self.job.scheduled_start, self.start)


class DayScheduleTests(RescheduleTestCase):
    """The non-drag route, which is the baseline."""

    def day_page(self, user="boss"):
        self.client.login(username=user, password=PASSWORD)
        day = timezone.localtime(self.job.scheduled_start).date()
        return self.client.get(reverse("jobs:calendar"), {"view": "day", "date": str(day)})

    def test_the_day_schedule_offers_move_controls(self):
        response = self.day_page()
        self.assertContains(response, reverse("jobs:job_reschedule", args=[self.job.pk]))
        self.assertContains(response, 'name="start"')
        self.assertContains(response, 'name="nudge"')

    def test_the_box_opens_showing_when_the_job_runs(self):
        response = self.day_page()
        self.assertContains(response, f'value="{local(self.job.scheduled_start)}"')

    def test_a_crew_member_is_offered_no_move_controls(self):
        response = self.day_page(user="casey")
        self.assertNotContains(response, reverse("jobs:job_reschedule", args=[self.job.pk]))

    def test_the_controls_need_no_javascript(self):
        """They are ordinary form fields, not a script's hooks."""
        body = self.day_page().content.decode()
        self.assertIn('type="datetime-local"', body)
        self.assertNotIn("js-only", body)


class DragEnhancementTests(RescheduleTestCase):
    """Dragging is built on the same endpoint, and only for people who
    may use it."""

    def week_page(self, user="boss"):
        self.client.login(username=user, password=PASSWORD)
        day = timezone.localtime(self.job.scheduled_start).date()
        return self.client.get(reverse("jobs:calendar"), {"view": "week", "date": str(day)})

    def test_a_chip_carries_what_a_drop_needs(self):
        response = self.week_page()
        self.assertContains(response, 'draggable="true"')
        self.assertContains(response, f'data-job="{self.job.pk}"')
        self.assertContains(response, reverse("jobs:job_reschedule", args=[self.job.pk]))

    def test_the_move_url_comes_from_django_not_from_the_script(self):
        """Built in JavaScript it would work until the route changed,
        then fail silently."""
        body = self.week_page().content.decode()
        self.assertIn(f'data-move-url="{reverse("jobs:job_reschedule", args=[self.job.pk])}"', body)

    def test_the_days_are_drop_targets(self):
        self.assertContains(self.week_page(), "data-day=")

    def test_the_posting_form_carries_a_rendered_token(self):
        """No script here can read the CSRF cookie, so the token has to
        be a field the server wrote."""
        response = self.week_page()
        self.assertContains(response, "data-move-form")
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_a_crew_member_gets_no_draggable_chips(self):
        response = self.week_page(user="casey")
        self.assertNotContains(response, 'draggable="true"')
        self.assertNotContains(response, "data-move-form")

    def test_the_script_only_loads_for_people_who_may_reschedule(self):
        self.assertContains(self.week_page(), "js/reschedule.js")
        self.assertNotContains(self.week_page(user="casey"), "js/reschedule.js")
