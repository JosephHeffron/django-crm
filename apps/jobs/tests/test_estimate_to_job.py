"""Scheduling an accepted estimate as a job (Phase 18 unit 3).

"In one click" means one click to the job form with everything carried
across — not a job created outright, because a job needs a date and a
time and only a person knows those. `scheduled_start` and
`scheduled_end` are both required, so there is nothing sensible to
invent.

The trap this file guards is the formset one. A formset renders exactly
as many blank rows as it is told to, whatever initial data it is
handed, so seeding it with a three-line estimate while asking for one
row silently drops two of them. That bug has already happened once in
this project, when invoicing a multi-line job.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Job, Quote, QuoteLineItem, ServiceType
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"
NEW_JOB = reverse("jobs:job_create")


class EstimateToJobTestCase(TestCase):
    def setUp(self):
        self.owner = grant_role(f.user("boss"), Role.OWNER)
        self.rep = grant_role(f.user("riley", first_name="Riley"), Role.SALES_REP)
        self.crew = grant_role(f.user("casey"), Role.CLEANER)
        self.customer = f.contact(self.owner)
        self.gutters = f.service()
        self.windows = ServiceType.objects.exclude(pk=self.gutters.pk).first() or self.gutters
        self.client.login(username="boss", password=PASSWORD)

    def accepted(self, lines=2, prepared_by=None):
        quote = Quote.objects.create(
            contact=self.customer,
            prepared_by=prepared_by or self.rep,
            status=Quote.Status.ACCEPTED,
            accepted_at=timezone.now(),
        )
        services = [self.gutters, self.windows][:lines]
        for position, service in enumerate(services):
            QuoteLineItem.objects.create(
                quote=quote,
                service_type=service,
                description=f"Line {position}",
                quantity=Decimal("2"),
                unit_price=Decimal(str(100 + position * 25)),
                position=position,
            )
        return quote

    def open_form(self, quote):
        response = self.client.get(NEW_JOB, {"quote": quote.pk})
        self.assertEqual(response.status_code, 200)
        return response


class PrefillTests(EstimateToJobTestCase):
    def test_the_estimate_page_offers_to_schedule_accepted_work(self):
        quote = self.accepted()
        response = self.client.get(quote.get_absolute_url())
        self.assertContains(response, f"{NEW_JOB}?quote={quote.pk}")
        self.assertContains(response, "Schedule this work")

    def test_an_unaccepted_estimate_offers_nothing(self):
        """Booking work the customer hasn't agreed to is backwards."""
        for status in (Quote.Status.DRAFT, Quote.Status.SENT, Quote.Status.DECLINED):
            quote = self.accepted()
            quote.status = status
            quote.save(update_fields=["status"])
            response = self.client.get(quote.get_absolute_url())
            self.assertNotContains(response, "Schedule this work", msg_prefix=status)

    def test_the_customer_and_seller_carry_across(self):
        quote = self.accepted()
        form = self.open_form(quote).context["form"]
        self.assertEqual(form.initial["contact"], self.customer.pk)
        self.assertEqual(form.initial["sales_rep"], self.rep.pk)

    def test_the_address_carries_across(self):
        from apps.crm.models import Property

        quote = self.accepted()
        address = Property.objects.create(
            contact=self.customer,
            street="1 Oak Ave",
            city="Penfield",
            state="NY",
            postal_code="14526",
        )
        quote.service_property = address
        quote.save(update_fields=["service_property"])
        form = self.open_form(quote).context["form"]
        self.assertEqual(form.initial["service_property"], address.pk)

    def test_the_first_service_becomes_the_job_service(self):
        # It decides the calendar colour, so it should not be blank.
        quote = self.accepted()
        form = self.open_form(quote).context["form"]
        self.assertEqual(form.initial["primary_service_type"], self.gutters.pk)

    def test_the_page_says_which_estimate_it_came_from(self):
        quote = self.accepted()
        response = self.open_form(quote)
        self.assertContains(response, quote.number)
        self.assertEqual(response.context["from_quote"], quote)

    def test_opening_the_form_without_an_estimate_prefills_nothing(self):
        response = self.client.get(NEW_JOB)
        self.assertIsNone(response.context["from_quote"])
        self.assertNotIn("contact", response.context["form"].initial)


class LineCopyingTests(EstimateToJobTestCase):
    """The formset trap."""

    def rows(self, response):
        return response.context["lines"]

    def test_every_line_on_the_estimate_is_offered(self):
        """A formset shows exactly as many rows as it is told to.

        Seeded with two lines while asking for one row, it would show
        one and silently drop the other — which is what happened when
        invoicing a multi-line job.
        """
        quote = self.accepted(lines=2)
        lines = self.rows(self.open_form(quote))
        seeded = [form.initial for form in lines.forms if form.initial]
        self.assertEqual(len(seeded), 2)
        self.assertEqual(
            [row["service_type"] for row in seeded],
            [self.gutters.pk, self.windows.pk],
        )

    def test_there_is_a_spare_row_to_add_work_with(self):
        quote = self.accepted(lines=2)
        self.assertGreaterEqual(len(self.rows(self.open_form(quote)).forms), 3)

    def test_the_prices_and_quantities_come_across(self):
        quote = self.accepted(lines=2)
        seeded = [row.initial for row in self.rows(self.open_form(quote)).forms if row.initial]
        self.assertEqual(
            [(row["quantity"], row["unit_price"]) for row in seeded],
            [(Decimal("2"), Decimal("100")), (Decimal("2"), Decimal("125"))],
        )

    def test_an_estimate_with_no_lines_still_opens(self):
        quote = self.accepted(lines=0)
        response = self.open_form(quote)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(self.rows(response).forms), 1)


