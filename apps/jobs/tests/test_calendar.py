from datetime import date, datetime, time

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs.calendar import calendar_range
from apps.jobs.models import Job, Quote
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


def local(day, hour):
    return timezone.make_aware(datetime.combine(day, time(hour)))


class CalendarRangeTests(SimpleTestCase):
    def test_week_starts_monday_and_spans_months(self):
        cal = calendar_range("week", date(2026, 10, 1))  # a Thursday
        self.assertEqual((cal.first, cal.last), (date(2026, 9, 28), date(2026, 10, 4)))
        self.assertEqual((cal.previous, cal.next), (date(2026, 9, 21), date(2026, 10, 5)))
        self.assertEqual(cal.title, "Sep 28 – Oct 4, 2026")

    def test_month_covers_whole_weeks(self):
        cal = calendar_range("month", date(2026, 2, 14))
        self.assertEqual((cal.first, cal.last), (date(2026, 1, 26), date(2026, 3, 1)))
        self.assertEqual((cal.first.weekday(), cal.last.weekday()), (0, 6))
        self.assertEqual((cal.previous, cal.next), (date(2026, 1, 1), date(2026, 3, 1)))
        self.assertEqual(cal.title, "February 2026")

    def test_month_rolls_over_the_year(self):
        cal = calendar_range("month", date(2026, 1, 31))
        self.assertEqual((cal.previous, cal.next), (date(2025, 12, 1), date(2026, 2, 1)))

    def test_day(self):
        cal = calendar_range("day", date(2026, 9, 29))
        self.assertEqual(
            (cal.first, cal.last, cal.title),
            (cal.anchor, cal.anchor, "Tuesday, September 29, 2026"),
        )


class CalendarViewTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("rep"), Role.SALES_REP)
        self.crew = grant_role(f.user("crew", first_name="Casey"), Role.CLEANER)
        self.other_crew = grant_role(f.user("crew2", first_name="Jordan"), Role.CLEANER)
        self.customer = f.contact(self.owner, "Pat", "Gutters")
        self.day = date(2026, 10, 1)
        self.mine = f.job(self.customer, self.owner, start=local(self.day, 9))
        f.assign(self.mine, self.crew)
        self.theirs = f.job(self.customer, self.owner, start=local(self.day, 13))
        f.assign(self.theirs, self.other_crew)
        f.job(self.customer, self.owner, start=local(self.day, 15), status=Job.Status.CANCELLED)
        self.visit = f.quote(
            self.customer, self.rep, status=Quote.Status.SENT, site_visit_at=local(self.day, 16)
        )

    def events(self, username, **params):
        self.client.login(username=username, password=PASSWORD)
        response = self.client.get(
            reverse("jobs:calendar"), {"view": "day", "date": self.day.isoformat(), **params}
        )
        self.assertEqual(response.status_code, 200)
        return [(e.kind, e.url) for e in response.context["days"][0]["events"]]

    def test_sales_roles_see_all_jobs_and_site_visits_in_time_order(self):
        expected = [
            ("job", self.mine.get_absolute_url()),
            ("job", self.theirs.get_absolute_url()),
            ("visit", self.visit.get_absolute_url()),
        ]
        self.assertEqual(self.events("rep"), expected)
        self.assertEqual(self.events("boss"), expected)

    def test_cleaner_sees_only_their_own_jobs(self):
        self.assertEqual(self.events("crew"), [("job", self.mine.get_absolute_url())])

    def test_crew_filter_narrows_jobs_and_drops_visits(self):
        self.assertEqual(
            self.events("rep", crew=self.other_crew.pk), [("job", self.theirs.get_absolute_url())]
        )

    def test_a_cleaner_cannot_use_the_crew_filter_to_see_others(self):
        self.assertEqual(
            self.events("crew", crew=self.other_crew.pk), [("job", self.mine.get_absolute_url())]
        )

    def test_week_and_month_views_render(self):
        self.client.login(username="rep", password=PASSWORD)
        for view, count in (("week", 7), ("month", 35)):
            response = self.client.get(
                reverse("jobs:calendar"), {"view": view, "date": self.day.isoformat()}
            )
            self.assertEqual(len(response.context["days"]), count, view)
            self.assertContains(response, "Pat Gutters")

    def test_bad_parameters_fall_back_to_this_week(self):
        self.client.login(username="rep", password=PASSWORD)
        for params in ({"view": "year"}, {"date": "2026-02-30"}, {"date": "soon"}, {"crew": "x"}):
            response = self.client.get(reverse("jobs:calendar"), params)
            self.assertEqual(response.status_code, 200, params)
            self.assertEqual(response.context["cal"].view, "week")
