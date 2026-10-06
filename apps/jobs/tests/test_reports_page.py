import csv
import io
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Contact
from apps.crm.tests._helpers import grant_role
from apps.jobs import crew, reporting
from apps.jobs.models import Expense, Invoice, Job, Quote
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"
LIST = reverse("jobs:report_list")


def detail(slug, **params):
    url = reverse("jobs:report_detail", args=[slug])
    return f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}" if params else url


class ReportTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss", first_name="Olivia", last_name="Grant"), Role.OWNER)
        self.rep = grant_role(f.user("rep", first_name="Robin", last_name="Reyes"), Role.SALES_REP)
        self.customer = f.contact(self.owner)
        self.today = timezone.localdate()
        self.client.login(username="boss", password=PASSWORD)

    def rows(self, slug, **params):
        return self.client.get(detail(slug, **params)).context["table"].rows


class CatalogueTests(ReportTestCase):
    def test_the_owner_sees_every_report(self):
        response = self.client.get(LIST)
        self.assertEqual(len(response.context["reports"]), len(reporting.CATALOGUE))
        self.assertEqual(response.context["hidden"], 0)

    def test_a_sales_rep_sees_no_money_reports(self):
        self.client.login(username="rep", password=PASSWORD)
        response = self.client.get(LIST)
        shown = {report.slug for report in response.context["reports"]}
        self.assertNotIn("revenue-by-service", shown)
        self.assertIn("estimate-outcomes", shown)
        self.assertGreater(response.context["hidden"], 0)
        self.assertContains(response, "only the owner sees")

    def test_a_money_report_is_not_found_for_a_rep(self):
        # 404, not 403, so the catalogue doesn't leak what else exists.
        self.client.login(username="rep", password=PASSWORD)
        self.assertEqual(self.client.get(detail("revenue-by-service")).status_code, 404)

    def test_a_cleaner_sees_no_reports_at_all(self):
        grant_role(f.user("casey"), Role.CLEANER)
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(LIST).status_code, 403)
        self.assertEqual(self.client.get(detail("jobs-by-status")).status_code, 403)

    def test_an_unknown_report_is_not_found(self):
        self.assertEqual(self.client.get(detail("made-up")).status_code, 404)

    def test_every_report_in_the_catalogue_opens(self):
        for report in reporting.CATALOGUE:
            response = self.client.get(detail(report.slug))
            self.assertEqual(response.status_code, 200, report.slug)
            self.assertContains(response, report.title)