class SavingTests(EstimateToJobTestCase):
    def book(self, quote, lines=2):
        start = timezone.localtime(timezone.now() + timedelta(days=3))
        data = {
            "contact": self.customer.pk,
            "primary_service_type": self.gutters.pk,
            "status": Job.Status.SCHEDULED,
            "scheduled_start": start.strftime("%Y-%m-%dT%H:%M"),
            "scheduled_end": (start + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
            "sales_rep": self.rep.pk,
            "notes": "",
            "lines-TOTAL_FORMS": str(lines),
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
        }
        services = [self.gutters, self.windows][:lines]
        for i, service in enumerate(services):
            data[f"lines-{i}-service_type"] = service.pk
            data[f"lines-{i}-description"] = f"Line {i}"
            data[f"lines-{i}-quantity"] = "2"
            data[f"lines-{i}-unit_price"] = str(100 + i * 25)
        return self.client.post(f"{NEW_JOB}?quote={quote.pk}", data)

    def test_the_job_is_linked_back_to_its_estimate(self):
        quote = self.accepted()
        self.book(quote)
        job = Job.objects.get()
        self.assertEqual(job.quote_id, quote.pk)

    def test_the_estimate_lists_the_job_it_became(self):
        quote = self.accepted()
        self.book(quote)
        self.assertEqual([j.pk for j in quote.jobs.all()], [Job.objects.get().pk])

    def test_all_the_work_is_saved_not_just_the_first_line(self):
        quote = self.accepted(lines=2)
        self.book(quote, lines=2)
        job = Job.objects.get()
        self.assertEqual(job.line_items.count(), 2)

    def test_booking_without_an_estimate_leaves_the_link_empty(self):
        start = timezone.localtime(timezone.now() + timedelta(days=3))
        self.client.post(
            NEW_JOB,
            {
                "contact": self.customer.pk,
                "primary_service_type": self.gutters.pk,
                "status": Job.Status.SCHEDULED,
                "scheduled_start": start.strftime("%Y-%m-%dT%H:%M"),
                "scheduled_end": (start + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "sales_rep": self.rep.pk,
                "notes": "",
                "lines-TOTAL_FORMS": "0",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertIsNone(Job.objects.get().quote_id)

    def test_editing_a_job_later_does_not_disturb_its_estimate_link(self):
        quote = self.accepted()
        self.book(quote)
        job = Job.objects.get()
        start = timezone.localtime(job.scheduled_start)
        self.client.post(
            reverse("jobs:job_update", args=[job.pk]),
            {
                "contact": self.customer.pk,
                "primary_service_type": self.gutters.pk,
                "status": Job.Status.SCHEDULED,
                "scheduled_start": start.strftime("%Y-%m-%dT%H:%M"),
                "scheduled_end": (start + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"),
                "sales_rep": self.rep.pk,
                "notes": "changed",
                "lines-TOTAL_FORMS": "0",
                "lines-INITIAL_FORMS": "0",
                "lines-MIN_NUM_FORMS": "0",
                "lines-MAX_NUM_FORMS": "1000",
            },
        )
        job.refresh_from_db()
        self.assertEqual((job.notes, job.quote_id), ("changed", quote.pk))


class AccessTests(EstimateToJobTestCase):
    def test_a_sales_rep_can_schedule_accepted_work(self):
        quote = self.accepted()
        self.client.login(username="riley", password=PASSWORD)
        self.assertEqual(self.client.get(NEW_JOB, {"quote": quote.pk}).status_code, 200)

    def test_a_crew_member_cannot_reach_the_job_form_at_all(self):
        quote = self.accepted()
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(NEW_JOB, {"quote": quote.pk}).status_code, 403)

    def test_a_nonsense_estimate_reference_is_ignored(self):
        for value in ("banana", "0", "99999", ""):
            response = self.client.get(NEW_JOB, {"quote": value})
            self.assertEqual(response.status_code, 200, value)
            self.assertIsNone(response.context["from_quote"], value)

    def test_an_estimate_that_is_not_accepted_prefills_nothing(self):
        """Guarded in the view, not only hidden in the template.

        A link can be typed, and the template check alone would let
        somebody schedule declined work by editing the URL.
        """
        quote = self.accepted()
        quote.status = Quote.Status.DECLINED
        quote.save(update_fields=["status"])
        response = self.client.get(NEW_JOB, {"quote": quote.pk})
        self.assertIsNone(response.context["from_quote"])
        self.assertNotIn("contact", response.context["form"].initial)
