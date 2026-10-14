"""The stats sheet: the same figures over several periods at once.

Phase 20. The owner asked for "a sort of stats sheet based on the role
of the user" — a Sales Rep seeing how many jobs they sold over the past
week, month, three, six and twelve months and what those were worth; a
Cleaner seeing how many jobs they did and what the work was worth.

The profile already computed every one of those figures, one window at
a time behind tabs, which answers "how many this month" but not "is
this month better than the last three". The sheet puts the periods in
rows.

Two things these tests are really for.

**The sheet and the cards must not drift.** Both are on the same page.
A second implementation of "jobs completed" that disagreed with the
first by a definition — completed_at versus status, say — would show
two different numbers side by side, and the one people would trust is
whichever they saw first. `crew_sheet` calls `crew_stats`, and
`test_the_sheet_agrees_with_the_single_window_figures` holds that true.

**A period boundary has to actually bound.** Work from eight months ago
belongs in the twelve-month row and in no other, and a sheet that
quietly ignored its own windows would look perfectly reasonable — every
row showing the same number is exactly what a lifetime total looks
like.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job, Quote
from apps.jobs.tests import _factories as f
from apps.users.roles import Role
from apps.users.stats import PERIODS, crew_sheet, crew_stats, sales_sheet, sales_stats

PASSWORD = "correct-horse-battery"


def completed(job, days_ago, rating=None):
    Job.objects.filter(pk=job.pk).update(
        status=Job.Status.COMPLETED,
        completed_at=timezone.now() - timedelta(days=days_ago),
        customer_rating=rating,
    )


class PeriodsTests(TestCase):
    def test_the_periods_are_the_ones_asked_for(self):
        """Week, 1, 3, 6 and 12 months — the owner's own list."""
        self.assertEqual([days for days, _ in PERIODS], [7, 30, 90, 180, 365])

    def test_every_period_is_labelled(self):
        for days, label in PERIODS:
            self.assertTrue(label, days)


class CrewSheetTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.customer = f.contact(self.owner)

    def did_work(self, days_ago, price, hours=Decimal("2"), rating=None):
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal(price))])
        f.assign(job, self.casey, hours=hours)
        completed(job, days_ago, rating)
        return job

    def rows(self):
        return {row["days"]: row for row in crew_sheet(self.casey)}

    def test_a_row_for_every_period(self):
        self.assertEqual([row["days"] for row in crew_sheet(self.casey)], [7, 30, 90, 180, 365])

    def test_work_counts_only_in_the_periods_that_contain_it(self):
        """The assertion that a sheet ignoring its own windows fails.

        One job eight months back: it belongs in the twelve-month row
        and nowhere else.
        """
        self.did_work(days_ago=240, price="300")
        rows = self.rows()
        self.assertEqual(
            {days: rows[days]["jobs_completed"] for days in (7, 30, 90, 180, 365)},
            {7: 0, 30: 0, 90: 0, 180: 0, 365: 1},
        )

    def test_the_periods_accumulate(self):
        """Each period contains the shorter ones: a job this week is
        also in the month, the quarter and the year."""
        self.did_work(days_ago=2, price="100")
        self.did_work(days_ago=45, price="200")
        self.did_work(days_ago=200, price="400")
        rows = self.rows()
        self.assertEqual(
            {days: rows[days]["jobs_completed"] for days in (7, 30, 90, 180, 365)},
            {7: 1, 30: 1, 90: 2, 180: 2, 365: 3},
        )

    def test_the_sheet_says_what_the_work_was_worth(self):
        """ "cleaned x amount of jobs costing over $y" — the total, not
        the average, which is what the cards already showed."""
        self.did_work(days_ago=2, price="150")
        self.did_work(days_ago=3, price="250")
        week = self.rows()[7]
        self.assertEqual(week["jobs_completed"], 2)
        self.assertEqual(week["value"], Decimal("400.00"))

    def test_a_period_with_no_work_reads_zero_not_blank(self):
        """A money figure of `None` renders as an empty cell, which
        reads as "unknown" rather than "none"."""
        row = self.rows()[7]
        self.assertEqual(row["jobs_completed"], 0)
        self.assertEqual(row["value"], Decimal("0.00"))

    def test_the_sheet_agrees_with_the_single_window_figures(self):
        """Both are on the same page; they cannot disagree."""
        self.did_work(days_ago=2, price="100", rating=5)
        self.did_work(days_ago=60, price="300", rating=3)
        for days, _ in PERIODS:
            single = crew_stats(self.casey, days)
            row = self.rows()[days]
            for key in ("jobs_completed", "hours", "value", "average_job_value", "average_rating"):
                self.assertEqual(row[key], single[key], f"{key} disagrees for {days} days")

    def test_another_persons_work_is_not_counted(self):
        other = grant_role(f.user("jordan"), Role.CLEANER)
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("500"))])
        f.assign(job, other)
        completed(job, days_ago=2)
        self.assertEqual(self.rows()[365]["jobs_completed"], 0)

    def test_an_unfinished_job_is_not_counted(self):
        """Every count of finished work reads `completed_at`."""
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("200"))])
        f.assign(job, self.casey)
        self.assertEqual(self.rows()[365]["jobs_completed"], 0)


