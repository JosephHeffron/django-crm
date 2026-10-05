import re
from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Expense, Invoice, InvoiceLineItem, Payment
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"
INVOICES = reverse("jobs:invoice_list")
NEW_INVOICE = reverse("jobs:invoice_create")
EXPENSES = reverse("jobs:expense_list")
NEW_EXPENSE = reverse("jobs:expense_create")


class FinanceTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.customer = f.contact(self.owner)
        self.job = f.job(self.customer, self.owner, lines=[(Decimal("2"), Decimal("150"))])
        self.service = f.service()
        self.today = timezone.localdate()
        self.client.login(username="boss", password=PASSWORD)

    def invoice_form(self, **extra):
        data = {
            "job": self.job.pk,
            "issued_on": self.today.isoformat(),
            "due_on": (self.today + timedelta(days=14)).isoformat(),
            "status": Invoice.Status.SENT,
            "notes": "",
            "lines-TOTAL_FORMS": "0",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
        }
        data.update(extra)
        return data

    def with_lines(self, rows, initial=0, **extra):
        data = self.invoice_form(
            **{"lines-TOTAL_FORMS": str(len(rows)), "lines-INITIAL_FORMS": str(initial)}, **extra
        )
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"lines-{index}-{key}"] = value
        return data


class AccessTests(FinanceTestCase):
    def test_only_the_owner_sees_money(self):
        pages = [
            INVOICES,
            NEW_INVOICE,
            EXPENSES,
            NEW_EXPENSE,
            reverse("jobs:payment_list"),
            reverse("jobs:financials"),
        ]
        for username, role in (("rep", Role.SALES_REP), ("crew", Role.CLEANER)):
            grant_role(f.user(username), role)
            self.client.login(username=username, password=PASSWORD)
            for page in pages:
                self.assertEqual(self.client.get(page).status_code, 403, page)

    def test_logged_out_is_sent_to_sign_in(self):
        self.client.logout()
        self.assertEqual(self.client.get(INVOICES).status_code, 302)

    def test_an_unknown_invoice_is_not_found(self):
        self.assertEqual(
            self.client.get(reverse("jobs:invoice_detail", args=[9999])).status_code, 404
        )


