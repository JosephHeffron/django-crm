from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.crm.models import Property
from apps.crm.tests._helpers import grant_role
from apps.jobs.models import Quote, QuoteLineItem
from apps.users.roles import Role

from . import _factories as f

PASSWORD = "correct-horse-battery"
NEW = reverse("jobs:quote_create")
LIST = reverse("jobs:quote_list")


class EstimateTestCase(TestCase):
    def setUp(self):
        self.rep = grant_role(f.user("rep", first_name="Robin"), Role.SALES_REP)
        self.customer = f.contact(self.rep)
        self.service = f.service()
        self.client.login(username="rep", password=PASSWORD)

    def form(self, **extra):
        data = {
            "contact": self.customer.pk,
            "status": Quote.Status.DRAFT,
            "site_visit_at": "",
            "expires_on": "",
            "notes": "",
            "lines-TOTAL_FORMS": "0",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
        }
        data.update(extra)
        return data

    def with_lines(self, rows, initial=0, **extra):
        data = self.form(
            **{"lines-TOTAL_FORMS": str(len(rows)), "lines-INITIAL_FORMS": str(initial)}, **extra
        )
        for index, row in enumerate(rows):
            for key, value in row.items():
                data[f"lines-{index}-{key}"] = value
        return data


class AccessTests(EstimateTestCase):
    def test_a_cleaner_is_refused(self):
        grant_role(f.user("casey"), Role.CLEANER)
        self.client.login(username="casey", password=PASSWORD)
        self.assertEqual(self.client.get(NEW).status_code, 403)
        self.assertEqual(self.client.post(NEW, self.form()).status_code, 403)
        self.assertFalse(Quote.objects.exists())

    def test_the_owner_may_write_one(self):
        grant_role(f.user("boss"), Role.OWNER)
        self.client.login(username="boss", password=PASSWORD)
        self.assertEqual(self.client.get(NEW).status_code, 200)

    def test_an_unknown_estimate_is_not_found(self):
        response = self.client.get(reverse("jobs:quote_update", args=[9999]))
        self.assertEqual(response.status_code, 404)