class FutureDatedEventTests(TestCase):
    """A timestamp in the future must not land in every period.

    Raised in review. Every period filtered `__gte=since` with no upper
    bound, so a completion or acceptance stamped later than now fell
    into every period whose start it followed — "this week" counting
    work dated next year, and all five rows inflated at once.

    Reachable through a bad import, an admin edit, or clock skew
    between a container and its host. The fix is an exclusive upper
    bound from one captured `now`, which also gives a sheet's five rows
    a single clock instead of five.
    """

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.riley = grant_role(f.user("riley"), Role.SALES_REP)
        self.customer = f.contact(self.owner)

    def test_a_job_completed_in_the_future_is_in_no_period(self):
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("900"))])
        f.assign(job, self.casey, hours=Decimal("4"))
        completed(job, days_ago=-30)  # stamped a month from now
        rows = {row["days"]: row for row in crew_sheet(self.casey)}
        self.assertEqual(
            {days: rows[days]["jobs_completed"] for days in (7, 30, 90, 180, 365)},
            {7: 0, 30: 0, 90: 0, 180: 0, 365: 0},
        )
        self.assertEqual(rows[365]["value"], Decimal("0.00"))

    def test_a_quote_accepted_in_the_future_is_in_no_period(self):
        quote = f.quote(self.customer, self.riley, lines=[(Decimal("1"), Decimal("700"))])
        ahead = timezone.now() + timedelta(days=30)
        Quote.objects.filter(pk=quote.pk).update(
            status=Quote.Status.ACCEPTED, accepted_at=ahead, sent_at=ahead, created_at=ahead
        )
        rows = {row["days"]: row for row in sales_sheet(self.riley)}
        self.assertEqual(
            {days: rows[days]["sold"] for days in (7, 30, 90, 180, 365)},
            {7: 0, 30: 0, 90: 0, 180: 0, 365: 0},
        )
        self.assertEqual(rows[365]["value_won"], Decimal("0"))

    def test_todays_work_still_counts(self):
        """The bound is exclusive on `now`, so it must not exclude work
        that happened a moment ago."""
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("120"))])
        f.assign(job, self.casey, hours=Decimal("1"))
        Job.objects.filter(pk=job.pk).update(
            status=Job.Status.COMPLETED, completed_at=timezone.now() - timedelta(seconds=5)
        )
        rows = {row["days"]: row for row in crew_sheet(self.casey)}
        self.assertEqual(rows[7]["jobs_completed"], 1)

    def test_upcoming_work_is_still_counted_though(self):
        """`upcoming` is deliberately unbounded above — it means
        everything still to come, not everything in the window."""
        job = f.job(self.customer, self.owner, start=timezone.now() + timedelta(days=400), lines=[])
        f.assign(job, self.casey)
        self.assertEqual(crew_stats(self.casey, 7)["upcoming"], 1)

    def test_one_clock_for_the_whole_sheet(self):
        """Five rows computed from five `timezone.now()` calls could
        disagree about where a period starts. The sheet captures one."""
        with mock.patch("apps.users.stats.timezone.now", wraps=timezone.now) as clock:
            crew_sheet(self.casey)
        self.assertEqual(clock.call_count, 1, "the sheet read the clock more than once")


class SalesSheetTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.riley = grant_role(f.user("riley"), Role.SALES_REP)
        self.customer = f.contact(self.owner)

    def sold(self, days_ago, price, raised_days_ago=None):
        """A quote accepted `days_ago`, raised then or earlier.

        `created_at` is set too, which the first version of this helper
        did not do — leaving a quote created *now* and accepted months
        ago. That is impossible in life and it made the test assert
        nonsense; `sold` and `won` then disagreed for a reason that was
        the fixture's fault rather than the code's. It turned out the
        code had a real version of the same disagreement, which is why
        `sold` exists, but the fixture had to be right first.
        """
        quote = f.quote(self.customer, self.riley, lines=[(Decimal("1"), Decimal(price))])
        when = timezone.now() - timedelta(days=days_ago)
        raised = timezone.now() - timedelta(days=raised_days_ago or days_ago)
        Quote.objects.filter(pk=quote.pk).update(
            status=Quote.Status.ACCEPTED, accepted_at=when, sent_at=raised, created_at=raised
        )
        return quote

    def rows(self):
        return {row["days"]: row for row in sales_sheet(self.riley)}

    def test_a_row_for_every_period(self):
        self.assertEqual([row["days"] for row in sales_sheet(self.riley)], [7, 30, 90, 180, 365])

    def test_what_they_sold_and_what_it_was_worth(self):
        """ "sold x jobs in the past week ... that costs $y"."""
        self.sold(days_ago=2, price="400")
        self.sold(days_ago=3, price="600")
        week = self.rows()[7]
        # `sold`, not `won`. An earlier edit here silently did not
        # apply — ruff had reformatted the docstring above, the
        # `str.replace` matched nothing, and nothing asserted that it
        # had. The test then passed anyway, because these two quotes
        # are created *and* accepted recently so `won` agrees by
        # accident, leaving the figure the test exists for unchecked.
        self.assertEqual(week["sold"], 2)
        self.assertEqual(week["value_won"], Decimal("1000"))

    def test_a_sale_counts_only_in_the_periods_that_contain_it(self):
        self.sold(days_ago=200, price="500")
        rows = self.rows()
        self.assertEqual(
            {days: rows[days]["sold"] for days in (7, 30, 90, 180, 365)},
            {7: 0, 30: 0, 90: 0, 180: 0, 365: 1},
        )

    def test_a_period_with_no_sales_reads_zero(self):
        row = self.rows()[7]
        self.assertEqual(row["sold"], 0)
        self.assertEqual(row["value_won"], Decimal("0"))

    def test_sold_and_its_value_always_describe_the_same_quotes(self):
        """The defect `sold` exists for.

        A quote raised in spring and signed last Tuesday belongs to
        last week's sales. `won` dates by creation, so it put the page
        in the position of reading "sold 0 jobs, worth $500" for the
        last seven days — measured on the page as it was. `sold` and
        `value_won` come from one queryset now and cannot part company.
        """
        self.sold(days_ago=2, price="500", raised_days_ago=100)
        for days, _ in PERIODS:
            row = self.rows()[days]
            if row["sold"] == 0:
                self.assertEqual(row["value_won"], Decimal("0"), f"{days} days")
            else:
                self.assertGreater(row["value_won"], Decimal("0"), f"{days} days")
        week = self.rows()[7]
        self.assertEqual((week["sold"], week["value_won"]), (1, Decimal("500")))

    def test_the_close_rate_still_dates_by_when_the_quote_was_raised(self):
        """Deliberately a different basis, and kept: of what I quoted
        then, how much came in. Dating it by acceptance would flatter
        itself."""
        self.sold(days_ago=2, price="500", raised_days_ago=100)
        week = self.rows()[7]
        self.assertEqual(week["sold"], 1)
        self.assertEqual(week["won"], 0)
        year = self.rows()[365]
        self.assertEqual(year["won"], 1)

    def test_the_sheet_agrees_with_the_single_window_figures(self):
        self.sold(days_ago=2, price="400")
        self.sold(days_ago=100, price="900")
        for days, _ in PERIODS:
            single = sales_stats(self.riley, days)
            row = self.rows()[days]
            for key in ("sold", "won", "value_won", "quotes_sent", "close_rate", "decided"):
                self.assertEqual(row[key], single[key], f"{key} disagrees for {days} days")

    def test_another_reps_sale_is_not_counted(self):
        other = grant_role(f.user("sam"), Role.SALES_REP)
        quote = f.quote(self.customer, other, lines=[(Decimal("1"), Decimal("800"))])
        Quote.objects.filter(pk=quote.pk).update(
            status=Quote.Status.ACCEPTED, accepted_at=timezone.now() - timedelta(days=1)
        )
        self.assertEqual(self.rows()[365]["sold"], 0)


