from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs import crew
from apps.jobs.models import Job, JobAssignment, TimeEntry
from apps.users.models import UserProfile, get_profile
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"
CLOCK = reverse("jobs:time_clock")
ASSIGNMENTS = reverse("jobs:assignments")
PAYROLL = reverse("jobs:payroll")
PERFORMANCE = reverse("jobs:performance")


class CrewTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.casey = grant_role(
            f.user("casey", first_name="Casey", last_name="Brooks"), Role.CLEANER
        )
        self.customer = f.contact(self.owner)
        self.now = timezone.now()
        self.client.login(username="casey", password=PASSWORD)

    def clock_in(self, **extra):
        data = {"action": "in"}
        data.update(extra)
        return self.client.post(CLOCK, data)

    def clock_out(self):
        return self.client.post(CLOCK, {"action": "out"})


class TimeClockTests(CrewTestCase):
    def test_everyone_with_a_role_has_a_clock(self):
        for username, role in (("rep", Role.SALES_REP), ("boss2", Role.OWNER)):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(self.client.get(CLOCK).status_code, 200)

    def test_someone_with_no_role_has_none(self):
        f.user("nobody")
        self.client.login(username="nobody", password=PASSWORD)
        self.assertEqual(self.client.get(CLOCK).status_code, 403)

    def test_clocking_in_and_out(self):
        self.clock_in()
        entry = TimeEntry.objects.get()
        self.assertTrue(entry.is_running)
        self.assertIsNone(entry.hours)
        self.assertContains(self.client.get(CLOCK), "On the clock")

        self.clock_out()
        entry.refresh_from_db()
        self.assertFalse(entry.is_running)
        self.assertIsNotNone(entry.hours)

    def test_clocking_in_twice_is_refused_kindly(self):
        self.clock_in()
        response = self.clock_in()
        self.assertEqual(TimeEntry.objects.count(), 1)
        self.assertContains(response.wsgi_request and self.client.get(CLOCK), "On the clock")

    def test_clocking_out_when_you_never_clocked_in(self):
        response = self.clock_out()
        self.assertRedirects(response, CLOCK)
        self.assertFalse(TimeEntry.objects.exists())

    def test_hours_on_a_job_go_onto_that_job(self):
        job = f.job(self.customer, self.owner, lines=[])
        started = self.now - timedelta(hours=3)
        crew.clock_in(self.casey, job=job, now=started)
        crew.clock_out(self.casey, now=started + timedelta(hours=2, minutes=30))
        assignment = JobAssignment.objects.get(job=job, user=self.casey)
        self.assertEqual(assignment.hours_worked, Decimal("2.50"))

    def test_hours_add_to_what_is_already_logged(self):
        job = f.job(self.customer, self.owner, lines=[])
        f.assign(job, self.casey, hours=Decimal("1.00"))
        started = self.now - timedelta(hours=2)
        crew.clock_in(self.casey, job=job, now=started)
        crew.clock_out(self.casey, now=started + timedelta(hours=1))
        self.assertEqual(
            JobAssignment.objects.get(job=job, user=self.casey).hours_worked, Decimal("2.00")
        )

    def test_time_with_no_job_is_still_recorded(self):
        started = self.now - timedelta(hours=1)
        crew.clock_in(self.casey, now=started)
        entry, error = crew.clock_out(self.casey, now=started + timedelta(minutes=45))
        self.assertIsNone(error)
        self.assertEqual(entry.hours, Decimal("0.75"))
        self.assertFalse(JobAssignment.objects.exists())

    def test_you_only_ever_see_your_own_time(self):
        other = grant_role(f.user("alex"), Role.CLEANER)
        started = self.now - timedelta(hours=2)
        crew.clock_in(other, now=started)
        crew.clock_out(other, now=started + timedelta(hours=1))
        response = self.client.get(CLOCK)
        self.assertEqual(list(response.context["week_entries"]), [])
        self.assertEqual(response.context["week_hours"], Decimal("0.00"))

    def test_a_job_you_are_not_on_assigns_you_to_it(self):
        # You clocked onto it, so you did the work.
        job = f.job(self.customer, self.owner, lines=[])
        started = self.now - timedelta(hours=1)
        crew.clock_in(self.casey, job=job, now=started)
        crew.clock_out(self.casey, now=started + timedelta(hours=1))
        self.assertTrue(JobAssignment.objects.filter(job=job, user=self.casey).exists())

    def test_two_taps_in_the_same_instant_start_one_clock(self):
        # The guard and the constraint can both be true at once on a
        # phone; the second must get the same answer, not a crash.
        crew.clock_in(self.casey)
        TimeEntry.objects.filter(user=self.casey).update(ended_at=None)
        entry, error = crew.clock_in(self.casey)
        self.assertIsNone(entry)
        self.assertIn("already clocked in", error)
        self.assertEqual(TimeEntry.objects.filter(user=self.casey).count(), 1)

    def test_an_end_before_the_start_is_refused(self):
        crew.clock_in(self.casey, now=self.now)
        entry, error = crew.clock_out(self.casey, now=self.now - timedelta(hours=1))
        self.assertIsNone(entry)
        self.assertIn("before it started", error)
        self.assertTrue(TimeEntry.objects.get().is_running)