class WritingTests(EstimateTestCase):
    def test_writing_an_estimate_with_lines(self):
        response = self.client.post(
            NEW,
            self.with_lines(
                [
                    {"service_type": self.service.pk, "quantity": "3", "unit_price": "120.00"},
                    {
                        "service_type": self.service.pk,
                        "description": "Back of house",
                        "quantity": "1",
                        "unit_price": "60.00",
                    },
                ]
            ),
        )
        quote = Quote.objects.get()
        self.assertRedirects(response, quote.get_absolute_url())
        self.assertEqual((quote.contact, quote.prepared_by), (self.customer, self.rep))
        self.assertEqual(quote.total, Decimal("420.00"))
        self.assertEqual(
            [line.position for line in quote.line_items.all()],
            [0, 1],
        )

    def test_a_draft_has_no_sent_date(self):
        self.client.post(NEW, self.form())
        quote = Quote.objects.get()
        self.assertIsNone(quote.sent_at)
        self.assertIsNone(quote.accepted_at)

    def test_sending_records_the_day_it_went_out(self):
        self.client.post(NEW, self.form(status=Quote.Status.SENT))
        quote = Quote.objects.get()
        self.assertIsNotNone(quote.sent_at)
        self.assertIsNone(quote.accepted_at)

    def test_accepting_records_both_dates(self):
        self.client.post(NEW, self.form(status=Quote.Status.ACCEPTED))
        quote = Quote.objects.get()
        self.assertIsNotNone(quote.sent_at)
        self.assertIsNotNone(quote.accepted_at)

    def test_the_sent_date_is_not_moved_by_a_later_edit(self):
        self.client.post(NEW, self.form(status=Quote.Status.SENT))
        quote = Quote.objects.get()
        first_sent = quote.sent_at
        self.client.post(
            reverse("jobs:quote_update", args=[quote.pk]),
            self.form(status=Quote.Status.ACCEPTED, notes="Corrected the price"),
        )
        quote.refresh_from_db()
        self.assertEqual(quote.sent_at, first_sent)

    def test_an_estimate_later_declined_no_longer_shows_a_won_date(self):
        self.client.post(NEW, self.form(status=Quote.Status.ACCEPTED))
        quote = Quote.objects.get()
        self.client.post(
            reverse("jobs:quote_update", args=[quote.pk]),
            self.form(status=Quote.Status.DECLINED),
        )
        quote.refresh_from_db()
        self.assertIsNone(quote.accepted_at)
        self.assertIsNotNone(quote.sent_at)  # it was still sent

    def test_an_address_belonging_to_someone_else_is_refused(self):
        stranger = f.contact(self.rep, "Sam", "Stranger")
        theirs = Property.objects.create(
            contact=stranger, street="9 Elm St", city="Oak Park", state="IL", postal_code="60301"
        )
        response = self.client.post(NEW, self.form(service_property=theirs.pk))
        self.assertContains(response, "belongs to a different customer")
        self.assertFalse(Quote.objects.exists())

    def test_a_site_visit_shows_on_the_schedule(self):
        visit = timezone.localtime(f.aware(2026, 11, 4, 14)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(NEW, self.form(status=Quote.Status.SENT, site_visit_at=visit))
        response = self.client.get(reverse("jobs:calendar"), {"view": "day", "date": "2026-11-04"})
        self.assertContains(response, "Site visit")

    def test_an_expiry_date_is_kept(self):
        self.client.post(NEW, self.form(expires_on="2026-12-31"))
        self.assertEqual(Quote.objects.get().expires_on, date(2026, 12, 31))

    def test_nothing_is_saved_when_a_line_is_wrong(self):
        response = self.client.post(
            NEW,
            self.with_lines([{"service_type": self.service.pk, "quantity": "1", "unit_price": ""}]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Quote.objects.exists())
        self.assertFalse(QuoteLineItem.objects.exists())

    def test_a_customer_can_be_prefilled(self):
        response = self.client.get(NEW, {"contact": str(self.customer.pk)})
        self.assertContains(response, f'<option value="{self.customer.pk}" selected>')


class EditingTests(EstimateTestCase):
    def setUp(self):
        super().setUp()
        self.quote = f.quote(self.customer, self.rep, lines=[(Decimal("1"), Decimal("100"))])
        self.url = reverse("jobs:quote_update", args=[self.quote.pk])

    def test_changing_a_line_price(self):
        line = self.quote.line_items.get()
        response = self.client.post(
            self.url,
            self.with_lines(
                [
                    {
                        "id": line.pk,
                        "service_type": line.service_type_id,
                        "quantity": "1",
                        "unit_price": "250.00",
                    }
                ],
                initial=1,
            ),
        )
        self.assertRedirects(response, self.quote.get_absolute_url())
        self.assertEqual(self.quote.line_items.get().unit_price, Decimal("250.00"))

    def test_removing_a_line(self):
        line = self.quote.line_items.get()
        self.client.post(
            self.url,
            self.with_lines(
                [
                    {
                        "id": line.pk,
                        "service_type": line.service_type_id,
                        "quantity": "1",
                        "unit_price": "100.00",
                        "DELETE": "on",
                    }
                ],
                initial=1,
            ),
        )
        self.assertFalse(self.quote.line_items.exists())


class ListPageTests(EstimateTestCase):
    def test_the_page_is_its_own_not_the_tasks_hub(self):
        response = self.client.get(LIST)
        self.assertContains(response, "<h1>Estimates</h1>", html=False)
        self.assertNotContains(response, "<h1>Tasks</h1>")
        self.assertContains(response, "New estimate")

    def test_the_hub_tabs_are_still_there(self):
        self.assertContains(self.client.get(LIST), 'aria-label="Tasks sections"')

    def test_an_empty_list_offers_to_write_one(self):
        response = self.client.get(LIST)
        self.assertContains(response, "No estimates here")
        self.assertContains(response, NEW)

    def test_each_row_can_be_edited(self):
        quote = f.quote(self.customer, self.rep)
        self.assertContains(self.client.get(LIST), reverse("jobs:quote_update", args=[quote.pk]))