class InvoicingTests(FinanceTestCase):
    def test_billing_a_job_starts_from_its_own_lines(self):
        response = self.client.get(NEW_INVOICE, {"job": str(self.job.pk)})
        self.assertContains(response, 'value="150.00"')
        self.assertContains(response, self.job.number)

    def test_every_line_of_the_job_carries_over(self):
        # A formset renders `extra` rows however many it's seeded with,
        # so a job with several lines would otherwise arrive as one and
        # the customer would be under-billed.
        job = f.job(
            self.customer,
            self.owner,
            lines=[
                (Decimal("2"), Decimal("150")),
                (Decimal("1"), Decimal("75")),
                (Decimal("3"), Decimal("20")),
            ],
        )
        page = self.client.get(NEW_INVOICE, {"job": str(job.pk)}).content.decode()
        prices = re.findall(r'name="lines-\d+-unit_price"[^>]*value="([\d.]+)"', page)
        self.assertEqual(prices, ["150.00", "75.00", "20.00"])
        # Plus one blank row to add another.
        rows = len(re.findall(r'name="lines-\d+-service_type"', page))
        self.assertEqual(rows, 4)

    def test_creating_an_invoice_takes_the_customer_from_the_job(self):
        response = self.client.post(
            NEW_INVOICE,
            self.with_lines(
                [{"service_type": self.service.pk, "quantity": "2", "unit_price": "150.00"}]
            ),
        )
        invoice = Invoice.objects.get()
        self.assertRedirects(response, invoice.get_absolute_url())
        self.assertEqual(invoice.contact, self.customer)
        self.assertEqual(invoice.total, Decimal("300.00"))

    def test_a_due_date_before_the_issue_date_is_refused(self):
        response = self.client.post(
            NEW_INVOICE,
            self.invoice_form(due_on=(self.today - timedelta(days=1)).isoformat()),
        )
        self.assertContains(response, "before the issue date")  # the apostrophe is escaped
        self.assertFalse(Invoice.objects.exists())

    def test_a_new_invoice_is_dated_today_and_due_in_two_weeks(self):
        response = self.client.get(NEW_INVOICE)
        self.assertContains(response, f'value="{self.today.isoformat()}"')
        self.assertContains(response, f'value="{(self.today + timedelta(days=14)).isoformat()}"')

    def test_nothing_is_saved_when_a_line_is_wrong(self):
        response = self.client.post(
            NEW_INVOICE,
            self.with_lines(
                [{"service_type": self.service.pk, "quantity": "0", "unit_price": "5"}]
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(InvoiceLineItem.objects.exists())

    def test_editing_an_invoice(self):
        invoice = f.invoice(self.job, lines=[(Decimal("1"), Decimal("100"))])
        line = invoice.line_items.get()
        self.client.post(
            reverse("jobs:invoice_update", args=[invoice.pk]),
            self.with_lines(
                [
                    {
                        "id": line.pk,
                        "service_type": line.service_type_id,
                        "quantity": "1",
                        "unit_price": "180.00",
                    }
                ],
                initial=1,
            ),
        )
        self.assertEqual(Invoice.objects.get().total, Decimal("180.00"))

    def test_the_job_page_offers_to_bill_a_job_that_has_no_invoice(self):
        response = self.client.get(self.job.get_absolute_url())
        self.assertContains(response, "Invoice this job")
        f.invoice(self.job)
        self.assertNotContains(self.client.get(self.job.get_absolute_url()), "Invoice this job")


class InvoiceListTests(FinanceTestCase):
    def setUp(self):
        super().setUp()
        self.unpaid = f.invoice(self.job, lines=[(Decimal("1"), Decimal("100"))], issued=self.today)
        self.overdue = f.invoice(
            self.job,
            lines=[(Decimal("1"), Decimal("200"))],
            issued=self.today - timedelta(days=40),
        )
        self.paid = f.invoice(self.job, lines=[(Decimal("1"), Decimal("50"))], issued=self.today)
        Payment.objects.create(
            invoice=self.paid,
            amount=Decimal("50"),
            received_on=self.today,
            recorded_by=self.owner,
        )
        self.draft = f.invoice(self.job, status=Invoice.Status.DRAFT)

    def shown(self, key):
        return list(self.client.get(INVOICES, {"show": key}).context["invoices"])

    def test_the_default_filter_is_what_is_still_owed(self):
        numbers = {invoice.pk for invoice in self.shown("unpaid")}
        self.assertEqual(numbers, {self.unpaid.pk, self.overdue.pk})

    def test_overdue_means_past_its_due_date(self):
        self.assertEqual([i.pk for i in self.shown("overdue")], [self.overdue.pk])

    def test_paid_means_the_balance_is_gone(self):
        self.assertEqual([i.pk for i in self.shown("paid")], [self.paid.pk])

    def test_drafts_are_kept_apart(self):
        self.assertEqual([i.pk for i in self.shown("draft")], [self.draft.pk])

    def test_the_totals_follow_the_filter(self):
        totals = self.client.get(INVOICES, {"show": "unpaid"}).context["totals"]
        self.assertEqual(totals["billed"], Decimal("300.00"))
        self.assertEqual(totals["owed"], Decimal("300.00"))
        self.assertEqual(totals["count"], 2)

    def test_the_badge_says_overdue(self):
        self.assertContains(self.client.get(INVOICES, {"show": "overdue"}), "Overdue")


class PaymentTests(FinanceTestCase):
    def setUp(self):
        super().setUp()
        self.invoice = f.invoice(self.job, lines=[(Decimal("1"), Decimal("300"))])
        self.url = reverse("jobs:payment_create", args=[self.invoice.pk])

    def form(self, **extra):
        data = {
            "amount": "300.00",
            "received_on": self.today.isoformat(),
            "method": Payment.Method.CARD,
            "notes": "",
        }
        data.update(extra)
        return data

    def test_the_amount_starts_at_the_balance_in_whole_cents(self):
        # The balance is a sum of sums, so it arrives with more decimal
        # places than money has; a raw 300.0000 doesn't match a field
        # that steps in cents.
        self.assertContains(self.client.get(self.url), 'value="300.00"')

    def test_recording_a_payment_settles_the_invoice(self):
        response = self.client.post(self.url, self.form())
        self.assertRedirects(response, self.invoice.get_absolute_url())
        payment = Payment.objects.get()
        self.assertEqual((payment.invoice, payment.recorded_by), (self.invoice, self.owner))
        self.assertEqual(Invoice.objects.with_balances().get().balance_amount, Decimal("0.00"))

    def test_a_part_payment_leaves_a_balance(self):
        self.client.post(self.url, self.form(amount="120.00"))
        self.assertEqual(Invoice.objects.with_balances().get().balance_amount, Decimal("180.00"))
        self.assertContains(self.client.get(INVOICES), "Part paid")

    def test_paying_more_than_the_balance_is_allowed_but_says_so(self):
        response = self.client.post(self.url, self.form(amount="350.00"), follow=True)
        self.assertContains(response, "more than the balance")
        self.assertEqual(Payment.objects.get().amount, Decimal("350.00"))

    def test_nothing_is_not_a_payment(self):
        response = self.client.post(self.url, self.form(amount="0"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Payment.objects.exists())

    def test_a_settled_invoice_stops_offering_to_record_more(self):
        self.client.post(self.url, self.form())
        self.assertNotContains(self.client.get(self.invoice.get_absolute_url()), "Record a payment")

    def test_payments_are_listed_with_their_total(self):
        self.client.post(self.url, self.form(amount="120.00"))
        response = self.client.get(reverse("jobs:payment_list"))
        self.assertEqual(response.context["total"], Decimal("120.00"))
        self.assertContains(response, self.invoice.number)


class ExpenseTests(FinanceTestCase):
    def form(self, **extra):
        data = {
            "date": self.today.isoformat(),
            "amount": "85.40",
            "category": Expense.Category.FUEL,
            "description": "Diesel for the van",
        }
        data.update(extra)
        return data

    def test_adding_an_expense(self):
        response = self.client.post(NEW_EXPENSE, self.form())
        self.assertRedirects(response, EXPENSES)
        expense = Expense.objects.get()
        self.assertEqual((expense.amount, expense.recorded_by), (Decimal("85.40"), self.owner))

    def test_the_date_starts_at_today(self):
        self.assertContains(self.client.get(NEW_EXPENSE), f'value="{self.today.isoformat()}"')

    def test_nothing_is_not_an_expense(self):
        response = self.client.post(NEW_EXPENSE, self.form(amount="0"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Expense.objects.exists())

    def test_filtering_by_category(self):
        self.client.post(NEW_EXPENSE, self.form())
        self.client.post(NEW_EXPENSE, self.form(category=Expense.Category.SUPPLIES, amount="20"))
        response = self.client.get(EXPENSES, {"category": Expense.Category.FUEL})
        self.assertEqual([e.amount for e in response.context["expenses"]], [Decimal("85.40")])
        self.assertEqual(response.context["total"], Decimal("85.40"))

    def test_editing_an_expense(self):
        self.client.post(NEW_EXPENSE, self.form())
        expense = Expense.objects.get()
        self.client.post(
            reverse("jobs:expense_update", args=[expense.pk]), self.form(amount="99.00")
        )
        expense.refresh_from_db()
        self.assertEqual(expense.amount, Decimal("99.00"))
        self.assertEqual(expense.recorded_by, self.owner)


class ProfitTests(FinanceTestCase):
    def test_money_recorded_through_the_pages_reaches_profit(self):
        self.client.post(
            NEW_INVOICE,
            self.with_lines(
                [{"service_type": self.service.pk, "quantity": "1", "unit_price": "500.00"}]
            ),
        )
        invoice = Invoice.objects.get()
        self.client.post(
            reverse("jobs:payment_create", args=[invoice.pk]),
            {
                "amount": "500.00",
                "received_on": self.today.isoformat(),
                "method": Payment.Method.CASH,
                "notes": "",
            },
        )
        self.client.post(
            NEW_EXPENSE,
            {
                "date": self.today.isoformat(),
                "amount": "125.00",
                "category": Expense.Category.SUPPLIES,
                "description": "",
            },
        )
        summary = self.client.get(reverse("jobs:financials"), {"range": "month"}).context["summary"]
        self.assertEqual(summary["revenue"], Decimal("500.00"))
        self.assertEqual(summary["collected"], Decimal("500.00"))
        self.assertEqual(summary["expenses"], Decimal("125.00"))
        self.assertEqual(summary["net"], Decimal("375.00"))

    def test_a_draft_invoice_is_not_revenue_yet(self):
        self.client.post(
            NEW_INVOICE,
            self.with_lines(
                [{"service_type": self.service.pk, "quantity": "1", "unit_price": "500.00"}],
                status=Invoice.Status.DRAFT,
            ),
        )
        summary = self.client.get(reverse("jobs:financials"), {"range": "month"}).context["summary"]
        self.assertEqual(summary["revenue"], Decimal("0.00"))

    def test_the_page_is_called_profit(self):
        response = self.client.get(reverse("jobs:financials"))
        self.assertContains(response, "<h1>Profit</h1>", html=False)
        self.assertContains(response, "Revenue − expenses")


class DateTests(FinanceTestCase):
    def test_an_expense_keeps_the_date_it_was_given(self):
        given = date(2026, 3, 9)
        self.client.post(
            NEW_EXPENSE,
            {
                "date": given.isoformat(),
                "amount": "40.00",
                "category": Expense.Category.MARKETING,
                "description": "Yard signs",
            },
        )
        self.assertEqual(Expense.objects.get().date, given)