class PayrollTests(CrewTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)
        profile = get_profile(self.casey)
        profile.hourly_rate = Decimal("22.50")
        profile.save(update_fields=["hourly_rate"])

    def log(self, user, hours, days_ago=0):
        started = timezone.now() - timedelta(days=days_ago, hours=hours)
        crew.clock_in(user, now=started)
        crew.clock_out(user, now=started + timedelta(hours=hours))

    def test_only_the_owner_sees_payroll(self):
        for username, role in (("rep", Role.SALES_REP), ("crew2", Role.CLEANER)):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            self.assertEqual(self.client.get(PAYROLL).status_code, 403)

    def test_pay_is_hours_times_the_rate(self):
        self.log(self.casey, 4)
        row = next(r for r in self.client.get(PAYROLL).context["rows"] if r["person"] == self.casey)
        self.assertEqual(row["hours"], Decimal("4.00"))
        self.assertEqual(row["rate"], Decimal("22.50"))
        self.assertEqual(row["pay"], Decimal("90.00"))

    def test_someone_with_no_rate_is_listed_and_flagged(self):
        other = grant_role(f.user("alex", first_name="Alex"), Role.CLEANER)
        self.log(other, 3)
        response = self.client.get(PAYROLL)
        row = next(r for r in response.context["rows"] if r["person"] == other)
        self.assertEqual(row["hours"], Decimal("3.00"))
        self.assertIsNone(row["pay"])
        self.assertIn(other, response.context["missing_rates"])
        self.assertContains(response, "No hourly rate set")

    def test_the_total_only_counts_what_can_be_worked_out(self):
        other = grant_role(f.user("alex"), Role.CLEANER)
        self.log(self.casey, 4)
        self.log(other, 3)
        self.assertEqual(self.client.get(PAYROLL).context["total"], Decimal("90.00"))

    def test_time_outside_the_period_is_not_paid(self):
        self.log(self.casey, 4, days_ago=90)
        response = self.client.get(PAYROLL, {"range": "week"})
        row = next(r for r in response.context["rows"] if r["person"] == self.casey)
        self.assertEqual(row["hours"], Decimal("0.00"))

    def test_a_running_clock_is_not_paid_yet(self):
        crew.clock_in(self.casey)
        row = next(r for r in self.client.get(PAYROLL).context["rows"] if r["person"] == self.casey)
        self.assertEqual(row["hours"], Decimal("0.00"))

    def test_the_owner_sets_a_rate_and_working_days(self):
        response = self.client.post(
            reverse("people:member", args=["casey"]),
            {"hourly_rate": "25.00", "working_days": ["0", "1", "2", "3", "4"]},
        )
        self.assertRedirects(response, reverse("people:member", args=["casey"]))
        profile = get_profile(self.casey)
        self.assertEqual(profile.hourly_rate, Decimal("25.00"))
        self.assertEqual(profile.working_days, "01234")
        self.assertEqual(profile.working_days_display, "Mon, Tue, Wed, Thu, Fri")

    def test_nobody_else_can_set_a_rate(self):
        grant_role(f.user("rep"), Role.SALES_REP)
        self.client.login(username="rep", password=PASSWORD)
        response = self.client.post(
            reverse("people:member", args=["casey"]), {"hourly_rate": "999"}
        )
        self.assertEqual(response.status_code, 403)
        # Unchanged, not merely absent: setUp already gave them a rate.
        self.assertEqual(get_profile(self.casey).hourly_rate, Decimal("22.50"))


