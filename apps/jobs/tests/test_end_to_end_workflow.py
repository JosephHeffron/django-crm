"""One customer, from first contact to money in the bank.

QA audit, acceptance test. Every other test in this project checks one
view, one form or one rule. This one walks the whole business through
the app the way the owner actually uses it, in order, through real HTTP
requests, and checks the database after each step rather than trusting
the redirect:

    new customer -> their address -> an estimate -> accept it ->
    schedule it as a job -> mark it done -> invoice it -> take payment
    -> the invoice reads paid, and the month's figures include it

The point is the joins between features. A unit test on each step can
pass while the sequence is broken — an estimate whose lines do not
reach the job, a completed job that never lands in the figures, a
payment that settles the wrong invoice. Those are the failures a
business notices and tests usually do not.

Each step asserts on model state, not on page content, because a page
can say "saved" while nothing was written.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Contact, Property
from apps.crm.tests._helpers import grant_role
from apps.jobs import reports
from apps.jobs.models import Invoice, Job, Payment, Quote
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"


class TheWholeJobTests(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley"), Role.SALES_REP)
        self.casey = grant_role(f.user("casey"), Role.CLEANER)
        self.service = f.service()
        self.client.login(username="boss", password=PASSWORD)

    # --- the steps, each one a real request ---------------------------

    def step_new_customer(self):
        response = self.client.post(
            reverse("crm:contact_create"),
            {
                "first_name": "Marguerite",
                "last_name": "Okonkwo",
                "status": Contact.Status.LEAD,
                "email": "m.okonkwo@example.test",
                "phone": "585-555-0142",
                "preferred_contact_method": "",
                "lead_source": "referral",
                "title": "",
                "notes": "Called about the gutters.",
                "is_active": "on",
                "owner": self.rep.pk,
            },
        )
        self.assertIn(response.status_code, (301, 302), "creating a customer did not redirect")
        customer = Contact.objects.get(last_name="Okonkwo")
        self.assertEqual(customer.status, Contact.Status.LEAD)
        self.assertEqual(customer.created_by, self.owner)
        return customer

    def step_their_address(self, customer):
        response = self.client.post(
            reverse("crm:property_create"),
            {
                "contact": customer.pk,
                "label": "Home",
                "street": "118 Castlebar Rd",
                "city": "Rochester",
                "state": "NY",
                "postal_code": "14610",
                "is_primary": "on",
                "notes": "",
            },
        )
        self.assertIn(response.status_code, (301, 302))
        address = Property.objects.get(contact=customer)
        self.assertTrue(address.is_primary)
        return address

    def step_an_estimate(self, customer, address):
        response = self.client.post(
            reverse("jobs:quote_create"),
            {
                "contact": customer.pk,
                "service_property": address.pk,
                "status": Quote.Status.SENT,
                "site_visit_at": "",
                "expires_on": (timezone.localdate() + timedelta(days=30)).isoformat(),
                "notes": "",
                "lines-TOTAL_FORMS": "2",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-service_type": self.service.pk,
                "lines-0-description": "Clear gutters, front and back",
                "lines-0-quantity": "1",
                "lines-0-unit_price": "240.00",
                "lines-1-service_type": self.service.pk,
                "lines-1-description": "Downspout flush",
                "lines-1-quantity": "2",
                "lines-1-unit_price": "45.00",
            },
        )
        self.assertIn(response.status_code, (301, 302))
        quote = Quote.objects.get(contact=customer)
        self.assertEqual(quote.line_items.count(), 2, "a line was silently dropped")
        self.assertEqual(quote.total, Decimal("330.00"))
        return quote

    def step_accept_it(self, quote):
        response = self.client.post(
            reverse("jobs:quote_update", args=[quote.pk]),
            {
                "contact": quote.contact_id,
                "service_property": quote.service_property_id or "",
                "status": Quote.Status.ACCEPTED,
                "site_visit_at": "",
                "expires_on": quote.expires_on.isoformat() if quote.expires_on else "",
                "notes": "",
                "lines-TOTAL_FORMS": "2",
                "lines-INITIAL_FORMS": "2",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                **{
                    f"lines-{i}-{key}": value
                    for i, line in enumerate(quote.line_items.all())
                    for key, value in (
                        ("id", line.pk),
                        ("service_type", line.service_type_id),
                        ("description", line.description),
                        ("quantity", str(line.quantity)),
                        ("unit_price", str(line.unit_price)),
                    )
                },
            },
        )
        self.assertIn(response.status_code, (301, 302))
        quote.refresh_from_db()
        self.assertEqual(quote.status, Quote.Status.ACCEPTED)
        self.assertEqual(quote.total, Decimal("330.00"), "accepting changed the price")
        return quote

    def step_schedule_it(self, quote):
        start = (timezone.localtime() + timedelta(days=2)).replace(
            hour=9, minute=0, second=0, microsecond=0
        )
        lines = list(quote.line_items.all())
        data = {
            "contact": quote.contact_id,
            "service_property": quote.service_property_id or "",
            "primary_service_type": self.service.pk,
            "status": Job.Status.SCHEDULED,
            "scheduled_start": start.strftime("%Y-%m-%dT%H:%M"),
            "scheduled_end": (start + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
            "sales_rep": self.rep.pk,
            "notes": "",
            "crew": [self.casey.pk],
            "lines-TOTAL_FORMS": str(len(lines)),
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
        }
        for i, line in enumerate(lines):
            data[f"lines-{i}-service_type"] = line.service_type_id
            data[f"lines-{i}-description"] = line.description
            data[f"lines-{i}-quantity"] = str(line.quantity)
            data[f"lines-{i}-unit_price"] = str(line.unit_price)
        response = self.client.post(f"{reverse('jobs:job_create')}?quote={quote.pk}", data)
        self.assertIn(response.status_code, (301, 302))
        job = Job.objects.get(contact=quote.contact_id)
        self.assertEqual(job.quote_id, quote.pk, "the job lost its link to the estimate")
        self.assertEqual(
            job.total, Decimal("330.00"), "the agreed price did not survive scheduling"
        )
        self.assertIn(self.casey, [a.user for a in job.assignments.all()])
        return job

    def step_mark_it_done(self, job):
        response = self.client.post(
            reverse("jobs:job_status", args=[job.pk]), {"status": Job.Status.COMPLETED}
        )
        self.assertIn(response.status_code, (301, 302))
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.COMPLETED)
        self.assertIsNotNone(
            job.completed_at,
            "status says completed but completed_at is empty — every count of "
            "finished work reads completed_at, so this job would be invisible",
        )
        return job

    def step_invoice_it(self, job):
        today = timezone.localdate()
        response = self.client.post(
            reverse("jobs:invoice_create"),
            {
                "job": job.pk,
                "issued_on": today.isoformat(),
                "due_on": (today + timedelta(days=14)).isoformat(),
                "status": Invoice.Status.SENT,
                "notes": "",
                "lines-TOTAL_FORMS": "2",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
                "lines-0-service_type": self.service.pk,
                "lines-0-description": "Clear gutters, front and back",
                "lines-0-quantity": "1",
                "lines-0-unit_price": "240.00",
                "lines-1-service_type": self.service.pk,
                "lines-1-description": "Downspout flush",
                "lines-1-quantity": "2",
                "lines-1-unit_price": "45.00",
            },
        )
        self.assertIn(response.status_code, (301, 302))
        invoice = Invoice.objects.get(job=job)
        self.assertEqual(invoice.total, Decimal("330.00"))
        self.assertEqual(invoice.balance, Decimal("330.00"))
        return invoice

    def step_take_payment(self, invoice):
        response = self.client.post(
            reverse("jobs:payment_create", args=[invoice.pk]),
            {
                "amount": "330.00",
                "received_on": timezone.localdate().isoformat(),
                "method": "card",
                "notes": "",
            },
        )
        self.assertIn(response.status_code, (301, 302))
        payment = Payment.objects.get(invoice=invoice)
        self.assertEqual(payment.amount, Decimal("330.00"))
        self.assertEqual(payment.recorded_by, self.owner)
        return payment

    # --- the whole thing ---------------------------------------------

    def test_a_customer_goes_from_enquiry_to_paid(self):
        customer = self.step_new_customer()
        address = self.step_their_address(customer)
        quote = self.step_an_estimate(customer, address)
        quote = self.step_accept_it(quote)
        job = self.step_schedule_it(quote)
        job = self.step_mark_it_done(job)
        invoice = self.step_invoice_it(job)
        self.step_take_payment(invoice)

        invoice.refresh_from_db()
        self.assertEqual(invoice.paid, Decimal("330.00"))
        self.assertEqual(invoice.balance, Decimal("0.00"))
        self.assertEqual(invoice.payment_status(timezone.localdate()), "paid")

    def test_the_finished_job_reaches_the_months_figures(self):
        """The join that unit tests miss.

        A job can be completed, invoiced and paid and still be absent
        from every report, because the reports read `completed_at` and
        the money reads payments. This asserts the sequence actually
        lands in the numbers the owner looks at.
        """
        customer = self.step_new_customer()
        address = self.step_their_address(customer)
        quote = self.step_accept_it(self.step_an_estimate(customer, address))
        job = self.step_mark_it_done(self.step_schedule_it(quote))
        invoice = self.step_invoice_it(job)
        self.step_take_payment(invoice)

        today = timezone.localdate()
        period, error = reports.report_period("month", None, None, today)
        self.assertIsNone(error)
        figures = reports.summary(period)
        self.assertEqual(
            figures["collected"],
            Decimal("330.00"),
            "the payment is missing from the month's collected total",
        )
        self.assertEqual(
            figures["revenue"],
            Decimal("330.00"),
            "the invoice is missing from the month's invoiced revenue",
        )
        self.assertEqual(
            figures["jobs_completed"],
            1,
            "the finished job is not counted among the month's completed jobs",
        )

        completed = Job.objects.filter(status=Job.Status.COMPLETED, completed_at__isnull=False)
        self.assertIn(job, completed)

    def test_the_customer_is_now_reachable_from_the_job_and_back(self):
        """Relationships survive the round trip in both directions."""
        customer = self.step_new_customer()
        address = self.step_their_address(customer)
        quote = self.step_accept_it(self.step_an_estimate(customer, address))
        job = self.step_schedule_it(quote)

        self.assertEqual(job.contact, customer)
        self.assertEqual(job.service_property, address)
        self.assertIn(job, customer.jobs.all())
        self.assertIn(quote, customer.quotes.all())
        quote.refresh_from_db()
        self.assertIn(job, quote.jobs.all())

    def test_signing_out_closes_the_door_behind_you(self):
        customer = self.step_new_customer()
        self.client.post(reverse("users:logout"))
        response = self.client.get(reverse("crm:contact_detail", args=[customer.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_a_crew_member_cannot_walk_the_money_half_of_this(self):
        """The same sequence, refused at the point it should be."""
        customer = self.step_new_customer()
        address = self.step_their_address(customer)
        quote = self.step_accept_it(self.step_an_estimate(customer, address))
        job = self.step_schedule_it(quote)

        self.client.post(reverse("users:logout"))
        self.client.login(username="casey", password=PASSWORD)

        self.assertEqual(self.client.get(reverse("jobs:invoice_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("jobs:financials")).status_code, 403)
        # But they can still report their own work as finished.
        response = self.client.post(
            reverse("jobs:job_status", args=[job.pk]), {"status": Job.Status.COMPLETED}
        )
        self.assertIn(response.status_code, (301, 302))
        job.refresh_from_db()
        self.assertEqual(job.status, Job.Status.COMPLETED)
        self.assertIsNotNone(job.completed_at)