class FiguresTests(ReportTestCase):
    def test_revenue_by_service_matches_what_was_invoiced(self):
        job = f.job(self.customer, self.owner, lines=[])
        f.invoice(job, lines=[(Decimal("2"), Decimal("150"))], issued=self.today)
        rows = self.rows("revenue-by-service")
        self.assertEqual(rows[0]["total"], Decimal("300.00"))
        self.assertEqual(rows[0]["share"], 100)

    def test_a_draft_invoice_is_not_revenue(self):
        job = f.job(self.customer, self.owner, lines=[])
        f.invoice(job, lines=[(Decimal("1"), Decimal("500"))], status=Invoice.Status.DRAFT)
        self.assertEqual(self.rows("revenue-by-service"), [])

    def test_revenue_by_rep_credits_the_jobs_rep(self):
        job = f.job(self.customer, self.owner, sales_rep=self.rep, lines=[])
        f.invoice(job, lines=[(Decimal("1"), Decimal("400"))], issued=self.today)
        rows = self.rows("revenue-by-rep")
        self.assertEqual(rows[0]["name"], "Robin Reyes")
        self.assertEqual(rows[0]["total"], Decimal("400.00"))

    def test_profit_over_time_subtracts_expenses(self):
        job = f.job(self.customer, self.owner, lines=[])
        f.invoice(job, lines=[(Decimal("1"), Decimal("900"))], issued=self.today)
        Expense.objects.create(
            date=self.today,
            amount=Decimal("250"),
            category=Expense.Category.FUEL,
            recorded_by=self.owner,
        )
        rows = self.rows("profit-by-month", range="month")
        latest = rows[-1]
        self.assertEqual(latest["revenue"], Decimal("900.00"))
        self.assertEqual(latest["expenses"], Decimal("250.00"))
        self.assertEqual(latest["profit"], Decimal("650.00"))

    def test_jobs_by_status(self):
        done = f.job(self.customer, self.owner, start=f.aware(self.today.year, self.today.month, 1))
        done.status = Job.Status.COMPLETED
        done.save(update_fields=["status"])
        rows = {row["name"]: row["count"] for row in self.rows("jobs-by-status", range="month")}
        self.assertEqual(rows.get("Completed"), 1)

    def test_estimate_outcomes_counts_only_decided_ones(self):
        f.quote(self.customer, self.rep, status=Quote.Status.ACCEPTED)
        f.quote(self.customer, self.rep, status=Quote.Status.DECLINED)
        f.quote(self.customer, self.rep, status=Quote.Status.SENT)  # still out
        row = self.rows("estimate-outcomes")[0]
        self.assertEqual((row["written"], row["won"], row["rate"]), (3, 1, 50))

    def test_where_customers_come_from_counts_customers_not_leads(self):
        Contact.objects.filter(pk=self.customer.pk).update(
            lead_source=Contact.LeadSource.REFERRAL, status=Contact.Status.CUSTOMER
        )
        lead = f.contact(self.owner, "Lee", "Lead")
        Contact.objects.filter(pk=lead.pk).update(
            lead_source=Contact.LeadSource.WEBSITE, status=Contact.Status.LEAD
        )
        rows = {row["name"]: row["count"] for row in self.rows("customers-by-source")}
        self.assertEqual(rows, {"Referral": 1})

    def test_shares_add_up_to_the_whole(self):
        # Derived from the rows themselves, so they can't disagree with
        # the totals beside them.
        job = f.job(self.customer, self.owner, lines=[])
        f.invoice(job, lines=[(Decimal("1"), Decimal("300"))], issued=self.today)
        other = f.job(self.customer, self.owner, lines=[])
        f.invoice(
            other,
            lines=[(Decimal("1"), Decimal("100"))],
            issued=self.today,
        )
        rows = self.rows("revenue-by-service")
        self.assertEqual(sum(row["share"] for row in rows), 100)

    def test_someone_who_has_left_still_shows_their_hours(self):
        from apps.users.models import get_profile

        gone = grant_role(f.user("former", first_name="Former"), Role.CLEANER)
        profile = get_profile(gone)
        profile.hourly_rate = Decimal("18.00")
        profile.save(update_fields=["hourly_rate"])
        started = timezone.now() - timedelta(hours=2)
        crew.clock_in(gone, now=started)
        crew.clock_out(gone, now=started + timedelta(hours=2))
        gone.is_active = False
        gone.save(update_fields=["is_active"])

        rows = {row["name"]: row for row in self.rows("crew-hours")}
        self.assertIn("Former", rows)
        self.assertEqual(rows["Former"]["hours"], Decimal("2.00"))

    def test_where_customers_come_from(self):
        Contact.objects.filter(pk=self.customer.pk).update(lead_source=Contact.LeadSource.REFERRAL)
        row = self.rows("customers-by-source")[0]
        self.assertEqual((row["name"], row["count"], row["share"]), ("Referral", 1, 100))

    def test_crew_hours_shows_pay_only_where_there_is_a_rate(self):
        from apps.users.models import get_profile

        casey = grant_role(f.user("casey", first_name="Casey"), Role.CLEANER)
        profile = get_profile(casey)
        profile.hourly_rate = Decimal("20.00")
        profile.save(update_fields=["hourly_rate"])
        started = timezone.now() - timedelta(hours=3)
        crew.clock_in(casey, now=started)
        crew.clock_out(casey, now=started + timedelta(hours=3))

        rows = {row["name"]: row for row in self.rows("crew-hours")}
        self.assertEqual(rows["Casey"]["hours"], Decimal("3.00"))
        self.assertEqual(rows["Casey"]["pay"], Decimal("60.00"))
        self.assertIsNone(rows["Robin Reyes"]["pay"])

    def test_a_period_with_nothing_in_it_says_so(self):
        response = self.client.get(detail("revenue-by-service", range="day"))
        self.assertContains(response, "Nothing in this period")

    def earlier_this_year(self):
        """A day in this calendar year but not this month, whenever the
        tests happen to run. Counting back a fixed number of days falls
        into last year for half the year."""
        first_of_month = self.today.replace(day=1)
        if first_of_month.month > 1:
            return first_of_month - timedelta(days=1)
        # In January there's no earlier month, so use the 1st itself and
        # compare against the day instead.
        return first_of_month

    def test_the_period_follows_the_buttons(self):
        job = f.job(self.customer, self.owner, lines=[])
        earlier = self.earlier_this_year()
        f.invoice(job, lines=[(Decimal("1"), Decimal("100"))], issued=earlier)
        if earlier.month != self.today.month:
            self.assertEqual(self.rows("revenue-by-service", range="month"), [])
        self.assertEqual(len(self.rows("revenue-by-service", range="ytd")), 1)


