import re
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


def _selected_address(response):
    """The pk selected in the **address** field, or None. See the twin
    in test_scheduling.py for why this reads one select's markup rather
    than searching the page."""
    page = response.content.decode()
    start = page.index('id="id_service_property"')
    block = page[start : page.index("</select>", start)]
    found = re.search(r'value="(\d+)"\s+selected', block)
    return int(found.group(1)) if found else None


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

    def test_the_customer_dropdown_offers_a_search_box(self):
        """The job form has had one since Phase 22; this form had none,
        and both pick a customer from the same list. Same contract: the
        box is hidden until the script unhides it, and
        `data-filter-for` names the select's real id.
        """
        page = self.client.get(NEW).content.decode()
        self.assertIn("js/picker.js", page)
        self.assertIn('data-filter-for="id_contact"', page)
        self.assertIn('<p class="field-filter" hidden', page)
        self.assertIn('id="id_contact"', page)
        self.assertIn("data-filter-count", page)
        # The input itself, inside the box. Without it picker.js finds
        # nothing to listen to and returns, leaving a box that never
        # appears — and every assertion above would still pass (#201).
        box = page.split('class="field-filter"', 1)[1].split("</p>", 1)[0]
        self.assertIn('type="search"', box)
        self.assertIn('id="customer-filter"', box)


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


class AddressFollowsCustomerTests(EstimateTestCase):
    """Choosing a customer offers their address (owner request,
    2026-11-03).

    The script does this in the page; these cover the halves it never
    sees — a form arriving with `?contact=` from the quick-add round
    trip, and a browser with JavaScript off, where the server has to
    have made the same choice already.
    """

    def setUp(self):
        super().setUp()
        self.home = Property.objects.create(
            contact=self.customer,
            label="Home",
            street="12 Oak Ave",
            city="Penfield",
            state="NY",
            postal_code="14526",
            is_primary=True,
        )
        self.rental = Property.objects.create(
            contact=self.customer,
            label="Rental",
            street="400 Elm St",
            city="Webster",
            state="NY",
            postal_code="14580",
        )

    def test_arriving_with_a_customer_offers_their_main_address(self):
        response = self.client.get(NEW, {"contact": str(self.customer.pk)})
        self.assertContains(
            response, f'value="{self.home.pk}" selected data-contact="{self.customer.pk}"'
        )
        self.assertNotContains(
            response, f'value="{self.rental.pk}" selected data-contact="{self.customer.pk}"'
        )

    def test_an_address_handed_back_by_the_quick_add_page_wins(self):
        """The round trip is somebody saying "this one, the new one".
        It must beat the primary-address default."""
        response = self.client.get(
            NEW, {"contact": str(self.customer.pk), "service_property": str(self.rental.pk)}
        )
        self.assertContains(
            response, f'value="{self.rental.pk}" selected data-contact="{self.customer.pk}"'
        )

    def test_a_customer_with_no_primary_address_gets_none_chosen(self):
        """Addresses with no primary among them: better blank than a
        guess at which house.

        The first version looked for `selected>Pat Homeowner — 12 Oak
        Ave`, which a selected option never renders — `data-contact`
        comes between — so it passed whatever happened (#202).
        """
        self.home.is_primary = False
        self.home.save(update_fields=["is_primary"])
        response = self.client.get(NEW, {"contact": str(self.customer.pk)})
        self.assertEqual(_selected_address(response), None)

    def test_editing_an_estimate_honours_a_quick_added_address(self):
        """The quick-add buttons are on the edit form too, and the
        update view ignored what they handed back (#202)."""
        quote = f.quote(self.customer, self.rep)
        quote.service_property = self.home
        quote.save(update_fields=["service_property"])
        response = self.client.get(
            reverse("jobs:quote_update", args=[quote.pk]),
            {"service_property": str(self.rental.pk)},
        )
        self.assertEqual(_selected_address(response), self.rental.pk)

    def test_editing_an_estimate_does_not_invent_an_address(self):
        """An estimate saved without one keeps it blank when reopened.
        The server must not default it, and the script must not either
        — saving an unrelated field would otherwise persist an address
        nobody chose."""
        quote = f.quote(self.customer, self.rep)
        response = self.client.get(reverse("jobs:quote_update", args=[quote.pk]))
        self.assertEqual(_selected_address(response), None)

    def test_each_address_says_whose_it_is(self):
        """What the script reads to narrow the list. Without these
        attributes it cannot tell one customer's addresses from
        another's, and silently does nothing."""
        page = self.client.get(NEW).content.decode()
        self.assertIn(f'data-contact="{self.customer.pk}"', page)
        self.assertIn('data-primary="1"', page)
        self.assertIn("js/address.js", page)
        self.assertIn("data-address-for=", page)
        self.assertIn("data-address-customer=", page)

    def test_the_estimate_form_offers_both_quick_add_buttons(self):
        """Parity with the job form: a customer or address can be added
        without abandoning the estimate."""
        page = self.client.get(NEW, {"contact": str(self.customer.pk)}).content.decode()
        self.assertIn(reverse("crm:contact_create"), page)
        self.assertIn(reverse("crm:property_create"), page)
        self.assertIn(f"contact={self.customer.pk}", page)

    def test_an_address_belonging_to_somebody_else_is_still_refused(self):
        """The server-side check stays the backstop. The script narrows
        the list; a hand-made POST ignores it."""
        other = f.contact(self.rep, "Sam", "Elsewhere")
        theirs = Property.objects.create(
            contact=other,
            label="Home",
            street="9 Pine Rd",
            city="Fairport",
            state="NY",
            postal_code="14450",
        )
        response = self.client.post(NEW, self.form(service_property=theirs.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "belongs to a different customer")


class WholeNumberQuantityTests(EstimateTestCase):
    """The same rule as the job form, because they share one formset
    (owner request, 2026-11-03). Proved here rather than inferred."""

    def test_a_fraction_is_refused_and_nothing_is_saved(self):
        response = self.client.post(
            NEW,
            self.with_lines(
                [{"service_type": self.service.pk, "quantity": "1.5", "unit_price": "100.00"}]
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Quote.objects.exists())
        self.assertFalse(QuoteLineItem.objects.exists())

    def test_a_whole_number_is_accepted(self):
        self.client.post(
            NEW,
            self.with_lines(
                [{"service_type": self.service.pk, "quantity": "4", "unit_price": "100.00"}]
            ),
        )
        self.assertEqual(Quote.objects.get().line_items.get().quantity, Decimal("4"))