class AssignmentsTests(CrewTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)
        self.monday = crew.week_bounds(timezone.localdate())[0]

    def at(self, day_offset, hour=9):
        day = self.monday + timedelta(days=day_offset)
        return timezone.make_aware(
            timezone.datetime.combine(day, timezone.datetime.min.time().replace(hour=hour))
        )

    def test_a_cleaner_cannot_see_the_whole_crews_week(self):
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(ASSIGNMENTS).status_code, 403)

    def test_each_person_gets_their_own_week(self):
        job = f.job(self.customer, self.owner, start=self.at(1), lines=[])
        f.assign(job, self.casey)
        row = next(
            r for r in self.client.get(ASSIGNMENTS).context["rows"] if r["person"] == self.casey
        )
        self.assertEqual([a.job for a in row["assignments"]], [job])

    def test_jobs_with_nobody_on_them_are_called_out(self):
        job = f.job(self.customer, self.owner, start=self.at(2), lines=[])
        response = self.client.get(ASSIGNMENTS)
        self.assertEqual(list(response.context["unassigned"]), [job])
        self.assertContains(response, "with nobody on")

    def test_a_job_on_someones_day_off_is_flagged(self):
        profile = get_profile(self.casey)
        profile.working_days = "01234"  # weekdays only
        profile.save(update_fields=["working_days"])
        saturday = f.job(self.customer, self.owner, start=self.at(5), lines=[])
        f.assign(saturday, self.casey)
        row = next(
            r for r in self.client.get(ASSIGNMENTS).context["rows"] if r["person"] == self.casey
        )
        self.assertEqual([a.job for a in row["off_days"]], [saturday])

    def test_with_no_working_days_set_nothing_is_flagged(self):
        job = f.job(self.customer, self.owner, start=self.at(6), lines=[])
        f.assign(job, self.casey)
        row = next(
            r for r in self.client.get(ASSIGNMENTS).context["rows"] if r["person"] == self.casey
        )
        self.assertEqual(row["off_days"], [])


class ProfileReadingTests(CrewTestCase):
    """Listing people must not write rows for them — the rule the app
    shell already follows when it reads a saved theme."""

    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def pages(self):
        return (ASSIGNMENTS, PAYROLL, PERFORMANCE, reverse("people:member", args=["casey"]))

    def test_opening_a_page_creates_no_profiles(self):
        UserProfile.objects.all().delete()
        for page in self.pages():
            self.assertEqual(self.client.get(page).status_code, 200, page)
            self.assertFalse(UserProfile.objects.exists(), page)

    def test_someone_without_a_profile_still_appears(self):
        UserProfile.objects.all().delete()
        row = next(r for r in self.client.get(PAYROLL).context["rows"] if r["person"] == self.casey)
        self.assertIsNone(row["rate"])
        self.assertEqual(row["hours"], Decimal("0.00"))


class PerformanceTests(CrewTestCase):
    def setUp(self):
        super().setUp()
        self.client.login(username="boss", password=PASSWORD)

    def test_only_the_owner_sees_performance(self):
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(PERFORMANCE).status_code, 403)

    def test_finished_work_hours_and_rating(self):
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("400"))])
        job.status = Job.Status.COMPLETED
        job.completed_at = timezone.now()
        job.customer_rating = 5
        job.save(update_fields=["status", "completed_at", "customer_rating"])
        f.assign(job, self.casey)
        started = timezone.now() - timedelta(hours=4)
        crew.clock_in(self.casey, now=started)
        crew.clock_out(self.casey, now=started + timedelta(hours=4))

        row = next(
            r for r in self.client.get(PERFORMANCE).context["rows"] if r["person"] == self.casey
        )
        self.assertEqual((row["jobs"], row["hours"]), (1, Decimal("4.00")))
        self.assertEqual(row["value"], Decimal("400.00"))
        self.assertEqual(row["per_hour"], Decimal("100.00"))
        self.assertEqual(row["rating"], 5)

    def test_without_hours_there_is_no_rate_per_hour(self):
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("400"))])
        job.status = Job.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        f.assign(job, self.casey)
        row = next(
            r for r in self.client.get(PERFORMANCE).context["rows"] if r["person"] == self.casey
        )
        self.assertIsNone(row["per_hour"])
        self.assertContains(self.client.get(PERFORMANCE), "—")
