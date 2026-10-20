from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs.calendar import Event, calendar_range, day_slots
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


def event(start, end=None, kind="job"):
    """The least an Event needs to be placed on a slot grid."""
    return Event(
        kind=kind,
        start=start,
        end=end,
        title="Gutter cleaning",
        subtitle="Pat Gutters",
        url="/jobs/1/",
        tone_class="tone-1",
    )


@override_settings(TIME_ZONE="America/New_York")
class DaySlotTests(SimpleTestCase):
    """The grid of times you can click on the day schedule.

    Pinned to the business's default zone. `CRM_TIME_ZONE` is
    configurable, and two of these build a New York instant and assert
    a wall-clock label, so they would fail under another setting even
    though the code reads the configured zone correctly — Sourcery's
    catch on PR #166. Pinning is right rather than deriving the
    expectations: a clock whose labels are computed from the same code
    under test asserts very little.
    """

    day = date(2026, 10, 1)

    def labels(self, slots):
        return [slot["label"] for slot in slots]

    def busy(self, slots):
        return [slot["label"] for slot in slots if slot["busy"]]

    def test_an_empty_day_runs_six_to_eight_in_half_hours(self):
        slots = day_slots(self.day, [])
        self.assertEqual(len(slots), 28)
        self.assertEqual(self.labels(slots)[:3], ["6:00 AM", "6:30 AM", "7:00 AM"])
        self.assertEqual(self.labels(slots)[-1], "7:30 PM")

    def test_each_slot_carries_the_value_the_job_form_wants(self):
        first = day_slots(self.day, [])[0]
        self.assertEqual(first["value"], "2026-10-01T06:00")

    def test_nothing_is_busy_on_an_empty_day(self):
        self.assertEqual(self.busy(day_slots(self.day, [])), [])

    def test_a_job_marks_every_slot_it_covers(self):
        slots = day_slots(self.day, [event(local(self.day, 9), local(self.day, 11))])
        self.assertEqual(self.busy(slots), ["9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM"])

    def test_a_job_ending_on_the_hour_does_not_take_the_next_slot(self):
        """Half-open at both ends, and this is the assertion for it.

        With `<=` anywhere in the overlap test, a job ending at
        exactly 11:00 marks the 11:00 slot too, and every
        back-to-back booking paints an extra half hour. The rendered
        page looks plausible either way, which is why this needs its
        own test rather than an eyeball.
        """
        slots = day_slots(self.day, [event(local(self.day, 9), local(self.day, 11))])
        self.assertNotIn("11:00 AM", self.busy(slots))

    def test_a_job_inside_one_slot_marks_only_that_slot(self):
        start = timezone.make_aware(datetime.combine(self.day, time(9, 10)))
        slots = day_slots(self.day, [event(start, start + timedelta(minutes=5))])
        self.assertEqual(self.busy(slots), ["9:00 AM"])

    def test_a_site_visit_with_no_end_holds_one_slot(self):
        """`Event.end` is None for a quote's site visit. Left as None
        it reads as free, and the grid offers a time the rep is
        already driving to."""
        slots = day_slots(self.day, [event(local(self.day, 14), None, kind="visit")])
        self.assertEqual(self.busy(slots), ["2:00 PM"])

    def test_a_site_visit_off_the_half_hour_still_holds_one_slot(self):
        """The version of the test above that actually checks the
        claim. Sourcery's catch on PR #166: a visit at 2:10 plus half
        an hour runs to 2:40 and marked the 2:30 slot too, so the
        grid said two slots while the docstring said one. A visit on
        the boundary — the only case the first test used — agrees with
        either implementation.
        """
        at_ten_past = timezone.make_aware(datetime.combine(self.day, time(14, 10)))
        slots = day_slots(self.day, [event(at_ten_past, None, kind="visit")])
        self.assertEqual(self.busy(slots), ["2:00 PM"])

    def test_the_window_widens_for_an_early_start(self):
        """6am is a floor, not the window. The agenda above lists a
        5:30 job, so a grid showing 6am as the start of the day would
        contradict the same page."""
        slots = day_slots(
            self.day,
            [
                event(
                    timezone.make_aware(datetime.combine(self.day, time(5, 30))), local(self.day, 7)
                )
            ],
        )
        self.assertEqual(self.labels(slots)[0], "5:30 AM")
        self.assertEqual(self.busy(slots)[:2], ["5:30 AM", "6:00 AM"])

    def test_the_window_widens_for_a_late_finish(self):
        slots = day_slots(self.day, [event(local(self.day, 19), local(self.day, 21))])
        self.assertEqual(self.labels(slots)[-1], "8:30 PM")

    def test_an_odd_start_time_is_floored_onto_the_grid(self):
        """Half past, not twenty-three minutes past: the grid stays on
        half-hour boundaries whatever time the job starts."""
        start = timezone.make_aware(datetime.combine(self.day, time(5, 23)))
        slots = day_slots(self.day, [event(start, local(self.day, 7))])
        self.assertEqual(self.labels(slots)[0], "5:00 AM")

    def test_the_grid_never_runs_past_midnight(self):
        """A job running into tomorrow stops the grid at the end of
        today — tomorrow has its own page."""
        slots = day_slots(
            self.day, [event(local(self.day, 23), local(self.day, 23) + timedelta(hours=3))]
        )
        self.assertEqual(self.labels(slots)[-1], "11:30 PM")
        self.assertEqual(slots[-1]["value"], "2026-10-01T23:30")

    def test_the_slots_step_by_half_an_hour_across_a_dst_change(self):
        """The clocks go back at 2am on 2026-11-01, and the grid still
        steps by half an hour of wall clock with nothing repeated and
        nothing missed.

        What this does **not** pin is naive versus aware building:
        `zoneinfo` datetimes add timedeltas to their naive fields, so
        an aware grid steps by the wall clock too. Mutating
        `_local_naive` to leave the datetimes aware passes this test
        and every other one here — checked, rather than assumed, after
        an earlier docstring claimed the opposite.

        The early event is what makes this reach the transition at
        all: it drags the floor down to midnight. A plain 6am-8pm
        window sails straight over 2am.
        """
        day = date(2026, 11, 1)
        early = timezone.make_aware(
            datetime.combine(day, time(0, 10)), ZoneInfo("America/New_York")
        )
        slots = day_slots(day, [event(early, early + timedelta(minutes=20))])
        labels = self.labels(slots)
        self.assertEqual(labels[0], "12:00 AM")
        self.assertEqual(
            labels[2:6], ["1:00 AM", "1:30 AM", "2:00 AM", "2:30 AM"], "an hour lived twice"
        )
        self.assertEqual(len(set(slot["value"] for slot in slots)), len(slots))


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