class ProfilePageTests(TestCase):
    """The sheet has to reach the page, for the right person."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.riley = grant_role(f.user("riley"), Role.SALES_REP)
        self.customer = f.contact(self.owner)

    def test_a_crew_member_sees_a_field_work_sheet(self):
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("275"))])
        f.assign(job, self.casey, hours=Decimal("3"))
        completed(job, days_ago=2)
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(reverse("people:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["crew_periods"])
        for _, label in PERIODS:
            self.assertContains(response, label)
        self.assertContains(response, "Field work by period")

    def test_a_crew_member_gets_no_sales_sheet(self):
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(reverse("people:profile"))
        self.assertIsNone(response.context["sales_periods"])
        self.assertNotContains(response, "Sales by period")

    def test_a_sales_rep_sees_a_sales_sheet(self):
        self.sold = f.quote(self.customer, self.riley, lines=[(Decimal("1"), Decimal("500"))])
        self.client.login(username="riley", password=PASSWORD)
        response = self.client.get(reverse("people:profile"))
        self.assertIsNotNone(response.context["sales_periods"])
        self.assertContains(response, "Sales by period")

    def test_the_figures_appear_in_the_sheet_not_just_the_context(self):
        """A context variable no template renders is not a feature.

        Scoped to the sheet's own table on purpose. The first version
        searched the whole page for "275", which also appears in the
        average-job-value card — so it passed whether or not the sheet
        rendered at all, which is the one thing it was meant to
        establish.
        """
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("275"))])
        f.assign(job, self.casey, hours=Decimal("3"))
        completed(job, days_ago=2)
        self.client.login(username="casey", password=PASSWORD)
        body = self.client.get(reverse("people:profile")).content.decode()
        table = body[body.index("Field work by period") :]
        table = table[: table.index("</table>")]
        self.assertIn("275", table)
        self.assertIn("This week", table)

    def test_the_cards_still_work(self):
        """The sheet was added beside them, not instead of them."""
        self.client.login(username="casey", password=PASSWORD)
        response = self.client.get(reverse("people:profile"))
        self.assertIsNotNone(response.context["crew"])
        self.assertContains(response, "Jobs completed")

    def test_an_owner_who_also_works_sees_both_sheets(self):
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("100"))])
        f.assign(job, self.owner)
        completed(job, days_ago=1)
        self.client.login(username="boss", password=PASSWORD)
        response = self.client.get(reverse("people:profile"))
        self.assertIsNotNone(response.context["crew_periods"])
        self.assertIsNotNone(response.context["sales_periods"])
        # The template can drop either sheet while both context values
        # stay populated, so assert on what was rendered.
        self.assertContains(response, "Field work by period")
        self.assertContains(response, "Sales by period")

    def test_someone_elses_profile_shows_their_sheet_not_mine(self):
        job = f.job(self.customer, self.owner, lines=[(Decimal("1"), Decimal("640"))])
        f.assign(job, self.casey)
        completed(job, days_ago=2)
        self.client.login(username="boss", password=PASSWORD)
        response = self.client.get(reverse("people:member", args=[self.casey.username]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["crew_periods"][4]["jobs_completed"], 1)