class TotalsTests(ReportTestCase):
    def test_money_and_counts_are_totalled_but_shares_are_not(self):
        job = f.job(self.customer, self.owner, sales_rep=self.rep, lines=[])
        f.invoice(job, lines=[(Decimal("1"), Decimal("250"))], issued=self.today)
        table = self.client.get(detail("revenue-by-rep")).context["table"]
        self.assertEqual(table.totals["total"], Decimal("250.00"))
        self.assertEqual(table.totals["jobs"], 1)
        self.assertNotIn("share", table.totals)
        self.assertNotIn("name", table.totals)


class CsvTests(ReportTestCase):
    def download(self, slug, **params):
        url = reverse("jobs:report_csv", args=[slug])
        response = self.client.get(url, params)
        body = b"".join(response.streaming_content).decode()
        return response, list(csv.DictReader(io.StringIO(body)))

    def test_the_file_holds_what_the_page_shows(self):
        job = f.job(self.customer, self.owner, lines=[])
        f.invoice(job, lines=[(Decimal("3"), Decimal("100"))], issued=self.today)
        response, rows = self.download("revenue-by-service")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn("revenue-by-service-", response["Content-Disposition"])
        # The file shows what the page showed: money is a sum of sums
        # and arrives with more places than it's worth.
        self.assertEqual(rows[0]["Revenue"], "300.00")
        self.assertEqual(rows[0]["Share"], "100")

    def test_an_empty_cell_is_empty_not_the_word_none(self):
        f.quote(self.customer, self.rep, status=Quote.Status.SENT)  # nothing decided
        _, rows = self.download("estimate-outcomes")
        self.assertEqual(rows[0]["Win rate"], "")

    def test_the_file_follows_the_same_period(self):
        job = f.job(self.customer, self.owner, lines=[])
        earlier = self.today.replace(day=1) - timedelta(days=1)
        if earlier.year != self.today.year:  # January: nothing earlier this year
            return
        f.invoice(job, lines=[(Decimal("1"), Decimal("100"))], issued=earlier)
        # An empty period still gives a file with its headings, not
        # zero bytes — so "no rows" means one blank line, not none.
        empty = self.download("revenue-by-service", range="month")[1]
        self.assertEqual([row["Revenue"] for row in empty], [""])
        self.assertEqual(len(self.download("revenue-by-service", range="ytd")[1]), 1)

    def test_a_custom_range_is_carried_into_the_download(self):
        job = f.job(self.customer, self.owner, lines=[])
        day = self.today - timedelta(days=3)
        f.invoice(job, lines=[(Decimal("1"), Decimal("777"))], issued=day)
        page = self.client.get(
            detail("revenue-by-service", range="custom", start=day.isoformat(), end=day.isoformat())
        )
        # The link has to carry the dates, or the download quietly falls
        # back to this month and exports different figures.
        link = page.context["query"]
        self.assertIn(f"start={day.isoformat()}", link)
        self.assertIn(f"end={day.isoformat()}", link)
        _, rows = self.download(
            "revenue-by-service", range="custom", start=day.isoformat(), end=day.isoformat()
        )
        self.assertEqual(rows[0]["Revenue"], "777.00")

    def test_a_rep_cannot_download_a_money_report(self):
        self.client.login(username="rep", password=PASSWORD)
        response = self.client.get(reverse("jobs:report_csv", args=["revenue-by-service"]))
        self.assertEqual(response.status_code, 404)

    def test_every_report_downloads_with_its_headings(self):
        # Reading the body matters: a zero-byte file is a 200 too.
        for report in reporting.CATALOGUE:
            response = self.client.get(reverse("jobs:report_csv", args=[report.slug]))
            self.assertEqual(response.status_code, 200, report.slug)
            body = b"".join(response.streaming_content).decode()
            first_line = body.splitlines()[0] if body else ""
            for column in report.columns:
                self.assertIn(column.label, first_line, report.slug)

    def test_column_labels_are_distinct_so_the_file_keeps_every_one(self):
        # csv_rows keys on the label, so two columns sharing one would
        # overwrite each other in the file.
        for report in reporting.CATALOGUE:
            labels = [column.label for column in report.columns]
            self.assertEqual(len(labels), len(set(labels)), report.slug)
