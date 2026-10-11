"""Does a page's query count grow with the number of rows on it?

QA audit. An N+1 query is invisible in development and invisible in a
unit test: the page is correct, it is just slower for every record
added. On a Raspberry Pi serving a real book of business that is the
difference between a page and a wait.

The method is deliberately not "assert this page runs N queries",
because that number changes with every legitimate feature and teaches
people to re-baseline the constant without looking. Instead each page
is loaded **twice** — once with a few records, once with many — and the
two query counts are compared. A page that does the same work per
record scores the same both times; an N+1 scores roughly its row count
higher.

`ALLOWED_GROWTH` is small rather than zero on purpose: a few pages
legitimately run one extra query when a region of the page stops being
empty, and pagination itself can add one. Growth proportional to row
count is what this is looking for, and 15 extra rows cannot hide in a
budget of 3.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Activity, Company, Contact, Property, Task
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Payment
from apps.jobs.tests import _factories as f
from apps.users.roles import Role

PASSWORD = "correct-horse-battery"
FEW, MANY = 3, 18
ALLOWED_GROWTH = 3


class QueryGrowthTests(TestCase):
    """One owner, and a `seed` that can be run twice."""

    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.service = f.service()
        self.client.login(username="boss", password=PASSWORD)
        self.made = 0

    # --- builders ----------------------------------------------------

    def customers(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            contact = Contact.objects.create(
                first_name=f"Person{n:03d}",
                last_name=f"Surname{n:03d}",
                email=f"p{n}@example.test",
                created_by=self.owner,
            )
            Property.objects.create(
                contact=contact,
                street=f"{n} Elm St",
                city="Rochester",
                state="NY",
                postal_code="14600",
            )

    def companies(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            company = Company.objects.create(name=f"Company {n:03d}", created_by=self.owner)
            Contact.objects.create(
                first_name=f"C{n}", last_name=f"Contact{n}", company=company, created_by=self.owner
            )

    def jobs(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            customer = f.contact(self.owner, f"J{n}", f"Cust{n}")
            job = f.job(
                customer,
                self.owner,
                start=timezone.now() + timedelta(days=(n % 20) + 1),
                lines=[(Decimal("1"), Decimal("150"))],
            )
            f.assign(job, self.owner)

    def quotes(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            f.quote(f.contact(self.owner, f"Q{n}", f"Cust{n}"), self.owner)

    def invoices(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            job = f.job(f.contact(self.owner, f"I{n}", f"Cust{n}"), self.owner, lines=[])
            invoice = f.invoice(job)
            Payment.objects.create(
                invoice=invoice,
                amount=Decimal("10.00"),
                received_on=timezone.localdate(),
                recorded_by=self.owner,
            )

    def tasks(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            Task.objects.create(
                title=f"Task {n}",
                assigned_to=self.owner,
                contact=f.contact(self.owner, f"T{n}", f"Cust{n}"),
                created_by=self.owner,
            )

    def activities(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            Activity.objects.create(
                activity_type="call",
                subject=f"Call {n}",
                contact=f.contact(self.owner, f"A{n}", f"Cust{n}"),
                created_by=self.owner,
            )

    def expenses(self, count):
        for i in range(count):
            self.made += 1
            n = self.made
            from apps.jobs.models import Expense

            Expense.objects.create(
                description=f"Expense {n}",
                amount=Decimal("20.00"),
                category="supplies",
                date=timezone.localdate(),
                recorded_by=self.owner,
            )

    # --- the measurement ---------------------------------------------

    def growth(self, url, seed, params=None):
        """Extra queries caused by the extra rows."""
        seed(FEW)
        with _Counter() as small:
            response = self.client.get(url, params or {})
        self.assertEqual(response.status_code, 200, url)
        seed(MANY - FEW)
        with _Counter() as large:
            response = self.client.get(url, params or {})
        self.assertEqual(response.status_code, 200, url)
        return small.queries, large.queries

    def assertNoGrowth(self, name, url, seed, params=None):
        small, large = self.growth(url, seed, params)
        self.assertLessEqual(
            large - small,
            ALLOWED_GROWTH,
            f"{name}: {small} queries for {FEW} rows, {large} for {MANY} — "
            f"grew by {large - small}, which scales with the data",
        )

    # --- the pages ----------------------------------------------------

    def test_customers_list(self):
        self.assertNoGrowth("Customers", reverse("crm:contact_list"), self.customers)

    def test_companies_list(self):
        self.assertNoGrowth("Companies", reverse("crm:company_list"), self.companies)

    def test_tasks_hub(self):
        self.assertNoGrowth("Tasks", reverse("crm:task_list"), self.tasks)

    def test_activities_list(self):
        self.assertNoGrowth("Activities", reverse("crm:activity_list"), self.activities)

    def test_jobs_calendar_month(self):
        self.assertNoGrowth(
            "Calendar (month)", reverse("jobs:calendar"), self.jobs, {"view": "month"}
        )

    def test_quotes_list(self):
        self.assertNoGrowth("Estimates", reverse("jobs:quote_list"), self.quotes)

    def test_invoices_list(self):
        self.assertNoGrowth("Invoices", reverse("jobs:invoice_list"), self.invoices)

    def test_payments_list(self):
        self.assertNoGrowth("Payments", reverse("jobs:payment_list"), self.invoices)

    def test_expenses_list(self):
        self.assertNoGrowth("Expenses", reverse("jobs:expense_list"), self.expenses)

    def test_financials(self):
        self.assertNoGrowth("Financials", reverse("jobs:financials"), self.invoices)

    def test_dashboard(self):
        self.assertNoGrowth("Dashboard", reverse("core:index"), self.jobs)

    def test_search(self):
        self.assertNoGrowth("Search", reverse("core:search"), self.customers, {"q": "Surname"})

    def test_change_log(self):
        self.assertNoGrowth("Change log", reverse("core:activity_log"), self.customers)

    def test_map(self):
        self.assertNoGrowth("Map", reverse("jobs:map"), self.customers)


class _Counter:
    """`assertNumQueries` asserts a number; this one just reports it."""

    def __init__(self):
        self.queries = 0

    def __enter__(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.ctx = CaptureQueriesContext(connection)
        self.ctx.__enter__()
        return self

    def __exit__(self, *exc):
        self.ctx.__exit__(*exc)
        self.queries = len(self.ctx.captured_queries)
        return False
